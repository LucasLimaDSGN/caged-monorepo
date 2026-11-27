"""Fonte de dados REAL: a planilha "Tabelas" do Novo CAGED (via load_tabelas).

Carrega a planilha UMA vez (leva ~15 s) e responde as consultas com as funcoes
de caged_analytics.consultas (Davi). Para estado/regiao/Brasil usa a tabela `uf`
direto, porque as funcoes do Davi so conhecem municipio e setor.
"""

from pathlib import Path

import pandas as pd

from caged_analytics.consultas import Filtro, agrupar, serie_mensal
from caged_analytics.tabelas import TabelasResult, load_tabelas
from caged_api.data import _make_item, _plain, sum_totals
from caged_api.schemas import (
    City,
    CitySeries,
    Level,
    Meta,
    Metric,
    MonthlyItem,
    Period,
    RankingItem,
    Sector,
    State,
)

# Os 5 grupamentos de setor (nivel 1 da planilha, sem "Nao identificado").
SECTOR_CODES = ["SERV", "G", "IND", "F", "A"]
REGION_CODES = {"Norte": "N", "Nordeste": "NE", "Centro-Oeste": "CO", "Sudeste": "SE", "Sul": "S"}


class RealData:
    @classmethod
    def from_xlsx(cls, xlsx: Path) -> "RealData":
        return cls(load_tabelas(xlsx), str(xlsx))

    def __init__(self, res: TabelasResult, origin: str = "tabelas") -> None:
        self.issues = res.issues
        if res.municipio.empty or res.uf.empty or res.setor.empty:
            raise RuntimeError(f"planilha sem dados utilizaveis: {origin}")
        self.municipio = res.municipio[res.municipio["municipio_identificado"]]
        self.setor = res.setor
        self.uf = res.uf

        ufs = self.uf[self.uf["nivel"] == "uf"].drop_duplicates("uf")
        self.states = sorted(
            (State(code=r.uf, name=r.territorio, region=r.regiao) for r in ufs.itertuples()),
            key=lambda s: s.name,
        )
        cities = self.municipio.drop_duplicates("municipio_codigo")
        self.cities = sorted(
            (
                City(code=int(r.municipio_codigo), name=r.municipio, state=r.uf)
                for r in cities.itertuples()
            ),
            key=lambda c: c.name,
        )
        self.city_names = {c.code: c.name for c in self.cities}
        names = self.setor.drop_duplicates("setor_codigo").set_index("setor_codigo")["setor"]
        self.sectors = [Sector(code=c, name=names[c]) for c in SECTOR_CODES if c in names.index]
        self.period = Period(start=self.uf["competencia"].min(), end=self.uf["competencia"].max())

    # ----- catalogos -----

    def get_meta(self) -> Meta:
        return Meta(
            period=self.period,
            series="adjusted",
            source="Novo CAGED (MTE), planilha Tabelas, séries com ajustes",
        )

    def list_states(self) -> list[State]:
        return self.states

    def list_cities(self, state: str | None, q: str | None, limit: int) -> list[City]:
        found = [
            c
            for c in self.cities
            if (state is None or c.state == state) and (q is None or _plain(q) in _plain(c.name))
        ]
        return found[:limit]

    def list_sectors(self) -> list[Sector]:
        return self.sectors

    # ----- numeros -----

    def monthly_series(
        self,
        start: str,
        end: str,
        city: int | None = None,
        state: str | None = None,
        sector: str | None = None,
    ) -> list[MonthlyItem]:
        if city is not None:
            points = serie_mensal(self.municipio, Filtro(start, end, municipios=[str(city)]))
        elif sector is not None:
            points = serie_mensal(self.setor, Filtro(start, end, setores=[sector]))
        else:
            if state is None:
                rows = self.uf[self.uf["nivel"] == "brasil"]
            else:
                rows = self.uf[(self.uf["nivel"] == "uf") & (self.uf["uf"] == state)]
            points = serie_mensal(rows, Filtro(start, end))
        return [_item(p) for p in points]

    def ranking(
        self,
        start: str,
        end: str,
        level: Level,
        metric: Metric,
        state: str | None = None,
        limit: int = 10,
    ) -> list[RankingItem]:
        flt = Filtro(start, end)
        rows: list[RankingItem] = []
        if level == "city":
            df = self.municipio[self.municipio["uf"] == state]
            rows = [_ranking(int(r.chave), r.nome, r) for r in agrupar(df, "municipio", flt)]
        elif level == "sector":
            rows = [
                _ranking(r.chave, r.nome, r)
                for r in agrupar(self.setor, "setor", flt)
                if r.chave in SECTOR_CODES
            ]
        else:
            nivel = "uf" if level == "state" else "regiao"
            df = self.uf[self.uf["nivel"] == nivel]
            if state is not None and level == "state":
                df = df[df["uf"] == state]
            if state is not None and level == "region":
                region = next(s.region for s in self.states if s.code == state)
                df = df[df["regiao"] == region]
            df = df[(df["competencia"] >= start) & (df["competencia"] <= end)]
            sums = df.groupby("territorio")[["admissoes", "desligamentos", "saldo"]].sum()
            for name, r in sums.iterrows():
                code = REGION_CODES[name] if level == "region" else _uf_code(df, name)
                rows.append(
                    RankingItem(
                        code=code,
                        name=name,
                        admissions=int(r.admissoes),
                        dismissals=int(r.desligamentos),
                        balance=int(r.saldo),
                    )
                )
        rows.sort(key=lambda item: getattr(item, metric), reverse=True)
        return rows[:limit]

    def compare(self, cities: list[int], start: str, end: str) -> list[CitySeries]:
        result = []
        for code in cities:
            items = self.monthly_series(start, end, city=code)
            result.append(
                CitySeries(
                    code=code,
                    name=self.city_names[code],
                    items=items,
                    totals=_totals(items),
                )
            )
        return result


# ---------- auxiliares ----------


def _item(p) -> MonthlyItem:
    return _make_item(p.competencia, p.admissoes, p.desligamentos)


def _ranking(code, name, r) -> RankingItem:
    return RankingItem(
        code=code,
        name=name,
        admissions=r.admissoes,
        dismissals=r.desligamentos,
        balance=r.saldo,
    )


def _totals(items: list[MonthlyItem]):
    return sum_totals(items)


def _uf_code(df: pd.DataFrame, territorio: str) -> str:
    return str(df.loc[df["territorio"] == territorio, "uf"].iloc[0])
