"""Testes das consultas com um conjunto pequeno cujos totais foram somados a mao.

Admissoes/desligamentos por (municipio, setor, mes):

    Campinas (350950)  C : jan 100/80  fev 120/90  mar  80/100   -> 300/270  saldo 30
    Campinas (350950)  G : jan  50/40  fev  60/70  mar  70/50    -> 180/160  saldo 20
    Santos   (354850)  C : jan  30/20  fev  40/50  mar  50/30    -> 120/100  saldo 20
    Santos   (354850)  G : jan  10/15  fev  20/10  mar  30/20    ->  60/45   saldo 15

    Campinas 480/430 saldo 50 | Santos 180/145 saldo 35 | geral 660/575 saldo 85
    Setor C 420/370 saldo 50  | Setor G 240/205 saldo 35
    Por mes (geral): jan 190/155 (35)  fev 240/220 (20)  mar 230/200 (30)
"""

import pandas as pd
import pytest

from caged_analytics.consultas import (
    ConsultaError,
    DimensaoIndisponivel,
    Filtro,
    FiltroInvalido,
    PontoMensal,
    Totais,
    agrupar,
    aplicar_filtro,
    comparar,
    opcoes_filtro,
    serie_mensal,
    totais,
)
from caged_analytics.schema import CANONICAL_COLUMNS, SETORES

CAMPINAS, SANTOS = "350950", "354850"
_MUN = {CAMPINAS: "Campinas", SANTOS: "Santos"}
_DADOS = {  # (municipio, setor) -> [(admissoes, desligamentos)] para jan, fev, mar
    (CAMPINAS, "C"): [(100, 80), (120, 90), (80, 100)],
    (CAMPINAS, "G"): [(50, 40), (60, 70), (70, 50)],
    (SANTOS, "C"): [(30, 20), (40, 50), (50, 30)],
    (SANTOS, "G"): [(10, 15), (20, 10), (30, 20)],
}


@pytest.fixture
def df() -> pd.DataFrame:
    linhas = []
    for (cod, setor), meses in _DADOS.items():
        for mes, (adm, des) in enumerate(meses, start=1):
            nome = _MUN[cod]
            linhas.append(
                {
                    "competencia": f"2025-{mes:02d}",
                    "municipio_codigo": cod,
                    "municipio": nome,
                    "municipio_chave": nome.upper(),
                    "uf": "SP",
                    "setor_codigo": setor,
                    "setor": SETORES[setor],
                    "admissoes": adm,
                    "desligamentos": des,
                    "saldo": adm - des,
                }
            )
    frame = pd.DataFrame(linhas, columns=list(CANONICAL_COLUMNS))
    return frame.astype({c: "Int64" for c in ("admissoes", "desligamentos", "saldo")})


# --- filtros -------------------------------------------------------------------
def test_sem_filtro_soma_tudo(df):
    assert totais(df) == Totais(660, 575, 85)


def test_filtro_por_periodo_e_inclusivo(df):
    assert totais(df, Filtro(inicio="2025-02", fim="2025-03")) == Totais(470, 420, 50)
    assert totais(df, Filtro(inicio="2025-02", fim="2025-02")) == Totais(240, 220, 20)
    assert totais(df, Filtro(fim="2025-01")) == Totais(190, 155, 35)


def test_filtro_por_municipio_aceita_codigo_codigo_ibge_7_digitos_e_nome(df):
    esperado = Totais(480, 430, 50)
    assert totais(df, Filtro(municipios=[CAMPINAS])) == esperado
    assert totais(df, Filtro(municipios=["3509502"])) == esperado  # IBGE com digito verificador
    assert totais(df, Filtro(municipios=["campinas"])) == esperado
    assert totais(df, Filtro(municipios=["  CAMPINAS "])) == esperado
    assert totais(df, Filtro(municipios="Campinas")) == esperado  # str solta, nao letras


def test_filtro_por_nome_ignora_acentos(df):
    df.loc[df["municipio_codigo"] == SANTOS, ["municipio", "municipio_chave"]] = [
        "São Vicente",
        "SAO VICENTE",
    ]
    assert totais(df, Filtro(municipios=["Sao Vicente"])).saldo == 35
    assert totais(df, Filtro(municipios=["São Vicente"])).saldo == 35


def test_filtro_por_setor_aceita_secao_nome_e_divisao_cnae(df):
    esperado = Totais(420, 370, 50)
    assert totais(df, Filtro(setores=["C"])) == esperado
    assert totais(df, Filtro(setores=["c"])) == esperado
    assert totais(df, Filtro(setores=[SETORES["C"]])) == esperado
    assert totais(df, Filtro(setores=["10"])) == esperado  # divisao 10 -> secao C


def test_varios_itens_sao_um_ou(df):
    assert totais(df, Filtro(setores=["C", "G"])) == Totais(660, 575, 85)
    assert totais(df, Filtro(municipios=[CAMPINAS, SANTOS])) == Totais(660, 575, 85)


