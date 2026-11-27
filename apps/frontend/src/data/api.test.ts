import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchLabor } from './api';

const month = (m: string, admissions: number, dismissals: number) =>
  ({ month: m, admissions, dismissals, balance: admissions - dismissals });

function mockApi(routes: Record<string, unknown>) {
  const calls: string[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    calls.push(url);
    const path = new URL(url).pathname;
    return path in routes
      ? { ok: true, status: 200, json: async () => routes[path] }
      : { ok: false, status: 422, json: async () => ({}) };
  }));
  return calls;
}

const compare = { series: [
  { code: 350950, name: 'Campinas', items: [month('2025-01', 10, 4), month('2025-02', 12, 6)], totals: { admissions: 22, dismissals: 10, balance: 12 } },
  { code: 355030, name: 'Sao Paulo', items: [month('2025-01', 100, 90), month('2025-02', 120, 80)], totals: { admissions: 220, dismissals: 170, balance: 50 } },
] };
const ranking = { items: [
  { code: 'SERV', name: 'Servicos', admissions: 500, dismissals: 400, balance: 100 },
  { code: 'IND', name: 'Industria geral', admissions: 300, dismissals: 310, balance: -10 },
] };

afterEach(() => vi.unstubAllGlobals());

describe('fetchLabor', () => {
  it('soma os municipios por mes e usa nomes de setor do front', async () => {
    mockApi({ '/api/compare': compare, '/api/ranking': ranking });
    const data = await fetchLabor({ start: '2025-01', end: '2025-02', sector: 'all' }, ['Campinas', 'Sao Paulo']);
    expect(data.monthly).toEqual([
      { name: '2025-01', admissions: 110, dismissals: 94, balance: 16 },
      { name: '2025-02', admissions: 132, dismissals: 86, balance: 46 },
    ]);
    expect(data.byCity.map((row) => row.name)).toEqual(['Campinas', 'Sao Paulo']);
    expect(data.bySector.map((row) => row.name)).toEqual(['Servicos', 'Industria']);
  });

  it('com um municipio usa /movements (o /compare exige dois ou mais)', async () => {
    const calls = mockApi({
      '/api/movements': { items: [month('2025-01', 10, 4)], totals: { admissions: 10, dismissals: 4, balance: 6 } },
      '/api/ranking': ranking,
    });
    const data = await fetchLabor({ start: '2025-01', end: '2025-01', sector: 'all' }, ['Campinas']);
    expect(calls.some((url) => url.includes('/api/movements') && url.includes('city=350950'))).toBe(true);
    expect(data.byCity).toEqual([{ name: 'Campinas', admissions: 10, dismissals: 4, balance: 6 }]);
  });

  it('com setor escolhido, os indicadores passam a ser do setor e avisa', async () => {
    mockApi({
      '/api/compare': compare, '/api/ranking': ranking,
      '/api/movements': { items: [month('2025-01', 300, 310)], totals: { admissions: 300, dismissals: 310, balance: -10 } },
    });
    const data = await fetchLabor({ start: '2025-01', end: '2025-01', sector: 'Industria' }, ['Campinas', 'Sao Paulo']);
    expect(data.monthly).toEqual([{ name: '2025-01', admissions: 300, dismissals: 310, balance: -10 }]);
    expect(data.bySector.map((row) => row.name)).toEqual(['Industria']);
    expect(data.notice).toContain('nao cruza');
  });

  it('sem municipios selecionados nao chama a API de municipios', async () => {
    const calls = mockApi({ '/api/ranking': ranking });
    const data = await fetchLabor({ start: '2025-01', end: '2025-02', sector: 'all' }, []);
    expect(data.monthly).toEqual([]);
    expect(calls).toHaveLength(1);
  });

  it('propaga erro da API (ex.: 422)', async () => {
    mockApi({});
    await expect(fetchLabor({ start: '2019-01', end: '2019-02', sector: 'all' }, ['Campinas', 'Sao Paulo'])).rejects.toThrow('422');
  });
});
