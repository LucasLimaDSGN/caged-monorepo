"""Fonte de dados da API.

DataSource e o "acordo" com o Davi: a lista de funcoes que a API chama.
FakeData cumpre esse acordo com numeros inventados, para a API funcionar
antes das analises reais ficarem prontas. Quando ficarem, basta trocar
o que get_data() devolve; as rotas nao mudam.
"""

import os
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from fastapi import HTTPException

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
    Totals,
)


class DataSource(Protocol):
    def get_meta(self) -> Meta: ...

    def list_states(self) -> list[State]: ...

    def list_cities(self, state: str | None, q: str | None, limit: int) -> list[City]: ...

    def list_sectors(self) -> list[Sector]: ...

    def monthly_series(
        self,
        start: str,
        end: str,
        city: int | None = None,
        state: str | None = None,
        sector: str | None = None,
    ) -> list[MonthlyItem]: ...

    def ranking(
        self,
        start: str,
        end: str,
        level: Level,
        metric: Metric,
        state: str | None = None,
        limit: int = 10,
    ) -> list[RankingItem]: ...

    def compare(self, cities: list[int], start: str, end: str) -> list[CitySeries]: ...


# ---------- Funcoes auxiliares ----------


def sum_totals(items: list[MonthlyItem]) -> Totals:
    admissions = sum(item.admissions for item in items)
    dismissals = sum(item.dismissals for item in items)
    return Totals(admissions=admissions, dismissals=dismissals, balance=admissions - dismissals)


