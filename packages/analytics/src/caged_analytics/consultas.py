"""Consultas e comparacoes sobre os dados normalizados do CAGED.

Sem dependencia de FastAPI: recebe um DataFrame e devolve dataclasses imutaveis.

    from caged_analytics.consultas import Filtro, totais, serie_mensal, comparar

    filtro = Filtro(inicio="2025-01", fim="2025-06", municipios=["Campinas"], setores=["C"])
    totais(df, filtro)                       # Totais(admissoes=..., desligamentos=..., saldo=...)
    serie_mensal(df, filtro)                 # [PontoMensal, ...] em ordem de competencia
    comparar(df, "municipio", ["350950", "354850"], filtro)

O DataFrame esperado e o de `pipeline.load_normalized` (colunas de `schema.CANONICAL_COLUMNS`).
Tambem funciona com as tabelas de `tabelas.load_tabelas`, desde que se use apenas as
dimensoes que a tabela possui (a planilha oficial NAO cruza municipio com setor):
filtrar por uma dimensao ausente levanta `DimensaoIndisponivel`.

Regras:
- Municipio: codigo IBGE (6 ou 7 digitos) ou nome (sem distincao de acento/caixa).
  Prefira o codigo: nomes iguais existem em UFs diferentes.
- Setor: secao CNAE (A..U), codigo agregado (TOTAL, IND, SERV...), divisao CNAE ou nome.
- Competencias sao "YYYY-MM"; o intervalo e inclusivo nas duas pontas.
- Em tabelas de setor hierarquicas (coluna `setor_nivel`), sem filtro de setor somente o
  nivel 1 e usado, para nao contar em dobro. Com filtro de setor, as linhas pedidas
  sao usadas como estao (nao selecione pai e filho juntos).
- Nenhum valor e inventado: periodos sem dados ficam de fora da serie, a menos que
  `preencher_lacunas=True` seja pedido explicitamente.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Literal

import pandas as pd

from . import normalize as nz

METRICAS: tuple[str, ...] = ("admissoes", "desligamentos", "saldo")
Metrica = Literal["admissoes", "desligamentos", "saldo"]
Dimensao = Literal["municipio", "setor"]

# Codigos agregados das tabelas oficiais (alem das secoes A..U).
_SETORES_AGREGADOS = frozenset(
    {"TOTAL", "IND", "SERV", "SERV_INFO", "SERV_ADM", "SERV_OUTROS", "NI"}
)


class ConsultaError(ValueError):
    """Erro de consulta (a API o traduz para HTTP 422)."""


class FiltroInvalido(ConsultaError):
    """Parametro de filtro invalido."""


class DimensaoIndisponivel(ConsultaError):
    """A base nao possui a dimensao/coluna pedida."""


# --- resultados ----------------------------------------------------------------
@dataclass(frozen=True)
class Totais:
    admissoes: int
    desligamentos: int
    saldo: int


@dataclass(frozen=True)
class PontoMensal:
    competencia: str
    admissoes: int
    desligamentos: int
    saldo: int


@dataclass(frozen=True)
class Resumo:
    chave: str  # codigo do municipio (ou nome padronizado, sem codigo) / codigo do setor
    nome: str
    admissoes: int
    desligamentos: int
    saldo: int


@dataclass(frozen=True)
class ItemComparado:
    chave: str
    nome: str
    totais: Totais
    participacao_admissoes: float | None  # fracao 0..1 das admissoes do recorte; None se total 0
    serie: tuple[PontoMensal, ...]


@dataclass(frozen=True)
class Comparacao:
    por: Dimensao
    metrica: Metrica  # criterio de ordenacao (decrescente)
    itens: tuple[ItemComparado, ...]
    sem_dados: tuple[str, ...]  # itens pedidos sem nenhuma linha no recorte
    total: Totais  # soma de todos os itens comparados


@dataclass(frozen=True)
class Opcao:
    chave: str
    nome: str


@dataclass(frozen=True)
class Opcoes:
    competencia_inicio: str | None
    competencia_fim: str | None
    municipios: tuple[Opcao, ...]
    setores: tuple[Opcao, ...]


# --- filtro --------------------------------------------------------------------
def _lista(valor: Iterable[str] | str | None) -> tuple[str, ...]:
    if valor is None:
        return ()
    return (valor,) if isinstance(valor, str) else tuple(valor)


def _competencia(valor: str | None) -> str | None:
    if valor is None:
        return None
    try:
        return nz.normalize_competencia(valor)
    except nz.NormalizationError as exc:
        raise FiltroInvalido(str(exc)) from exc


def _token_municipio(valor: str) -> str:
    texto = re.sub(r"\s+", " ", str(valor).strip())
    if not texto:
        raise FiltroInvalido("municipio vazio")
    if texto.isdigit():
        try:
            return nz.normalize_municipio_codigo(texto)
        except nz.NormalizationError as exc:
            raise FiltroInvalido(str(exc)) from exc
    return nz.municipio_chave(texto)


def _token_setor(valor: str) -> str:
    texto = str(valor).strip()
    if texto.upper() in _SETORES_AGREGADOS:
        return texto.upper()
    try:
        return nz.normalize_setor(texto)
    except nz.NormalizationError as exc:
        raise FiltroInvalido(str(exc)) from exc


@dataclass(frozen=True)
class Filtro:
    """Recorte da consulta. Listas vazias significam "todos"; varios itens = OU."""

    inicio: str | None = None
    fim: str | None = None
    municipios: tuple[str, ...] = ()
    setores: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        inicio, fim = _competencia(self.inicio), _competencia(self.fim)
        if inicio and fim and inicio > fim:
            raise FiltroInvalido(f"inicio ({inicio}) posterior ao fim ({fim})")
        municipios = tuple(dict.fromkeys(_token_municipio(m) for m in _lista(self.municipios)))
        setores = tuple(dict.fromkeys(_token_setor(s) for s in _lista(self.setores)))
        object.__setattr__(self, "inicio", inicio)
        object.__setattr__(self, "fim", fim)
        object.__setattr__(self, "municipios", municipios)
        object.__setattr__(self, "setores", setores)


def _exigir(df: pd.DataFrame, *colunas: str) -> None:
    faltando = [c for c in colunas if c not in df.columns]
    if faltando:
        raise DimensaoIndisponivel(f"a base nao possui a(s) coluna(s): {', '.join(faltando)}")


def _chave_municipio(df: pd.DataFrame) -> pd.Series:
    if "municipio_chave" in df.columns:
        return df["municipio_chave"]
    if "municipio" in df.columns:
        return df["municipio"].map(lambda v: nz.municipio_chave(v) if isinstance(v, str) else None)
    raise DimensaoIndisponivel("a base nao possui municipio")


def _mascara_municipio(df: pd.DataFrame, tokens: tuple[str, ...]) -> pd.Series:
    codigos = {t for t in tokens if t.isdigit()}
    nomes = {t for t in tokens if not t.isdigit()}
    mascara = pd.Series(False, index=df.index)
    if codigos:
        _exigir(df, "municipio_codigo")
        mascara |= df["municipio_codigo"].isin(codigos)
    if nomes:
        mascara |= _chave_municipio(df).isin(nomes)
    return mascara


def aplicar_filtro(df: pd.DataFrame, filtro: Filtro | None = None) -> pd.DataFrame:
    """Linhas de `df` que atendem ao filtro (periodo, municipio e setor)."""
    filtro = filtro or Filtro()
    mascara = pd.Series(True, index=df.index)
    if filtro.inicio or filtro.fim:
        _exigir(df, "competencia")
        if filtro.inicio:
            mascara &= df["competencia"] >= filtro.inicio
        if filtro.fim:
            mascara &= df["competencia"] <= filtro.fim
    if filtro.municipios:
        mascara &= _mascara_municipio(df, filtro.municipios)
    if filtro.setores:
        _exigir(df, "setor_codigo")
        mascara &= df["setor_codigo"].isin(filtro.setores)
    recorte = df.loc[mascara]
    if "setor_nivel" in recorte.columns and not filtro.setores:
        recorte = recorte[recorte["setor_nivel"] == 1]  # evita contar a hierarquia em dobro
    return recorte


# --- agregacoes ----------------------------------------------------------------
def _somar(df: pd.DataFrame) -> Totais:
    _exigir(df, *METRICAS)
    return Totais(*(int(df[m].sum()) for m in METRICAS))


def totais(df: pd.DataFrame, filtro: Filtro | None = None) -> Totais:
    """Admissoes, desligamentos e saldo do recorte (zeros se o recorte for vazio)."""
    return _somar(aplicar_filtro(df, filtro))


def serie_mensal(
    df: pd.DataFrame, filtro: Filtro | None = None, *, preencher_lacunas: bool = False
) -> list[PontoMensal]:
    """Agregacao mensal em ordem de competencia.

    Com `preencher_lacunas=True`, meses sem linhas entre o inicio e o fim (do filtro, ou
    do primeiro ao ultimo mes com dados) entram com zeros.
    """
    filtro = filtro or Filtro()
    recorte = aplicar_filtro(df, filtro)
    _exigir(recorte, "competencia", *METRICAS)
    if recorte.empty:
        return []
    soma = recorte.groupby("competencia")[list(METRICAS)].sum().sort_index()
    pontos = {
        str(linha.Index): PontoMensal(
            str(linha.Index), int(linha.admissoes), int(linha.desligamentos), int(linha.saldo)
        )
        for linha in soma.itertuples()
    }
    if preencher_lacunas:
        inicio, fim = filtro.inicio or min(pontos), filtro.fim or max(pontos)
        for periodo in pd.period_range(inicio, fim, freq="M"):
            pontos.setdefault(str(periodo), PontoMensal(str(periodo), 0, 0, 0))
    return [pontos[c] for c in sorted(pontos)]


def _validar_dimensao(por: str) -> None:
    if por not in ("municipio", "setor"):
        raise ConsultaError(f"dimensao invalida: {por!r} (use 'municipio' ou 'setor')")


def _validar_metrica(metrica: str) -> None:
    if metrica not in METRICAS:
        raise ConsultaError(f"metrica invalida: {metrica!r} (use {', '.join(METRICAS)})")


def _com_identidade(df: pd.DataFrame, por: str) -> pd.DataFrame:
    """Acrescenta `_chave` (identificador estavel) e `_nome` (rotulo de exibicao)."""
    if por == "setor":
        _exigir(df, "setor_codigo")
        chave = df["setor_codigo"].astype("object")
        nome = df["setor"].astype("object") if "setor" in df.columns else chave
    else:
        if "municipio_codigo" not in df.columns and "municipio" not in df.columns:
            raise DimensaoIndisponivel("a base nao possui municipio")
        codigo = df["municipio_codigo"].astype("object") if "municipio_codigo" in df else None
        nome = df["municipio"].astype("object") if "municipio" in df else None
        chave_nome = _chave_municipio(df).astype("object") if nome is not None else None
        if codigo is None:
            chave = chave_nome
        elif chave_nome is None:
            chave = codigo
        else:
            chave = codigo.where(codigo.notna(), chave_nome)
        nome = chave if nome is None else nome
    nome = nome.where(nome.notna(), chave)
    return df.assign(_chave=chave, _nome=nome)


def agrupar(df: pd.DataFrame, por: Dimensao, filtro: Filtro | None = None) -> list[Resumo]:
    """Totais por municipio ou por setor, em ordem de chave."""
    _validar_dimensao(por)
    recorte = _com_identidade(aplicar_filtro(df, filtro), por)
    _exigir(recorte, *METRICAS)
    if recorte.empty:
        return []
    grupos = recorte.groupby("_chave", sort=True).agg(
        nome=("_nome", "first"),
        admissoes=("admissoes", "sum"),
        desligamentos=("desligamentos", "sum"),
        saldo=("saldo", "sum"),
    )
    return [
        Resumo(str(g.Index), str(g.nome), int(g.admissoes), int(g.desligamentos), int(g.saldo))
        for g in grupos.itertuples()
    ]


def _tokens_presentes(df: pd.DataFrame, por: str) -> set[str]:
    if por == "setor":
        return set(df["setor_codigo"].dropna().astype(str))
    tokens: set[str] = set()
    if "municipio_codigo" in df.columns:
        tokens |= set(df["municipio_codigo"].dropna().astype(str))
    if "municipio_chave" in df.columns or "municipio" in df.columns:
        tokens |= set(_chave_municipio(df).dropna().astype(str))
    return tokens


def comparar(
    df: pd.DataFrame,
    por: Dimensao,
    itens: Iterable[str] | None = None,
    filtro: Filtro | None = None,
    *,
    metrica: Metrica = "saldo",
) -> Comparacao:
    """Compara municipios ou setores no mesmo recorte.

    `itens` (codigos ou nomes) substitui o filtro da dimensao comparada; sem `itens`,
    compara todos. A lista sai ordenada por `metrica`, do maior para o menor.
    """
    _validar_dimensao(por)
    _validar_metrica(metrica)
    filtro = filtro or Filtro()
    campo = "municipios" if por == "municipio" else "setores"
    if itens:
        filtro = replace(filtro, **{campo: _lista(itens)})

    recorte = _com_identidade(aplicar_filtro(df, filtro), por)
    _exigir(recorte, "competencia", *METRICAS)

    pedidos: tuple[str, ...] = getattr(filtro, campo)
    presentes = _tokens_presentes(recorte, por) if pedidos else set()
    sem_dados = tuple(t for t in pedidos if t not in presentes)

    total = _somar(recorte)
    soma = recorte.groupby("_chave").agg(
        nome=("_nome", "first"),
        admissoes=("admissoes", "sum"),
        desligamentos=("desligamentos", "sum"),
        saldo=("saldo", "sum"),
    )
    series: dict[str, list[PontoMensal]] = {}
    mensal = recorte.groupby(["_chave", "competencia"])[list(METRICAS)].sum()
    for (chave, comp), linha in mensal.iterrows():
        series.setdefault(str(chave), []).append(
            PontoMensal(
                str(comp),
                int(linha["admissoes"]),
                int(linha["desligamentos"]),
                int(linha["saldo"]),
            )
        )

    comparados = [
        ItemComparado(
            chave=str(g.Index),
            nome=str(g.nome),
            totais=Totais(int(g.admissoes), int(g.desligamentos), int(g.saldo)),
            participacao_admissoes=(
                int(g.admissoes) / total.admissoes if total.admissoes else None
            ),
            serie=tuple(series.get(str(g.Index), ())),
        )
        for g in soma.itertuples()
    ]
    comparados.sort(key=lambda i: (-getattr(i.totais, metrica), i.nome))
    return Comparacao(por, metrica, tuple(comparados), sem_dados, total)


def opcoes_filtro(df: pd.DataFrame) -> Opcoes:
    """Valores disponiveis na base, para montar os filtros do front."""
    competencias = df["competencia"].dropna() if "competencia" in df.columns else pd.Series([])

    def _opcoes(por: str) -> tuple[Opcao, ...]:
        try:
            com_id = _com_identidade(df, por)
        except DimensaoIndisponivel:
            return ()
        unicos = com_id.drop_duplicates("_chave")
        opcoes = [Opcao(str(c), str(n)) for c, n in zip(unicos["_chave"], unicos["_nome"])]
        # setores seguem a ordem da secao CNAE (A..U); municipios, a ordem alfabetica
        return tuple(
            sorted(
                opcoes,
                key=(lambda o: (o.chave,)) if por == "setor" else (lambda o: (o.nome, o.chave)),
            )
        )

    return Opcoes(
        competencia_inicio=str(competencias.min()) if len(competencias) else None,
        competencia_fim=str(competencias.max()) if len(competencias) else None,
        municipios=_opcoes("municipio"),
        setores=_opcoes("setor"),
    )


__all__ = [
    "METRICAS",
    "Comparacao",
    "ConsultaError",
    "Dimensao",
    "DimensaoIndisponivel",
    "Filtro",
    "FiltroInvalido",
    "ItemComparado",
    "Metrica",
    "Opcao",
    "Opcoes",
    "PontoMensal",
    "Resumo",
    "Totais",
    "agrupar",
    "aplicar_filtro",
    "comparar",
    "opcoes_filtro",
    "serie_mensal",
    "totais",
]
