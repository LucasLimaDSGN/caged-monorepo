"""Contrato HTTP da API do CAGED.

Cada classe descreve um JSON que a API devolve. O FastAPI usa estes
modelos para conferir as respostas e para montar a pagina /docs.
"""

from typing import Literal

from pydantic import BaseModel, Field

# Valores aceitos nos parametros "level" e "metric" do /api/ranking.
Level = Literal["region", "state", "city", "sector"]
Metric = Literal["admissions", "dismissals", "balance"]

# Mes no formato YYYY-MM, com o mes entre 01 e 12.
MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


# ---------- Catalogos (alimentam os filtros do front) ----------


class Period(BaseModel):
    start: str = Field(pattern=MONTH_PATTERN, examples=["2020-01"])
    end: str = Field(pattern=MONTH_PATTERN, examples=["2026-08"])


class Meta(BaseModel):
    """Resposta de GET /api/meta."""

    period: Period
    series: Literal["adjusted", "unadjusted"]
    source: str


class State(BaseModel):
    """Item de GET /api/states."""

    code: str = Field(min_length=2, max_length=2, examples=["MG"])
    name: str = Field(examples=["Minas Gerais"])
    region: str = Field(examples=["Sudeste"])


class City(BaseModel):
    """Item de GET /api/cities."""

    code: int = Field(examples=[310620])
    name: str = Field(examples=["Belo Horizonte"])
    state: str = Field(examples=["MG"])


class Sector(BaseModel):
    """Item de GET /api/sectors."""

    code: str = Field(examples=["industria-geral"])
    name: str = Field(examples=["Industria geral"])


# ---------- Numeros (alimentam os graficos) ----------


class Totals(BaseModel):
    """Os tres numeros do CAGED. As outras classes herdam daqui."""

    admissions: int
    dismissals: int
    balance: int


class MonthlyItem(Totals):
    """Um mes da serie: month + admissions, dismissals, balance."""

    month: str = Field(pattern=MONTH_PATTERN, examples=["2025-01"])


class MovementFilters(BaseModel):
    """Filtros que a API entendeu (devolvidos junto com os dados)."""

    start: str
    end: str
    city: int | None = None
    state: str | None = None
    sector: str | None = None


class MovementsResponse(BaseModel):
    """Resposta de GET /api/movements."""

    filters: MovementFilters
    items: list[MonthlyItem]
    totals: Totals


class RankingItem(Totals):
    """Uma barra do ranking: mesmo formato do Summary do front."""

    code: int | str = Field(examples=["SE", "MG", 310620])
    name: str = Field(examples=["Sudeste"])


class RankingResponse(BaseModel):
    """Resposta de GET /api/ranking."""

    level: Level
    metric: Metric
    items: list[RankingItem]


class CitySeries(BaseModel):
    """A serie de um municipio dentro da comparacao."""

    code: int
    name: str
    items: list[MonthlyItem]
    totals: Totals


class CompareResponse(BaseModel):
    """Resposta de GET /api/compare."""

    series: list[CitySeries]