def _plain(text: str) -> str:
    """Tira acentos e maiusculas: 'São Paulo' -> 'sao paulo'."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()


def _make_item(month: str, admissions: int, dismissals: int) -> MonthlyItem:
    return MonthlyItem(
        month=month,
        admissions=admissions,
        dismissals=dismissals,
        balance=admissions - dismissals,
    )


# ---------- Dados falsos (NAO sao estatisticas oficiais) ----------

MONTHS = [f"2025-{number:02d}" for number in range(1, 13)]

REGION_CODES = {"Norte": "N", "Nordeste": "NE", "Centro-Oeste": "CO", "Sudeste": "SE", "Sul": "S"}

STATES = [
    State(code="BA", name="Bahia", region="Nordeste"),
    State(code="MG", name="Minas Gerais", region="Sudeste"),
    State(code="SP", name="São Paulo", region="Sudeste"),
]

CITIES = [
    City(code=310620, name="Belo Horizonte", state="MG"),
    City(code=317020, name="Uberlândia", state="MG"),
    City(code=350950, name="Campinas", state="SP"),
    City(code=355030, name="São Paulo", state="SP"),
    City(code=292740, name="Salvador", state="BA"),
]

SECTORS = [
    Sector(code="comercio", name="Comércio"),
    Sector(code="industria-geral", name="Indústria geral"),
    Sector(code="servicos", name="Serviços"),
]


def _fake_series(base: int, seed: int) -> list[MonthlyItem]:
    """Gera 12 meses com numeros sempre iguais (deterministicos)."""
    items = []
    for index, month in enumerate(MONTHS):
        admissions = base + base * index // 50 + (index * 7 + seed) % 13 * base // 100
        dismissals = admissions - base // 20 + (index * 5 + seed) % 11 * base // 100
        items.append(_make_item(month, admissions, dismissals))
    return items


class FakeData:
    def __init__(self) -> None:
        bases = {310620: 30000, 317020: 9000, 350950: 15000, 355030: 120000, 292740: 20000}
        self.by_city = {code: _fake_series(base, code % 17) for code, base in bases.items()}
        self.by_sector = {
            sector.code: _fake_series(base, seed)
            for seed, (sector, base) in enumerate(zip(SECTORS, [90000, 60000, 140000], strict=True))
        }

    # ----- catalogos -----

    def get_meta(self) -> Meta:
        return Meta(
            period=Period(start=MONTHS[0], end=MONTHS[-1]),
            series="adjusted",
            source="Dados falsos para desenvolvimento (não são estatísticas oficiais)",
        )

    def list_states(self) -> list[State]:
        return STATES

    def list_cities(self, state: str | None, q: str | None, limit: int) -> list[City]:
        found = [
            city
            for city in CITIES
            if (state is None or city.state == state)
            and (q is None or _plain(q) in _plain(city.name))
        ]
        return sorted(found, key=lambda city: city.name)[:limit]

    def list_sectors(self) -> list[Sector]:
        return SECTORS

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
            series = [self.by_city.get(city, [])]
        elif sector is not None:
            series = [self.by_sector.get(sector, [])]
        else:
            # Estado ou Brasil inteiro: soma os municipios mes a mes.
            series = [
                self.by_city[item.code] for item in CITIES if state is None or item.state == state
            ]
        return self._sum_by_month(series, start, end)

    def ranking(
        self,
        start: str,
        end: str,
        level: Level,
        metric: Metric,
        state: str | None = None,
        limit: int = 10,
    ) -> list[RankingItem]:
        groups: dict[int | str, tuple[str, list[list[MonthlyItem]]]] = {}
        if level == "sector":
            for sector in SECTORS:
                groups[sector.code] = (sector.name, [self.by_sector[sector.code]])
        else:
            state_by_code = {item.code: item for item in STATES}
            for city in CITIES:
                if state is not None and city.state != state:
                    continue
                if level == "city":
                    key, name = city.code, city.name
                elif level == "state":
                    key, name = city.state, state_by_code[city.state].name
                else:  # region
                    name = state_by_code[city.state].region
                    key = REGION_CODES[name]
                groups.setdefault(key, (name, []))[1].append(self.by_city[city.code])

        items = []
        for key, (name, series) in groups.items():
            totals = sum_totals(self._sum_by_month(series, start, end))
            items.append(RankingItem(code=key, name=name, **totals.model_dump()))
        items.sort(key=lambda item: getattr(item, metric), reverse=True)
        return items[:limit]

    def compare(self, cities: list[int], start: str, end: str) -> list[CitySeries]:
        names = {city.code: city.name for city in CITIES}
        result = []
        for code in cities:
            items = self._sum_by_month([self.by_city.get(code, [])], start, end)
            result.append(
                CitySeries(code=code, name=names[code], items=items, totals=sum_totals(items))
            )
        return result

    @staticmethod
    def _sum_by_month(series: list[list[MonthlyItem]], start: str, end: str) -> list[MonthlyItem]:
        sums: dict[str, list[int]] = {}
        for items in series:
            for item in items:
                if start <= item.month <= end:
                    month_sum = sums.setdefault(item.month, [0, 0])
                    month_sum[0] += item.admissions
                    month_sum[1] += item.dismissals
        return [_make_item(month, adm, dis) for month, (adm, dis) in sorted(sums.items())]


_FAKE_DATA = FakeData()


def xlsx_path() -> Path | None:
    """Planilha do CAGED: variavel CAGED_XLSX ou o primeiro *tabelas*.xlsx de data/raw."""
    if os.environ.get("CAGED_XLSX"):
        return Path(os.environ["CAGED_XLSX"])
    raw = Path(__file__).resolve().parents[4] / "data" / "raw"
    return next(iter(sorted(raw.glob("*tabelas*.xlsx"))), None)


@lru_cache(maxsize=1)
def _load_real(path: Path) -> DataSource:
    from caged_api.real_data import RealData  # import aqui: real_data importa este arquivo

    return RealData.from_xlsx(path)


def get_data() -> DataSource:
    """Ponto unico de troca. Real por padrao; CAGED_USE_FAKE=1 volta aos dados falsos."""
    if os.environ.get("CAGED_USE_FAKE") == "1":
        return _FAKE_DATA
    path = xlsx_path()
    if path is None or not path.is_file():
        raise HTTPException(
            status_code=503,
            detail="Planilha do CAGED não encontrada. Coloque-a em data/raw/ ou defina CAGED_XLSX.",
        )
    return _load_real(path)
