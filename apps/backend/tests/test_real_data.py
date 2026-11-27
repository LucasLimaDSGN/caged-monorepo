"""Testa a fonte REAL (RealData) com tabelas pequenas, de valores conhecidos.

Sem ler a planilha de verdade: montamos as tres tabelas de `load_tabelas` na mao, para
conferir a conta (e a integracao com as funcoes do Davi) com numeros faceis de somar.
"""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from caged_analytics.tabelas import TabelasResult
from caged_api.data import get_data
from caged_api.main import app
from caged_api.real_data import RealData

JAN, FEV = "2025-01", "2025-02"


def _df(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["saldo"] = df["admissoes"] - df["desligamentos"]
    df["estoque"] = 0
    return df


def _mun(uf, codigo, nome, jan, fev, identificado=True):
    return [
        {"competencia": mes, "uf": uf, "municipio_codigo": codigo, "municipio": nome,
         "municipio_identificado": identificado, "admissoes": a, "desligamentos": d}
        for mes, (a, d) in ((JAN, jan), (FEV, fev))
    ]  # fmt: skip


def _set(codigo, nome, nivel, pai, jan, fev):
    return [
        {"competencia": mes, "setor_codigo": codigo, "setor": nome, "setor_nivel": nivel,
         "setor_pai": pai, "admissoes": a, "desligamentos": d}
        for mes, (a, d) in ((JAN, jan), (FEV, fev))
    ]  # fmt: skip


def _uf(territorio, nivel, uf, regiao, jan, fev):
    return [
        {"competencia": mes, "territorio": territorio, "nivel": nivel, "uf": uf,
         "regiao": regiao, "admissoes": a, "desligamentos": d}
        for mes, (a, d) in ((JAN, jan), (FEV, fev))
    ]  # fmt: skip


@pytest.fixture(scope="module")
def data() -> RealData:
    municipio = _df(
        _mun("MG", "310620", "Belo Horizonte", (100, 90), (110, 120))  # saldo total 0
        + _mun("MG", "317020", "Uberlandia", (20, 5), (30, 10))  # saldo total 35
        + _mun("SP", "350950", "Campinas", (50, 40), (60, 50))  # saldo total 20
        + _mun("SP", "999999", "Nao identificado", (9, 9), (9, 9), identificado=False)
    )
    setor = _df(
        _set("TOTAL", "Total", 0, None, (170, 135), (200, 180))
        + _set("SERV", "Servicos", 1, "TOTAL", (80, 70), (90, 100))
        + _set("IND", "Industria geral", 1, "TOTAL", (50, 40), (60, 45))
        + _set("G", "Comercio", 1, "TOTAL", (20, 15), (30, 20))
        + _set("F", "Construcao", 1, "TOTAL", (10, 10), (10, 10))
        + _set("A", "Agropecuaria", 1, "TOTAL", (5, 5), (5, 5))
        + _set("NI", "Nao identificado", 1, "TOTAL", (5, 0), (5, 0))
        + _set("B", "Industrias Extrativas", 2, "IND", (7, 7), (7, 7))  # nivel 2: fora
    )
    uf = _df(
        _uf("Brasil", "brasil", None, None, (170, 135), (200, 180))
        + _uf("Sudeste", "regiao", None, "Sudeste", (170, 135), (200, 180))
        + _uf("Sul", "regiao", None, "Sul", (1, 1), (1, 1))
        + _uf("Minas Gerais", "uf", "MG", "Sudeste", (120, 95), (140, 130))
        + _uf("Sao Paulo", "uf", "SP", "Sudeste", (50, 40), (60, 50))
    )
    return RealData(TabelasResult(municipio, setor, uf))


@pytest.fixture
def client(data):
    app.dependency_overrides[get_data] = lambda: data
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------- catalogos ----------


def test_meta_periodo_vem_dos_dados(data):
    assert (data.get_meta().period.start, data.get_meta().period.end) == (JAN, FEV)


def test_estados_ordenados_com_regiao(data):
    assert [(s.code, s.region) for s in data.list_states()] == [
        ("MG", "Sudeste"),
        ("SP", "Sudeste"),
    ]


def test_cidades_ignoram_nao_identificado_e_buscam_sem_acento(data):
    assert [c.code for c in data.list_cities(None, None, 50)] == [310620, 350950, 317020]
    assert [c.name for c in data.list_cities("MG", "UBERL", 50)] == ["Uberlandia"]
    assert data.list_cities(None, None, 1)[0].name == "Belo Horizonte"


def test_setores_sao_os_cinco_grupamentos(data):
    assert [s.code for s in data.list_sectors()] == ["SERV", "G", "IND", "F", "A"]


# ---------- series ----------


def test_serie_do_municipio(data):
    items = data.monthly_series(JAN, FEV, city=310620)
    assert [(i.month, i.admissions, i.dismissals, i.balance) for i in items] == [
        (JAN, 100, 90, 10),
        (FEV, 110, 120, -10),
    ]


def test_serie_do_periodo_filtrado(data):
    assert [i.month for i in data.monthly_series(FEV, FEV, city=310620)] == [FEV]


def test_serie_do_estado_do_setor_e_do_brasil(data):
    assert [i.admissions for i in data.monthly_series(JAN, FEV, state="MG")] == [120, 140]
    assert [i.balance for i in data.monthly_series(JAN, FEV, sector="IND")] == [10, 15]
    assert [i.admissions for i in data.monthly_series(JAN, FEV)] == [170, 200]


# ---------- ranking ----------


def test_ranking_de_municipios_do_estado(data):
    by_balance = data.ranking(JAN, FEV, "city", "balance", state="MG")
    assert [(i.code, i.balance) for i in by_balance] == [(317020, 35), (310620, 0)]
    by_admissions = data.ranking(JAN, FEV, "city", "admissions", state="MG", limit=1)
    assert [i.code for i in by_admissions] == [310620]


def test_ranking_de_setores_ignora_ni_e_niveis_filhos(data):
    items = data.ranking(JAN, FEV, "sector", "admissions")
    assert [(i.code, i.admissions) for i in items] == [
        ("SERV", 170), ("IND", 110), ("G", 50), ("F", 20), ("A", 10),
    ]  # fmt: skip


def test_ranking_de_regioes_e_estados(data):
    regions = data.ranking(JAN, FEV, "region", "admissions")
    assert [(i.code, i.name, i.admissions) for i in regions] == [
        ("SE", "Sudeste", 370), ("S", "Sul", 2),
    ]  # fmt: skip
    states = data.ranking(JAN, FEV, "state", "balance")
    assert [(i.code, i.balance) for i in states] == [("MG", 35), ("SP", 20)]


def test_ranking_respeita_o_periodo(data):
    (first, *_) = data.ranking(JAN, JAN, "state", "admissions")
    assert (first.code, first.admissions) == ("MG", 120)


# ---------- comparacao ----------


def test_compare_devolve_serie_e_totais_por_municipio(data):
    bh, campinas = data.compare([310620, 350950], JAN, FEV)
    assert (bh.name, bh.totals.admissions, bh.totals.balance) == ("Belo Horizonte", 210, 0)
    assert (campinas.name, campinas.totals.balance, len(campinas.items)) == ("Campinas", 20, 2)


# ---------- de ponta a ponta (HTTP) ----------


def test_http_com_fonte_real(client):
    body = client.get(f"/api/ranking?start={JAN}&end={FEV}&level=city&state=MG").json()
    assert [item["name"] for item in body["items"]] == ["Belo Horizonte", "Uberlandia"]
    movements = client.get(f"/api/movements?start={JAN}&end={FEV}&city=310620").json()
    assert movements["totals"] == {"admissions": 210, "dismissals": 210, "balance": 0}
    # periodo fora do que os dados cobrem -> 422 (valida contra o meta real)
    assert client.get("/api/movements?start=2020-01&end=2020-02").status_code == 422
