import { useDeferredValue, useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { NavLink, Navigate, Route, Routes, useSearchParams } from 'react-router';
import {
  ArrowDownRight, ArrowDownToLine, ArrowRightLeft, ArrowUpRight, ChevronDown,
  ChevronRight, Database, ExternalLink, Info, LayoutDashboard, LogOut, Menu, Minus,
  SlidersHorizontal, RotateCcw, Search, UserRound, X,
} from 'lucide-react';
import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import {
  cities, comparePeriodTrend, defaultFilters, sectors, toCsv,
  type Filters, type Summary,
} from './data/labor';
import { fetchLabor, sumTotals } from './data/api';
import styles from './App.module.css';

const number = new Intl.NumberFormat('pt-BR');
const compact = new Intl.NumberFormat('pt-BR', { notation: 'compact', maximumFractionDigits: 1 });
const percentage = new Intl.NumberFormat('pt-BR', { style: 'percent', maximumFractionDigits: 1 });
const monthFormat = new Intl.DateTimeFormat('pt-BR', { month: 'short', timeZone: 'UTC' });
const monthLabel = (month: string) => monthFormat.format(new Date(`${month}-01T00:00:00Z`)).replace('.', '');
const signed = (value: number) => `${value > 0 ? '+' : ''}${number.format(value)}`;

function exportRows(rows: Summary[]) {
  const url = URL.createObjectURL(new Blob([toCsv(rows)], { type: 'text/csv;charset=utf-8;' }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = 'caged-demonstrativo.csv';
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function Dashboard({ comparison = false }: { comparison?: boolean }) {
  const [params, setParams] = useSearchParams();
  const [mobileMenu, setMobileMenu] = useState(false);
  const [accountPanel, setAccountPanel] = useState<'profile' | 'logout' | null>(null);
  const [filterOpen, setFilterOpen] = useState(false);
  const [metric, setMetric] = useState<'balance' | 'movement'>('balance');
  const [dimension, setDimension] = useState<'city' | 'sector'>('city');
  const [search, setSearch] = useState('');
  const [selectedCities, setSelectedCities] = useState<string[]>(['Campinas', 'Sao Paulo']);
  const [filterDraft, setFilterDraft] = useState<Filters>(defaultFilters);
  const [cityDraft, setCityDraft] = useState<string[]>(['Campinas', 'Sao Paulo']);
  const filterDialogRef = useRef<HTMLDialogElement>(null);
  const deferredSearch = useDeferredValue(search);
  const filters: Filters = {
    start: params.get('start') || defaultFilters.start,
    end: params.get('end') || defaultFilters.end,
    city: comparison ? 'all' : params.get('city') || 'all',
    sector: params.get('sector') || 'all',
  };
  const validMonth = /^\d{4}-(0[1-9]|1[0-2])$/;
  const invalidPeriod = !validMonth.test(filters.start) || !validMonth.test(filters.end)
    || filters.start > filters.end;
  const cityList = comparison ? selectedCities : filters.city === 'all' ? [...cities] : [filters.city];
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ['labor', filters.start, filters.end, filters.sector, cityList],
    queryFn: ({ signal }) => fetchLabor(filters, cityList, signal),
    enabled: !invalidPeriod,
  });
  const monthly = data?.monthly ?? [];
  const total = sumTotals(monthly);
  const byCity = [...(data?.byCity ?? [])].sort((first, second) => second.balance - first.balance);
  const bySector = [...(data?.bySector ?? [])].sort((first, second) => second.balance - first.balance);
  const grouped = (comparison || dimension === 'city' ? byCity : bySector);
  const tableRows = grouped.filter((row) => row.name.toLocaleLowerCase('pt-BR')
    .includes(deferredSearch.toLocaleLowerCase('pt-BR')));
  const period = `${monthLabel(filters.start.match(validMonth) ? filters.start : '2025-01')}/${filters.start.slice(0, 4)} a ${monthLabel(filters.end.match(validMonth) ? filters.end : '2025-12')}/${filters.end.slice(0, 4)}`;
  const citySummary = comparison
    ? selectedCities.length === cities.length ? 'Todos os municipios' : `${selectedCities.length} municipios`
    : filters.city === 'all' ? 'Todos os municipios' : filters.city;
  const sectorSummary = filters.sector === 'all' ? 'Todos os setores' : filters.sector;

  function trendChip(metricName: 'balance' | 'admissions' | 'dismissals') {
    const trend = comparePeriodTrend(monthly, metricName);
    if (!trend) {
      return <span className={`${styles.trendChip} ${styles.trendUnavailable}`} title="Sem duas competencias comparaveis" aria-label="Sem duas competencias comparaveis">—</span>;
    }

    const label = `${trend.direction === 'up' ? 'Aumento' : trend.direction === 'down' ? 'Queda' : 'Sem variacao'} de ${percentage.format(trend.percentage)} entre ${monthLabel(trend.start)}/${trend.start.slice(0, 4)} e ${monthLabel(trend.end)}/${trend.end.slice(0, 4)}`;
    const TrendIcon = trend.direction === 'up' ? ArrowUpRight : trend.direction === 'down' ? ArrowDownRight : Minus;
    const tone = trend.direction === 'up' ? styles.trendUp : trend.direction === 'down' ? styles.trendDown : styles.trendFlat;
    return <span className={`${styles.trendChip} ${tone}`} title={label} aria-label={label}><TrendIcon size={12} aria-hidden="true" />{percentage.format(trend.percentage)}</span>;
  }

  useEffect(() => {
    const dialog = filterDialogRef.current;
    if (filterOpen && dialog && !dialog.open) dialog.showModal();
  }, [filterOpen]);

  function openFilters() {
    setFilterDraft(filters);
    setCityDraft(selectedCities);
    setFilterOpen(true);
  }

  function applyFilters() {
    const next = new URLSearchParams(params);
    for (const key of ['start', 'end', 'city', 'sector'] as const) {
      const value = filterDraft[key];
      if (value && value !== 'all') next.set(key, value);
      else next.delete(key);
    }
    setParams(next, { replace: true });
    if (comparison) setSelectedCities(cityDraft);
    setFilterOpen(false);
  }

  return (
    <div className={styles.app}>
      {mobileMenu && <button className={styles.scrim} aria-label="Fechar navegacao" onClick={() => setMobileMenu(false)} />}
      <aside className={`${styles.sidebar} ${mobileMenu ? styles.sidebarOpen : ''}`}>
        <div className={styles.brand} aria-label="CAGED">CAGED</div>
        <nav className={styles.railNav} aria-label="Navegacao principal">
          <NavLink end title="Visao geral" aria-label="Visao geral" to={{ pathname: '/', search: params.toString() }} onClick={() => setMobileMenu(false)} className={({ isActive }) => `${styles.navLink} ${isActive ? styles.active : ''}`}><LayoutDashboard size={19} /><span>Visao geral</span></NavLink>
          <NavLink title="Comparar municipios" aria-label="Comparar municipios" to={{ pathname: '/comparar', search: params.toString() }} onClick={() => setMobileMenu(false)} className={({ isActive }) => `${styles.navLink} ${isActive ? styles.active : ''}`}><ArrowRightLeft size={19} /><span>Comparar municipios</span></NavLink>
          <a className={styles.navLink} title="Fonte oficial do CAGED" aria-label="Fonte oficial do CAGED" href="https://www.gov.br/trabalho-e-emprego/pt-br/assuntos/estatisticas-trabalho/novo-caged" target="_blank" rel="noreferrer"><ExternalLink size={18} /><span>Fonte oficial</span></a>
          <button className={styles.navLink} type="button" title="Exportar CSV" aria-label="Exportar CSV" onClick={() => exportRows(tableRows)} disabled={!tableRows.length || invalidPeriod || isError}><ArrowDownToLine size={18} /><span>Exportar CSV</span></button>
        </nav>
        <div className={styles.sidebarBottom}>
          <button className={styles.navLink} title="Sair" aria-label="Sair" onClick={() => setAccountPanel('logout')}><LogOut size={18} /><span>Sair</span></button>
        </div>
      </aside>

      <div className={styles.page}>
        <header className={styles.topbar}>
          <button className={styles.menuButton} title="Abrir navegacao" aria-label="Abrir navegacao" onClick={() => setMobileMenu(true)}><Menu size={21} /></button>
          <div className={styles.breadcrumb}>Workspace<ChevronRight size={14} /><span>{comparison ? 'Comparacao' : 'Visao geral'}</span></div>
          <button className={styles.profileButton} title="Perfil" aria-label="Perfil" aria-expanded={accountPanel === 'profile'} onClick={() => setAccountPanel(accountPanel === 'profile' ? null : 'profile')}><UserRound size={19} /></button>
          {accountPanel && <div className={styles.accountPopover} role="status"><span>{accountPanel === 'profile' ? 'Autenticacao de perfil ainda nao configurada.' : 'Nenhuma sessao autenticada para encerrar.'}</span><button aria-label="Fechar aviso" onClick={() => setAccountPanel(null)}><X size={15} /></button></div>}
        </header>

        <main className={styles.main}>
          <div className={styles.dashboardHeader}>
            <div className={styles.heading}>
              <p className={styles.eyebrow}>EMPREGO FORMAL / SAO PAULO</p>
              <div className={styles.titleRow}><h1>{comparison ? 'Compare os municipios' : 'Mercado de trabalho'}</h1>{!comparison && <span className={styles.infoWrap}><button className={styles.infoButton} aria-label="Informacoes sobre a base de dados" aria-describedby="data-info-tooltip"><Info size={16} /></button><span id="data-info-tooltip" role="tooltip" className={styles.infoTooltip}>Dados oficiais do Novo CAGED (MTE), series com ajustes.</span></span>}</div>
              <p className={styles.subtitle}>{comparison ? 'Diferentes localidades, um mesmo recorte.' : 'Um olhar sobre os movimentos do emprego formal.'}</p>
            </div>
          </div>

          {data?.notice && <p role="note" className={styles.subtitle}>{data.notice}</p>}

          <div className={styles.filterAnalyticsRow}>
            <button className={styles.filterTrigger} type="button" aria-haspopup="dialog" aria-expanded={filterOpen} onClick={openFilters}>
              <SlidersHorizontal size={18} /><span>Filtros</span><small>{period} / {citySummary} / {sectorSummary}</small><ChevronDown size={17} />
            </button>
            <section className={styles.metricStrip} aria-label="Indicadores do periodo">
              <article className={styles.metricSummary}><span>Saldo de empregos</span><div className={styles.metricValue}><strong>{signed(total.balance)}</strong>{trendChip('balance')}</div></article>
              <article className={styles.metricSummary}><span>Admissoes</span><div className={styles.metricValue}><strong>{number.format(total.admissions)}</strong>{trendChip('admissions')}</div></article>
              <article className={styles.metricSummary}><span>Desligamentos</span><div className={styles.metricValue}><strong>{number.format(total.dismissals)}</strong>{trendChip('dismissals')}</div></article>
            </section>
          </div>

          {filterOpen && <dialog ref={filterDialogRef} className={styles.filterDialog} aria-labelledby="filter-dialog-title" onCancel={(event) => { event.preventDefault(); const citySelect = filterDialogRef.current?.querySelector<HTMLDetailsElement>('details.cityMultiSelect'); if (citySelect?.open) citySelect.open = false; else setFilterOpen(false); }} onClick={(event) => { const citySelect = filterDialogRef.current?.querySelector<HTMLDetailsElement>('details.cityMultiSelect'); if (citySelect?.open && !citySelect.contains(event.target as Node)) citySelect.open = false; if (event.target === event.currentTarget) setFilterOpen(false); }}>
            <div className={styles.filterDialogHeader}><h2 id="filter-dialog-title">Filtros da consulta</h2><button type="button" aria-label="Fechar filtros" onClick={() => setFilterOpen(false)}><X size={18} /></button></div>
            <form className={styles.filterDialogForm} onSubmit={(event) => { event.preventDefault(); applyFilters(); }}>
              <div className={`${styles.filterFields} ${styles.dialogFields}`}>
                <div className={styles.dateFilters}>
                  <label>De<input aria-label="Periodo inicial" type="month" value={filterDraft.start} onChange={(event) => setFilterDraft((current) => ({ ...current, start: event.target.value }))} /></label>
                  <label>Ate<input aria-label="Periodo final" type="month" value={filterDraft.end} onChange={(event) => setFilterDraft((current) => ({ ...current, end: event.target.value }))} /></label>
                </div>
                <div className={styles.categoryFilters}>
                  {!comparison && <label>Municipio<select aria-label="Municipio" value={filterDraft.city} onChange={(event) => setFilterDraft((current) => ({ ...current, city: event.target.value }))}><option value="all">Todos os municipios</option>{cities.map((city) => <option key={city}>{city}</option>)}</select></label>}
                  {comparison && <div className={styles.multiSelectField}><span>Municipios</span><details className={styles.cityMultiSelect}><summary aria-label="Selecionar municipios"><span>{cityDraft.length === 0 ? 'Selecionar municipios' : `${cityDraft.length} municipios selecionados`}</span><ChevronDown size={16} /></summary><div className={styles.cityOptions} role="group" aria-label="Municipios disponiveis">{cities.map((city) => <label key={city}><input type="checkbox" checked={cityDraft.includes(city)} onChange={(event) => setCityDraft(event.target.checked ? [...cityDraft, city] : cityDraft.filter((value) => value !== city))} /><span>{city}</span></label>)}</div></details></div>}
                  <label>Atividade economica<select aria-label="Atividade economica" value={filterDraft.sector} onChange={(event) => setFilterDraft((current) => ({ ...current, sector: event.target.value }))}><option value="all">Todos os setores</option>{sectors.map((sector) => <option key={sector}>{sector}</option>)}</select></label>
                </div>
              </div>
              <div className={styles.filterDialogActions}><button className={styles.filterReset} type="button" onClick={() => { setFilterDraft(defaultFilters); setCityDraft([...cities]); }}><RotateCcw size={14} />Limpar filtros</button><button type="button" onClick={() => setFilterOpen(false)}>Cancelar</button><button type="submit">Aplicar filtros</button></div>
            </form>
          </dialog>}

          {invalidPeriod ? <div role="alert" className={styles.empty}>Informe um periodo valido, com a data inicial anterior ou igual a final.</div>
            : isError ? <div role="alert" className={styles.empty}>Nao foi possivel carregar os dados.<button onClick={() => void refetch()}>Tentar novamente</button></div>
            : isPending ? <div role="status" className={styles.empty}>Carregando indicadores...</div>
            : !monthly.length ? <div className={styles.empty}><Database size={30} /><h2>Nenhum resultado neste recorte</h2><p>{comparison && !selectedCities.length ? 'Nenhum municipio selecionado.' : 'Nao ha dados para este recorte.'}</p><button onClick={() => { setParams({}); setSelectedCities(['Campinas', 'Sao Paulo']); }}>Restaurar consulta</button></div>
            : <>
              <div className={styles.dashboardGrid}>
                <div className={styles.dashboardColumn}>
                  <section className={`${styles.chartSection} ${styles.panelCard}`} aria-labelledby="city-chart-title">
                    <div className={styles.sectionHeading}><div><h2 id="city-chart-title">Saldo por municipio</h2><p>Comparacao no mesmo periodo</p></div></div>
                    <div className={styles.chart} role="img" aria-label="Grafico de saldo por municipio; valores detalhados na tabela">
                      <ResponsiveContainer width="100%" height="100%" minWidth={0}><BarChart data={byCity} margin={{ top: 14, right: 8, left: 0, bottom: 4 }}><CartesianGrid vertical={false} stroke="#dedede" strokeDasharray="4 4" /><XAxis dataKey="name" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} interval={0} /><YAxis tickFormatter={(value: number) => compact.format(value)} tick={{ fontSize: 10 }} tickLine={false} axisLine={false} width={43} /><Tooltip formatter={(value) => number.format(Number(value))} /><ReferenceLine y={0} stroke="#999" /><Bar name="Saldo" dataKey="balance" fill="#1a1a1a" radius={[4, 4, 0, 0]} maxBarSize={48} /></BarChart></ResponsiveContainer>
                    </div>
                  </section>

                  <section className={`${styles.tableSection} ${styles.panelCard}`} aria-labelledby="table-title">
                    <div className={styles.sectionHeading}><div><h2 id="table-title">{comparison ? 'Municipios lado a lado' : 'O recorte em detalhe'}<span className={styles.count}>{grouped.length}</span></h2><p>Valores acumulados / {period}</p></div>{!comparison && <div className={styles.segmented} aria-label="Agrupar tabela"><button aria-pressed={dimension === 'city'} onClick={() => setDimension('city')}>Municipios</button><button aria-pressed={dimension === 'sector'} onClick={() => setDimension('sector')}>Setores</button></div>}</div>
                    <div className={styles.tableToolbar}><label className={styles.search}><Search size={16} /><input aria-label="Pesquisar na tabela" placeholder={dimension === 'sector' && !comparison ? 'Buscar setor...' : 'Buscar municipio...'} value={search} onChange={(event) => setSearch(event.target.value)} />{search && <button title="Limpar pesquisa" aria-label="Limpar pesquisa" onClick={() => setSearch('')}><X size={14} /></button>}</label><span>Ordenado por saldo</span></div>
                    <div className={styles.tableScroll}><table><caption className={styles.srOnly}>Dados agregados por {dimension === 'sector' && !comparison ? 'setor' : 'municipio'}</caption><thead><tr><th>{dimension === 'sector' && !comparison ? 'Atividade economica' : 'Municipio'}</th><th>Admissoes</th><th>Desligamentos</th><th>Saldo</th><th>Saldo / admissoes</th></tr></thead><tbody>{tableRows.map((row, index) => <tr key={row.name}><th scope="row"><span className={styles.rowIndex}>{String(index + 1).padStart(2, '0')}</span>{row.name}</th><td>{number.format(row.admissions)}</td><td>{number.format(row.dismissals)}</td><td><span className={row.balance >= 0 ? styles.positive : styles.negative}>{signed(row.balance)}</span></td><td><span className={styles.shareBar}><span style={{ width: `${Math.min(100, Math.abs(row.balance / row.admissions * 100))}%` }} /></span>{(row.balance / row.admissions * 100).toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%</td></tr>)}</tbody></table>{!tableRows.length && <p className={styles.noMatches}>Nenhum resultado para "{search}".</p>}</div>
                    <div className={styles.tableFooter}>{tableRows.length} de {grouped.length} resultados<span>Fonte: Novo CAGED / MTE</span></div>
                  </section>
                </div>

                <div className={styles.dashboardColumn}>
                  <section className={`${styles.chartSection} ${styles.panelCard}`} aria-labelledby="sector-chart-title">
                    <div className={styles.sectionHeading}><div><h2 id="sector-chart-title">Movimentacoes por setor</h2><p>Admissoes e desligamentos acumulados</p></div></div>
                    <div className={`${styles.chart} ${styles.sectorChart}`} role="img" aria-label="Grafico de movimentacoes por setor; tabela detalhada abaixo">
                      <ResponsiveContainer width="100%" height="100%" minWidth={0}><BarChart data={bySector} layout="vertical" margin={{ top: 10, right: 12, left: 2, bottom: 0 }}><CartesianGrid horizontal={false} stroke="#dedede" strokeDasharray="4 4" /><XAxis type="number" tickFormatter={(value: number) => compact.format(value)} tick={{ fontSize: 9 }} tickLine={false} axisLine={false} /><YAxis type="category" dataKey="name" width={91} tick={{ fontSize: 10 }} tickLine={false} axisLine={false} /><Tooltip formatter={(value) => number.format(Number(value))} /><Legend iconType="circle" iconSize={7} /><Bar name="Admissoes" dataKey="admissions" fill="#1a1a1a" radius={[0, 4, 4, 0]} maxBarSize={14} /><Bar name="Desligamentos" dataKey="dismissals" fill="#a0a0a0" radius={[0, 4, 4, 0]} maxBarSize={14} /></BarChart></ResponsiveContainer>
                    </div>
                  </section>

                  <section className={`${styles.chartSection} ${styles.panelCard}`} aria-labelledby="monthly-chart-title">
                    <div className={styles.sectionHeading}><div><h2 id="monthly-chart-title">{comparison ? 'Evolucao conjunta' : 'O emprego ao longo do ano'}</h2><p>{comparison ? 'Movimentacao mensal das localidades selecionadas' : 'Movimentacao mensal no periodo'}</p></div>{!comparison && <div className={styles.segmented} aria-label="Indicador do grafico"><button aria-pressed={metric === 'balance'} onClick={() => setMetric('balance')}>Saldo</button><button aria-pressed={metric === 'movement'} onClick={() => setMetric('movement')}>Movimentacoes</button></div>}</div>
                    <div className={styles.chart} role="img" aria-label="Grafico de movimentacao mensal; valores detalhados abaixo">
                      <ResponsiveContainer width="100%" height="100%" minWidth={0}><LineChart data={monthly} margin={{ top: 16, right: 12, left: 0, bottom: 4 }}><CartesianGrid vertical={false} stroke="#dedede" strokeDasharray="4 4" /><XAxis dataKey="name" tickFormatter={monthLabel} tick={{ fontSize: 10 }} tickLine={false} axisLine={false} minTickGap={18} /><YAxis tickFormatter={(value: number) => compact.format(value)} tick={{ fontSize: 10 }} tickLine={false} axisLine={false} width={43} /><Tooltip labelFormatter={(value) => monthLabel(String(value))} formatter={(value) => number.format(Number(value))} /><ReferenceLine y={0} stroke="#999" />{metric === 'balance' ? <Line name="Saldo" dataKey="balance" stroke="#1a1a1a" strokeWidth={2.5} dot={{ r: 3, fill: '#fff', strokeWidth: 2 }} activeDot={{ r: 5 }} /> : <><Legend iconType="circle" iconSize={7} /><Line name="Admissoes" dataKey="admissions" stroke="#1a1a1a" strokeWidth={2.5} dot={false} /><Line name="Desligamentos" dataKey="dismissals" stroke="#8a8a8a" strokeWidth={2.5} dot={false} /></>}</LineChart></ResponsiveContainer>
                    </div>
                    <details className={styles.accessibleData}><summary>Dados mensais</summary><div className={styles.tableScroll}><table><caption className={styles.srOnly}>Valores mensais do grafico</caption><thead><tr><th>Mes</th><th>Admissoes</th><th>Desligamentos</th><th>Saldo</th></tr></thead><tbody>{monthly.map((row) => <tr key={row.name}><th scope="row">{row.name}</th><td>{number.format(row.admissions)}</td><td>{number.format(row.dismissals)}</td><td>{signed(row.balance)}</td></tr>)}</tbody></table></div></details>
                  </section>
                </div>
              </div>
            </>}
          <footer className={styles.footer}><span>CAGED<span className={styles.metaDivider}>/</span>Observatorio do trabalho</span><span>Projeto academico<span className={styles.metaDivider}>/</span>2025</span></footer>
        </main>
      </div>
    </div>
  );
}

export function App() {
  return <Routes><Route path="/" element={<Dashboard />} /><Route path="/comparar" element={<Dashboard comparison />} /><Route path="*" element={<Navigate to="/" replace />} /></Routes>;
}