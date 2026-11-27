import type { Filters, Summary } from './labor';

// Endereco da API. Em outro PC/porta: crie apps/frontend/.env.local com VITE_API_URL=...
const API_URL: string = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000';

// A API identifica municipios e setores por codigo; o front mostra nomes.
export const cityCodes: Record<string, number> = {
  Campinas: 350950, 'Sao Paulo': 355030, Santos: 354850, 'Ribeirao Preto': 354340,
};
export const sectorCodes: Record<string, string> = {
  Servicos: 'SERV', Comercio: 'G', Industria: 'IND', Construcao: 'F', Agropecuaria: 'A',
};
const sectorNames = Object.fromEntries(Object.entries(sectorCodes).map(([name, code]) => [code, name]));

interface Totals { admissions: number; dismissals: number; balance: number }
interface MonthlyItem extends Totals { month: string }
interface Movements { items: MonthlyItem[]; totals: Totals }
interface Compare { series: { code: number; name: string; items: MonthlyItem[]; totals: Totals }[] }
interface Ranking { items: (Totals & { code: string | number; name: string })[] }

export interface LaborData {
  monthly: Summary[]; // name = mes (YYYY-MM)
  byCity: Summary[];
  bySector: Summary[];
  notice: string | null;
}

async function get<T>(path: string, params: Record<string, string>, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_URL}${path}?${new URLSearchParams(params)}`, { signal });
  if (!response.ok) throw new Error(`API ${response.status} em ${path}`);
  return response.json() as Promise<T>;
}

const summary = (name: string, value: Totals): Summary => ({
  name, admissions: value.admissions, dismissals: value.dismissals, balance: value.balance,
});

export function sumTotals(rows: Summary[]): Omit<Summary, 'name'> {
  return rows.reduce((sum, row) => ({
    admissions: sum.admissions + row.admissions,
    dismissals: sum.dismissals + row.dismissals,
    balance: sum.balance + row.balance,
  }), { admissions: 0, dismissals: 0, balance: 0 });
}

function sumByMonth(series: MonthlyItem[][]): Summary[] {
  const months = new Map<string, Summary>();
  for (const item of series.flat()) {
    const row = months.get(item.month) ?? summary(item.month, { admissions: 0, dismissals: 0, balance: 0 });
    row.admissions += item.admissions;
    row.dismissals += item.dismissals;
    row.balance += item.balance;
    months.set(item.month, row);
  }
  return [...months.values()].sort((a, b) => a.name.localeCompare(b.name));
}

/**
 * Busca tudo que o painel precisa. A planilha do CAGED NAO cruza municipio com setor,
 * entao os dados por municipio e por setor vem de consultas separadas.
 */
export async function fetchLabor(
  filters: Pick<Filters, 'start' | 'end' | 'sector'>,
  cities: string[],
  signal?: AbortSignal,
): Promise<LaborData> {
  const period = { start: filters.start, end: filters.end };
  const codes = cities.map((city) => cityCodes[city]);

  const cityData = async (): Promise<{ monthly: Summary[]; byCity: Summary[] }> => {
    if (codes.length === 0) return { monthly: [], byCity: [] };
    if (codes.length === 1) { // /compare exige 2 a 5 municipios
      const one = await get<Movements>('/api/movements', { ...period, city: String(codes[0]) }, signal);
      return { monthly: one.items.map((i) => summary(i.month, i)), byCity: [summary(cities[0], one.totals)] };
    }
    const many = await get<Compare>('/api/compare', { ...period, cities: codes.join(',') }, signal);
    return {
      monthly: sumByMonth(many.series.map((s) => s.items)),
      byCity: many.series.map((s) => summary(s.name, s.totals)),
    };
  };

  const ranking = get<Ranking>('/api/ranking', { ...period, level: 'sector', limit: '10' }, signal);
  const [byCityResult, sectorRanking] = await Promise.all([cityData(), ranking]);

  let bySector = sectorRanking.items.map((item) => summary(sectorNames[item.code] ?? item.name, item));
  if (filters.sector === 'all') {
    return { ...byCityResult, bySector, notice: bySector.length ? 'Os setores mostram o Brasil inteiro: a planilha do CAGED nao cruza municipio com setor.' : null };
  }

  // Setor escolhido: totais e serie mensal passam a ser do setor, no Brasil.
  const only = await get<Movements>('/api/movements', { ...period, sector: sectorCodes[filters.sector] }, signal);
  bySector = bySector.filter((row) => row.name === filters.sector);
  return {
    monthly: only.items.map((i) => summary(i.month, i)),
    byCity: byCityResult.byCity,
    bySector,
    notice: 'Com um setor escolhido, indicadores e evolucao mensal sao do setor no Brasil inteiro (a planilha nao cruza municipio com setor). O grafico de municipios segue sem o filtro de setor.',
  };
}