def test_filtros_combinados(df):
    filtro = Filtro(inicio="2025-02", fim="2025-03", municipios=["Campinas"], setores=["C"])
    assert totais(df, filtro) == Totais(200, 190, 10)
    assert len(aplicar_filtro(df, filtro)) == 2


def test_recorte_vazio_devolve_zeros_sem_inventar_dados(df):
    filtro = Filtro(inicio="2026-01", fim="2026-12")
    assert totais(df, filtro) == Totais(0, 0, 0)
    assert serie_mensal(df, filtro) == []
    assert agrupar(df, "municipio", filtro) == []
    assert totais(df, Filtro(municipios=["Inexistente"])) == Totais(0, 0, 0)


def test_saldo_sempre_igual_a_admissoes_menos_desligamentos(df):
    for filtro in (Filtro(), Filtro(setores=["G"]), Filtro(municipios=[SANTOS], inicio="2025-02")):
        t = totais(df, filtro)
        assert t.saldo == t.admissoes - t.desligamentos


@pytest.mark.parametrize(
    "kwargs",
    [
        {"inicio": "2025-13"},
        {"inicio": "abc"},
        {"inicio": "2025-03", "fim": "2025-01"},
        {"municipios": [""]},
        {"municipios": ["12345"]},  # numero que nao e codigo IBGE
        {"setores": ["ZZZ desconhecido"]},
    ],
)
def test_filtro_invalido(kwargs):
    with pytest.raises(FiltroInvalido):
        Filtro(**kwargs)


# --- serie mensal --------------------------------------------------------------
def test_serie_mensal_geral(df):
    assert serie_mensal(df) == [
        PontoMensal("2025-01", 190, 155, 35),
        PontoMensal("2025-02", 240, 220, 20),
        PontoMensal("2025-03", 230, 200, 30),
    ]


def test_serie_mensal_filtrada_e_soma_bate_com_totais(df):
    filtro = Filtro(municipios=["Campinas"])
    serie = serie_mensal(df, filtro)
    assert [(p.competencia, p.saldo) for p in serie] == [
        ("2025-01", 30),
        ("2025-02", 20),
        ("2025-03", 0),
    ]
    assert sum(p.admissoes for p in serie) == totais(df, filtro).admissoes == 480


def test_serie_mensal_nao_preenche_lacunas_por_padrao(df):
    sem_fev = df[df["competencia"] != "2025-02"]
    assert [p.competencia for p in serie_mensal(sem_fev)] == ["2025-01", "2025-03"]


def test_serie_mensal_preenche_lacunas_so_quando_pedido(df):
    sem_fev = df[df["competencia"] != "2025-02"]
    serie = serie_mensal(sem_fev, preencher_lacunas=True)
    assert serie[1] == PontoMensal("2025-02", 0, 0, 0)
    assert len(serie) == 3
    # usa o inicio/fim do filtro quando informados
    estendida = serie_mensal(df, Filtro(inicio="2024-12", fim="2025-04"), preencher_lacunas=True)
    assert [p.competencia for p in estendida] == [
        "2024-12",
        "2025-01",
        "2025-02",
        "2025-03",
        "2025-04",
    ]


# --- agrupamento ---------------------------------------------------------------
def test_agrupar_por_municipio(df):
    resultado = agrupar(df, "municipio")
    assert [(r.chave, r.nome, r.admissoes, r.desligamentos, r.saldo) for r in resultado] == [
        (CAMPINAS, "Campinas", 480, 430, 50),
        (SANTOS, "Santos", 180, 145, 35),
    ]


def test_agrupar_por_setor_respeita_filtro(df):
    assert [(r.chave, r.saldo) for r in agrupar(df, "setor")] == [("C", 50), ("G", 35)]
    so_santos = agrupar(df, "setor", Filtro(municipios=[SANTOS]))
    assert [(r.chave, r.admissoes, r.desligamentos, r.saldo) for r in so_santos] == [
        ("C", 120, 100, 20),
        ("G", 60, 45, 15),
    ]


@pytest.mark.parametrize("por", ["municipio", "setor"])
def test_soma_dos_grupos_e_igual_ao_total(df, por):
    filtro = Filtro(inicio="2025-01", fim="2025-02")
    grupos = agrupar(df, por, filtro)
    total = totais(df, filtro)
    assert sum(g.admissoes for g in grupos) == total.admissoes
    assert sum(g.desligamentos for g in grupos) == total.desligamentos
    assert sum(g.saldo for g in grupos) == total.saldo


