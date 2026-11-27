# Frontend

Painel React + TypeScript + Vite para consultas e comparacoes do CAGED.
Os dados vem da API do backend (Novo CAGED, series com ajustes). O painel mostra
quatro municipios de Sao Paulo e cinco setores economicos. A API precisa estar em
execucao: veja o README da raiz. Endereco em `VITE_API_URL` (`.env.example`).

## Execucao

Use Node.js 24 LTS. Na raiz do monorepo:

```powershell
npm ci
npm run dev
npm test
npm run build
```

O servidor local fica em http://127.0.0.1:5173, usando outra porta automaticamente
se necessario. Para escolher uma porta explicitamente:

```powershell
npm run dev --workspace @caged/frontend -- --port 5174
```

## Organizacao

- `src/main.tsx`: providers do TanStack Query e React Router.
- `src/App.tsx`: rotas `/` e `/comparar`, filtros, indicadores, graficos e tabelas.
- `src/App.module.css`: estilos responsivos e fontes locais.
- `src/data/api.ts`: cliente da API (`fetchLabor`); converte nomes em codigos e junta as respostas.
- `src/data/api.test.ts`: testes do cliente com `fetch` simulado.
- `src/data/labor.ts`: tipos, CSV e tendencia. `demoRecords` e `queryLabor` (dados
  simulados) nao sao mais usados pelo painel.
- `src/data/labor.test.ts`: testes de filtros, saldo, cancelamento e CSV.

Os filtros de periodo, municipio e setor ficam na URL. A selecao dos municipios
na comparacao, a pesquisa na tabela e o modo dos graficos ficam em memoria.
A exportacao CSV respeita os filtros e a pesquisa da tabela, com codificacao
UTF-8 e separador ponto e virgula.

## Integracao com a API

A planilha do CAGED nao cruza municipio com setor, entao o painel faz consultas
separadas: municipios via `/api/compare` (ou `/api/movements` para um so) e setores
via `/api/ranking?level=sector` (Brasil inteiro). Com um setor escolhido, indicadores
e evolucao mensal passam a ser do setor no Brasil, e o painel avisa isso na tela.
Municipios e setores sao mapeados de nome para codigo em `src/data/api.ts`.

A interface nao le as planilhas diretamente. Processamento e regras de negocio
ficam em `packages/analytics`, expostas pela API em `apps/backend`.

## Publicacao

O build gera `apps/frontend/dist`. Configure a hospedagem para servir
`index.html` nas rotas do cliente, incluindo `/comparar`. As fontes sao
empacotadas localmente; nao ha dependencia de servicos externos de fontes.