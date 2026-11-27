"""Testes da API. Trocam a fonte de dados (get_data) por uma falsa: rapidos e sem planilha."""

import pytest
from fastapi.testclient import TestClient

from caged_api.data import FakeData, get_data
from caged_api.main import app

PERIOD = "start=2025-01&end=2025-03"


class EmptyData(FakeData):
    """Fonte valida, mas sem nenhum numero (o catalogo continua existindo)."""

    def monthly_series(self, *args, **kwargs):
        return []

    def ranking(self, *args, **kwargs):
        return []

    def compare(self, cities, start, end):
        return []


@pytest.fixture
def client():
    app.dependency_overrides[get_data] = FakeData
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------- sucesso ----------


def test_catalogos(client):
    assert client.get("/api/meta").json()["period"] == {"start": "2025-01", "end": "2025-12"}
    assert {s["code"] for s in client.get("/api/states").json()} >= {"MG", "SP"}
    assert client.get("/api/cities?state=MG&q=belo").json() == [
        {"code": 310620, "name": "Belo Horizonte", "state": "MG"}
    ]
    assert client.get("/api/sectors").json()


def test_movements_brasil_e_municipio(client):
    brasil = client.get(f"/api/movements?{PERIOD}").json()
    cidade = client.get(f"/api/movements?{PERIOD}&city=310620").json()
    assert len(brasil["items"]) == 3
    assert (
        brasil["totals"]["balance"]
        == brasil["totals"]["admissions"] - brasil["totals"]["dismissals"]
    )
    assert cidade["filters"]["city"] == 310620
    assert cidade["totals"]["admissions"] < brasil["totals"]["admissions"]


def test_ranking_ordenado(client):
    items = client.get(f"/api/ranking?{PERIOD}&level=state&metric=admissions").json()["items"]
    values = [item["admissions"] for item in items]
    assert values == sorted(values, reverse=True)


def test_compare(client):
    body = client.get(f"/api/compare?{PERIOD}&cities=310620,355030").json()
    assert [s["code"] for s in body["series"]] == [310620, 355030]


# ---------- parametro invalido (422 no formato do FastAPI) ----------


@pytest.mark.parametrize(
    "url",
    [
        "/api/movements?start=2025-13&end=2025-03",  # mes inexistente
        "/api/movements?start=2025-03&end=2025-01",  # inicio depois do fim
        "/api/movements?start=2020-01&end=2025-03",  # fora do periodo
        f"/api/movements?{PERIOD}&city=310620&state=MG",  # dois filtros
        f"/api/movements?{PERIOD}&state=XX",  # UF desconhecida
        f"/api/movements?{PERIOD}&city=1",  # municipio desconhecido
        f"/api/movements?{PERIOD}&sector=nada",  # setor desconhecido
        f"/api/ranking?{PERIOD}&level=city",  # city exige state
        f"/api/ranking?{PERIOD}&level=sector&state=MG",  # sector nao aceita state
        f"/api/ranking?{PERIOD}&metric=lucro",  # metrica invalida
        f"/api/compare?{PERIOD}&cities=310620",  # menos de 2
        f"/api/compare?{PERIOD}&cities=310620,abc",  # nao numerico
        f"/api/compare?{PERIOD}&cities=310620,310620",  # repetido
        "/api/cities?q=a",  # busca curta demais
    ],
)
def test_parametro_invalido(client, url):
    response = client.get(url)
    assert response.status_code == 422
    assert {"loc", "msg", "type"} <= set(response.json()["detail"][0])


# ---------- sem dados ----------


def test_sem_dados_devolve_200_com_lista_vazia():
    app.dependency_overrides[get_data] = EmptyData
    try:
        client = TestClient(app)
        movements = client.get(f"/api/movements?{PERIOD}").json()
        assert movements["items"] == []
        assert movements["totals"] == {"admissions": 0, "dismissals": 0, "balance": 0}
        assert client.get(f"/api/ranking?{PERIOD}").json()["items"] == []
        assert client.get(f"/api/compare?{PERIOD}&cities=310620,355030").json()["series"] == []
    finally:
        app.dependency_overrides.clear()


def test_planilha_ausente_devolve_503(monkeypatch, tmp_path):
    monkeypatch.delenv("CAGED_USE_FAKE")
    monkeypatch.setenv("CAGED_XLSX", str(tmp_path / "nao-existe.xlsx"))
    response = TestClient(app).get("/api/meta")
    assert response.status_code == 503


def test_cors_libera_o_front(client):
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