# --- comparacao ----------------------------------------------------------------
def test_comparar_municipios_ordena_por_saldo_e_traz_serie(df):
    r = comparar(df, "municipio", [SANTOS, "Campinas"])
    assert [i.nome for i in r.itens] == ["Campinas", "Santos"]  # saldo 50 > 35
    campinas, santos = r.itens
    assert campinas.totais == Totais(480, 430, 50)
    assert santos.totais == Totais(180, 145, 35)
    assert campinas.participacao_admissoes == pytest.approx(480 / 660)
    assert santos.participacao_admissoes == pytest.approx(180 / 660)
    assert [p.saldo for p in santos.serie] == [5, 0, 30]
    assert r.total == Totais(660, 575, 85)
    assert r.sem_dados == ()


def test_comparar_respeita_periodo_e_a_ordem_muda(df):
    r = comparar(df, "municipio", filtro=Filtro(inicio="2025-03", fim="2025-03"))
    assert [(i.nome, i.totais.saldo) for i in r.itens] == [("Santos", 30), ("Campinas", 0)]


def test_comparar_por_outra_metrica(df):
    r = comparar(df, "municipio", metrica="desligamentos")
    assert [(i.nome, i.totais.desligamentos) for i in r.itens] == [
        ("Campinas", 430),
        ("Santos", 145),
    ]


def test_comparar_setores_dentro_de_um_municipio(df):
    r = comparar(df, "setor", filtro=Filtro(municipios=[CAMPINAS]))
    assert [(i.chave, i.totais) for i in r.itens] == [
        ("C", Totais(300, 270, 30)),
        ("G", Totais(180, 160, 20)),
    ]


def test_comparar_informa_itens_sem_dados(df):
    r = comparar(df, "municipio", [CAMPINAS, "999999", "Atlantida"])
    assert [i.chave for i in r.itens] == [CAMPINAS]
    assert r.sem_dados == ("999999", "ATLANTIDA")


def test_comparar_recorte_vazio(df):
    r = comparar(df, "setor", filtro=Filtro(inicio="2030-01"))
    assert r.itens == () and r.total == Totais(0, 0, 0)


def test_comparar_participacao_none_sem_admissoes(df):
    df["admissoes"] = pd.array([0] * len(df), dtype="Int64")
    df["saldo"] = -df["desligamentos"]
    assert all(i.participacao_admissoes is None for i in comparar(df, "setor").itens)


def test_comparar_rejeita_parametros_invalidos(df):
    with pytest.raises(ConsultaError):
        comparar(df, "uf")  # type: ignore[arg-type]
    with pytest.raises(ConsultaError):
        comparar(df, "setor", metrica="estoque")  # type: ignore[arg-type]


# --- bases sem uma das dimensoes (planilha oficial "Tabelas") -------------------
def test_dimensao_ausente_levanta_erro_claro(df):
    so_setor = df.drop(columns=["municipio_codigo", "municipio", "municipio_chave"])
    assert totais(so_setor, Filtro(setores=["C"])).saldo == 50
    with pytest.raises(DimensaoIndisponivel):
        totais(so_setor, Filtro(municipios=["Campinas"]))
    with pytest.raises(DimensaoIndisponivel):
        agrupar(so_setor, "municipio")


def test_tabela_de_setor_hierarquica_nao_conta_em_dobro():
    # TOTAL = A + IND + F ; IND = B + C (somar todas as linhas contaria o dobro)
    linhas = [
        ("TOTAL", 0, 100),
        ("A", 1, 10),
        ("IND", 1, 60),
        ("B", 2, 20),
        ("C", 2, 40),
        ("F", 1, 30),
    ]
    tabela = pd.DataFrame(
        {
            "competencia": "2025-01",
            "setor_codigo": [c for c, _, _ in linhas],
            "setor": [c for c, _, _ in linhas],
            "setor_nivel": pd.array([n for _, n, _ in linhas], dtype="Int64"),
            "admissoes": pd.array([v for _, _, v in linhas], dtype="Int64"),
            "desligamentos": pd.array([0] * len(linhas), dtype="Int64"),
            "saldo": pd.array([v for _, _, v in linhas], dtype="Int64"),
        }
    )
    assert totais(tabela).admissoes == 100  # nivel 1: 10 + 60 + 30
    assert [r.chave for r in agrupar(tabela, "setor")] == ["A", "F", "IND"]
    assert totais(tabela, Filtro(setores=["C"])).admissoes == 40  # filtro explicito alcanca nivel 2
    assert totais(tabela, Filtro(setores=["TOTAL"])).admissoes == 100


# --- opcoes --------------------------------------------------------------------
def test_opcoes_filtro(df):
    o = opcoes_filtro(df)
    assert (o.competencia_inicio, o.competencia_fim) == ("2025-01", "2025-03")
    assert [(m.chave, m.nome) for m in o.municipios] == [(CAMPINAS, "Campinas"), (SANTOS, "Santos")]
    assert [s.chave for s in o.setores] == ["C", "G"]


def test_opcoes_filtro_base_vazia():
    from caged_analytics.pipeline import empty_frame

    o = opcoes_filtro(empty_frame())
    assert o.competencia_inicio is None and o.municipios == () and o.setores == ()
