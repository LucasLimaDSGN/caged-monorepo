# CAGED

Monorepo para extracao de planilhas, manipulacao e analise de dados do CAGED,
com uma API para futuras pesquisas e comparacoes pelo frontend.

## Estrutura

```text
apps/
  backend/                 API FastAPI e seus testes
    src/caged_api/
    tests/
  frontend/                Painel React, TypeScript e Vite
packages/
  analytics/               Pacote Python compartilhado de dados e analises
    src/caged_analytics/
    tests/
data/
  raw/                     Arquivos originais, sem alteracoes
  processed/               Dados tratados e exportacoes
notebooks/                 Analises exploratorias
.github/workflows/          Validacao automatica
```

## Requisitos

- Python 3.11 ou superior.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) para dependencias
  e gerenciamento do workspace.

Execute os comandos abaixo na raiz do repositorio:

```powershell
python -m pip install --user uv
uv sync --all-packages
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

O arquivo `uv.lock` fixa as versoes resolvidas e deve ser versionado. Depois de
clonar o projeto, use `uv sync --all-packages --locked` para reproduzir o ambiente.
O ambiente virtual `.venv` e compartilhado pelos pacotes Python do workspace.

## Backend

```powershell
uv run uvicorn caged_api.main:app --reload --host 127.0.0.1 --port 8000
```

- API: http://127.0.0.1:8000
- Documentacao: http://127.0.0.1:8000/docs
- Verificacao de saude: http://127.0.0.1:8000/health

A API le a planilha oficial "Tabelas" do Novo CAGED (MTE). Coloque o arquivo em
`data/raw/` (o nome precisa conter `tabelas` e terminar em `.xlsx`) ou aponte para ele
com a variavel `CAGED_XLSX`. A planilha e lida uma unica vez, ao iniciar (cerca de
15 segundos). Sem a planilha, as rotas respondem 503.

| Rota (todas GET) | O que devolve |
|---|---|
| `/api/meta` | periodo disponivel, tipo de serie (com ajustes) e fonte |
| `/api/states` | UFs com sigla, nome e regiao |
| `/api/cities?state&q&limit` | municipios (codigo IBGE) |
| `/api/sectors` | os 5 grupamentos de setor |
| `/api/movements?start&end` + no maximo um entre `city`, `state`, `sector` | serie mensal e totais (sem filtro = Brasil) |
| `/api/ranking?start&end&level&metric&state&limit` | ranking por regiao, UF, municipio ou setor |
| `/api/compare?start&end&cities=310620,355030` | 2 a 5 municipios lado a lado |

Meses usam `YYYY-MM`. Parametro invalido responde 422 (mesmo formato do FastAPI) e
consulta sem dados responde 200 com lista vazia. A planilha **nao cruza municipio com
setor**, por isso as rotas aceitam um unico filtro por vez. O CORS libera
`http://localhost:5173` e `http://127.0.0.1:5173` (outras origens: `CAGED_CORS_ORIGINS`,
separadas por virgula). Com `CAGED_USE_FAKE=1` a API usa dados falsos, sem a planilha.
Nao ha upload HTTP, banco de dados ou autenticacao.

## Pacote de Dados

`caged-analytics` concentra a logica reutilizavel, sem depender de FastAPI.
Inclui pandas, matplotlib, openpyxl, xlrd e pyarrow para planilhas, analises,
graficos e armazenamento colunar. O backend depende desse pacote pelo workspace.

```python
from caged_analytics.ingestion import load_excel

frame = load_excel("data/raw/caged.xlsx")
print(frame.head())
```

O leitor carrega uma unica aba, por indice ou nome (`sheet_name=0` por padrao).
Ele ainda nao valida colunas, normaliza valores ou aplica regras do CAGED.
Planilhas grandes sao carregadas em memoria; a estrategia de processamento
devera ser definida a partir do volume real dos arquivos.

## Dados do CAGED

Consulte [data/README.md](data/README.md) antes de adicionar arquivos. Os dados
originais e processados ficam fora do Git por padrao. Para entrega pelo proprio
repositorio, configure Git LFS antes de liberar o versionamento dos originais.

## Frontend e Exploracao

O frontend usa React, TypeScript, Vite, React Router, TanStack Query, Recharts e
CSS Modules. Requer Node.js 24 LTS com npm. Execute na raiz:

```powershell
npm ci
npm run dev
```

Acesse http://127.0.0.1:5173 (ou a porta informada pelo Vite, se estiver ocupada).
O painel tem filtros de periodo, municipio e setor, graficos, comparacao entre
municipios, pesquisa na tabela e exportacao CSV. Os valores vem da API (dados oficiais
do Novo CAGED), entao **o backend precisa estar em execucao** (por padrao em
http://127.0.0.1:8000). Se a API usar outra porta, copie `apps/frontend/.env.example` para
`apps/frontend/.env.local` e ajuste `VITE_API_URL`.

Detalhes em [apps/frontend/README.md](apps/frontend/README.md). As dependencias
JavaScript sao gerenciadas pelo workspace npm da raiz e por `package-lock.json`.

`notebooks` recebe exploracoes; logica reutilizavel Python deve ir para
`packages/analytics`. Jupyter ainda nao e instalado.

## Validacao

A integracao continua executa os testes e o Ruff em Python 3.11 e 3.14.
Os testes criam planilhas temporarias e nao dependem dos arquivos reais do CAGED.
O job de frontend usa Node.js 24 e executa:

```powershell
npm test
npm run build
```

O build verifica os tipos TypeScript antes de gerar os arquivos em
`apps/frontend/dist`. Em hospedagens estaticas, configure o fallback de rotas
para `index.html`, permitindo acesso direto a `/comparar`.