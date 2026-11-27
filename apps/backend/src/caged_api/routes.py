"""Rotas da API do CAGED (contrato: GET /api/...).

Cada rota so faz tres coisas: valida os parametros, chama a fonte de
dados (DataSource) e devolve o resultado no formato do schemas.py.
Nenhuma conta e feita aqui.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from caged_api.data import DataSource, get_data, sum_totals
from caged_api.schemas import (
    MONTH_PATTERN,
    City,
    CompareResponse,
    Level,
    Meta,
    Metric,
    MovementFilters,
    MovementsResponse,
    RankingResponse,
    Sector,
    State,
)

router = APIRouter(prefix="/api", tags=["caged"])

# Tipos reaproveitados nas rotas.
Data = Annotated[DataSource, Depends(get_data)]
Month = Annotated[str, Query(pattern=MONTH_PATTERN, examples=["2025-01"])]
StateCode = Annotated[str | None, Query(pattern=r"^[A-Z]{2}$", examples=["MG"])]


# ---------- Validacoes que o FastAPI nao faz sozinho ----------


def invalid(param: str, message: str) -> HTTPException:
    """Erro 422 no mesmo formato da validacao automatica do FastAPI."""
    return HTTPException(
        status_code=422,
        detail=[{"loc": ["query", param], "msg": message, "type": "value_error"}],
    )


def check_period(data: DataSource, start: str, end: str) -> None:
    if start > end:
        raise invalid("start", "start deve ser anterior ou igual a end")
    period = data.get_meta().period
    if start < period.start or end > period.end:
        raise invalid("start", f"período disponível: {period.start} a {period.end}")


def check_state(data: DataSource, state: str | None) -> None:
    if state is not None and state not in {item.code for item in data.list_states()}:
        raise invalid("state", f"UF desconhecida: {state}")


def check_city(data: DataSource, city: int, param: str = "city") -> None:
    known = {item.code for item in data.list_cities(state=None, q=None, limit=10_000)}
    if city not in known:
        raise invalid(param, f"município desconhecido: {city}")


def check_sector(data: DataSource, sector: str | None) -> None:
    if sector is not None and sector not in {item.code for item in data.list_sectors()}:
        raise invalid("sector", f"setor desconhecido: {sector}")


# ---------- Catalogos ----------


@router.get("/meta")
def get_meta(data: Data) -> Meta:
    return data.get_meta()


@router.get("/states")
def list_states(data: Data) -> list[State]:
    return data.list_states()


@router.get("/cities")
def list_cities(
    data: Data,
    state: StateCode = None,
    q: Annotated[str | None, Query(min_length=2, max_length=60)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[City]:
    check_state(data, state)
    return data.list_cities(state=state, q=q, limit=limit)


@router.get("/sectors")
def list_sectors(data: Data) -> list[Sector]:
    return data.list_sectors()


# ---------- Numeros ----------


@router.get("/movements")
def get_movements(
    data: Data,
    start: Month,
    end: Month,
    city: int | None = None,
    state: StateCode = None,
    sector: str | None = None,
) -> MovementsResponse:
    check_period(data, start, end)
    if sum(value is not None for value in (city, state, sector)) > 1:
        raise invalid("city", "use no máximo um filtro entre city, state e sector")
    if city is not None:
        check_city(data, city)
    check_state(data, state)
    check_sector(data, sector)

    items = data.monthly_series(start, end, city=city, state=state, sector=sector)
    return MovementsResponse(
        filters=MovementFilters(start=start, end=end, city=city, state=state, sector=sector),
        items=items,
        totals=sum_totals(items),
    )


@router.get("/ranking")
def get_ranking(
    data: Data,
    start: Month,
    end: Month,
    level: Level = "region",
    metric: Metric = "admissions",
    state: StateCode = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 10,
) -> RankingResponse:
    check_period(data, start, end)
    check_state(data, state)
    if level == "city" and state is None:
        raise invalid("state", "level=city exige o parâmetro state")
    if level == "sector" and state is not None:
        raise invalid("state", "level=sector só existe para o Brasil; remova state")

    items = data.ranking(start, end, level=level, metric=metric, state=state, limit=limit)
    return RankingResponse(level=level, metric=metric, items=items)


@router.get("/compare")
def compare_cities(
    data: Data,
    start: Month,
    end: Month,
    cities: Annotated[str, Query(examples=["310620,355030"])],
) -> CompareResponse:
    check_period(data, start, end)
    parts = [part.strip() for part in cities.split(",")]
    if not all(part.isdigit() for part in parts):
        raise invalid("cities", "use códigos de município separados por vírgula")
    codes = [int(part) for part in parts]
    if len(set(codes)) != len(codes):
        raise invalid("cities", "há municípios repetidos")
    if not 2 <= len(codes) <= 5:
        raise invalid("cities", "compare de 2 a 5 municípios")
    for code in codes:
        check_city(data, code, param="cities")

    return CompareResponse(series=data.compare(codes, start, end))
