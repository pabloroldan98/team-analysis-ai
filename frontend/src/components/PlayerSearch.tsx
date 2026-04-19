import { useState, useCallback, useEffect, useRef, useMemo } from "react";
import type { Lang, League, SearchPlayer, XGrowthPlayer, XGrowthRanges } from "../types";
import { t, formatCurrency, POS_ORDER, POS_KEYS } from "../i18n";
import { api } from "../api";

const NORM_RE = /[\u0300-\u036f]/g;
function norm(s: string) { return s.normalize("NFD").replace(NORM_RE, "").toLowerCase(); }

/* ── Pagination ────────────────────────────────────────────────────── */

const PAGE_SIZES = [25, 50, 100] as const;

function Pagination({
  lang, total, page, pageSize, onPage, onPageSize,
}: {
  lang: Lang; total: number; page: number; pageSize: number;
  onPage: (p: number) => void; onPageSize: (s: number) => void;
}) {
  const last = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="flex items-center justify-between flex-wrap gap-2 py-2 text-xs text-gray-500">
      <div className="flex items-center gap-1">
        <button disabled={page <= 1} onClick={() => onPage(1)} className="px-1.5 py-0.5 rounded hover:bg-gray-100 disabled:opacity-30">«</button>
        <button disabled={page <= 1} onClick={() => onPage(page - 1)} className="px-1.5 py-0.5 rounded hover:bg-gray-100 disabled:opacity-30">‹</button>
        <span className="px-2">{page} {t(lang, "page_of")} {last}</span>
        <button disabled={page >= last} onClick={() => onPage(page + 1)} className="px-1.5 py-0.5 rounded hover:bg-gray-100 disabled:opacity-30">›</button>
        <button disabled={page >= last} onClick={() => onPage(last)} className="px-1.5 py-0.5 rounded hover:bg-gray-100 disabled:opacity-30">»</button>
      </div>
      <div className="flex items-center gap-1">
        <select
          className="border rounded px-1 py-0.5 text-xs"
          value={pageSize}
          onChange={(e) => { onPageSize(Number(e.target.value)); onPage(1); }}
        >
          {PAGE_SIZES.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <span>{t(lang, "page_per_page")}</span>
      </div>
    </div>
  );
}

/* ── Slider components ──────────────────────────────────────────────── */

function DualRangeSlider({
  label, min, max, lo, hi, step, onChange, format,
}: {
  label: string; min: number; max: number; lo: number; hi: number;
  step?: number; onChange: (lo: number, hi: number) => void;
  format?: (v: number) => string;
}) {
  const fmt = format ?? ((v) => String(Math.round(v)));
  const pct = (v: number) => max > min ? ((v - min) / (max - min)) * 100 : 0;
  if (min >= max) return null;

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-gray-600">{label}</span>
        <span className="text-[10px] text-gray-400">{fmt(lo)} – {fmt(hi)}</span>
      </div>
      <div className="relative h-5">
        <div className="absolute top-1/2 -translate-y-1/2 w-full h-1 rounded bg-gray-200" />
        <div
          className="absolute top-1/2 -translate-y-1/2 h-1 rounded bg-primary/50"
          style={{ left: `${pct(lo)}%`, width: `${pct(hi) - pct(lo)}%` }}
        />
        <input
          type="range" min={min} max={max} step={step ?? 1} value={lo}
          onChange={(e) => onChange(Math.min(Number(e.target.value), hi), hi)}
          className="range-thumb absolute w-full top-0 h-5 pointer-events-none appearance-none bg-transparent [&::-webkit-slider-thumb]:pointer-events-auto [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-primary [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-white [&::-webkit-slider-thumb]:shadow [&::-webkit-slider-thumb]:cursor-pointer [&::-moz-range-thumb]:pointer-events-auto [&::-moz-range-thumb]:appearance-none [&::-moz-range-thumb]:w-3.5 [&::-moz-range-thumb]:h-3.5 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:bg-primary [&::-moz-range-thumb]:border-2 [&::-moz-range-thumb]:border-white [&::-moz-range-thumb]:shadow [&::-moz-range-thumb]:cursor-pointer"
        />
        <input
          type="range" min={min} max={max} step={step ?? 1} value={hi}
          onChange={(e) => onChange(lo, Math.max(Number(e.target.value), lo))}
          className="range-thumb absolute w-full top-0 h-5 pointer-events-none appearance-none bg-transparent [&::-webkit-slider-thumb]:pointer-events-auto [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-primary [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-white [&::-webkit-slider-thumb]:shadow [&::-webkit-slider-thumb]:cursor-pointer [&::-moz-range-thumb]:pointer-events-auto [&::-moz-range-thumb]:appearance-none [&::-moz-range-thumb]:w-3.5 [&::-moz-range-thumb]:h-3.5 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:bg-primary [&::-moz-range-thumb]:border-2 [&::-moz-range-thumb]:border-white [&::-moz-range-thumb]:shadow [&::-moz-range-thumb]:cursor-pointer"
        />
      </div>
    </div>
  );
}

function MinThresholdSlider({
  label, min, max, value, step, onChange, format,
}: {
  label: string; min: number; max: number; value: number;
  step?: number; onChange: (v: number) => void;
  format?: (v: number) => string;
}) {
  const fmt = format ?? ((v) => String(Math.round(v)));
  const pct = max > min ? ((value - min) / (max - min)) * 100 : 0;
  if (min >= max) return null;

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-gray-600">{label}</span>
        <span className="text-[10px] text-gray-400">≥ {fmt(value)}</span>
      </div>
      <div className="relative h-5">
        <div className="absolute top-1/2 -translate-y-1/2 w-full h-1 rounded bg-gray-200" />
        <div
          className="absolute top-1/2 -translate-y-1/2 h-1 rounded bg-green-400/60"
          style={{ left: `${pct}%`, width: `${100 - pct}%` }}
        />
        <input
          type="range" min={min} max={max} step={step ?? 0.01} value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="absolute w-full top-0 h-5 appearance-none bg-transparent cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-green-500 [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-white [&::-webkit-slider-thumb]:shadow [&::-moz-range-thumb]:appearance-none [&::-moz-range-thumb]:w-3.5 [&::-moz-range-thumb]:h-3.5 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:bg-green-500 [&::-moz-range-thumb]:border-2 [&::-moz-range-thumb]:border-white [&::-moz-range-thumb]:shadow"
        />
      </div>
    </div>
  );
}

interface Props {
  lang: Lang;
  season: string;
  clubName?: string;
  leagues?: League[];
}

function SearchTab({ lang, season }: Props) {
  const [query, setQuery] = useState("");
  const [position, setPosition] = useState("");
  const [minValue, setMinValue] = useState("");
  const [maxValue, setMaxValue] = useState("");
  const [minAge, setMinAge] = useState("");
  const [maxAge, setMaxAge] = useState("");
  const [results, setResults] = useState<SearchPlayer[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [sPage, setSPage] = useState(1);
  const [sPageSize, setSPageSize] = useState<number>(50);

  const doSearch = useCallback(async () => {
    setLoading(true);
    setSearched(true);
    setSPage(1);
    try {
      const res = await api.searchPlayers({
        q: query || undefined,
        season: season || undefined,
        position: position || undefined,
        minValue: minValue ? Number(minValue) : undefined,
        maxValue: maxValue ? Number(maxValue) : undefined,
        minAge: minAge ? Number(minAge) : undefined,
        maxAge: maxAge ? Number(maxAge) : undefined,
        limit: 0,
      });
      setResults(res.players);
      setTotal(res.total);
    } catch {
      setResults([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [query, season, position, minValue, maxValue, minAge, maxAge]);

  const searchDisplay = results.slice((sPage - 1) * sPageSize, sPage * sPageSize);

  return (
    <div>
      <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-7 gap-2 mb-3">
        <input
          className="input-field col-span-2"
          placeholder={t(lang, "search_placeholder")}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && doSearch()}
        />
        <select
          className="input-field"
          value={position}
          onChange={(e) => setPosition(e.target.value)}
        >
          <option value="">{t(lang, "search_position")}</option>
          {POS_ORDER.map((p) => (
            <option key={p} value={p}>{t(lang, POS_KEYS[p])}</option>
          ))}
        </select>
        <div className="relative">
          <input
            className="input-field w-full pr-8"
            type="number"
            placeholder={t(lang, "search_min_value")}
            value={minValue}
            onChange={(e) => setMinValue(e.target.value)}
          />
          <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">M€</span>
        </div>
        <div className="relative">
          <input
            className="input-field w-full pr-8"
            type="number"
            placeholder={t(lang, "search_max_value")}
            value={maxValue}
            onChange={(e) => setMaxValue(e.target.value)}
          />
          <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">M€</span>
        </div>
        <input
          className="input-field"
          type="number"
          placeholder={t(lang, "search_min_age")}
          value={minAge}
          onChange={(e) => setMinAge(e.target.value)}
        />
        <input
          className="input-field"
          type="number"
          placeholder={t(lang, "search_max_age")}
          value={maxAge}
          onChange={(e) => setMaxAge(e.target.value)}
        />
      </div>

      <button onClick={doSearch} disabled={loading} className="btn-primary mb-3">
        {loading ? "..." : t(lang, "search_btn")}
      </button>

      {searched && (
        <p className="text-xs text-gray-500 mb-2">
          <strong>{total}</strong> {t(lang, "search_results")}
        </p>
      )}

      {searched && results.length === 0 && !loading && (
        <p className="text-sm text-gray-400">{t(lang, "search_no_results")}</p>
      )}

      {results.length > 0 && (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-gray-500">
                  <th className="py-2 pr-3">#</th>
                  <th className="py-2 pr-3">{t(lang, "xgrowth_col_player")}</th>
                  <th className="py-2 pr-3">{lang === "es" ? "Equipo" : "Team"}</th>
                  <th className="py-2 pr-3">Pos</th>
                  <th className="py-2 pr-3">{lang === "es" ? "Edad" : "Age"}</th>
                  <th className="py-2 pr-3 text-right">{t(lang, "xgrowth_col_value")}</th>
                  <th className="py-2 pr-3 text-right">{t(lang, "xgrowth_col_predicted")}</th>
                  <th className="py-2 pr-3 text-right">xGrowth</th>
                  <th className="py-2 text-right">{t(lang, "fair_price")}</th>
                </tr>
              </thead>
              <tbody>
                {searchDisplay.map((p, i) => (
                  <tr key={p.player_id} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="py-1.5 pr-3 text-xs text-gray-400">{(sPage - 1) * sPageSize + i + 1}</td>
                    <td className="py-1.5 pr-3 font-medium">
                      <div className="flex items-center gap-2">
                        {p.img_url ? (
                          <img src={p.img_url} alt="" className="w-6 h-6 rounded-full object-cover bg-gray-200" />
                        ) : (
                          <div className="w-6 h-6 rounded-full bg-gray-200" />
                        )}
                        <span>{p.name}</span>
                      </div>
                    </td>
                    <td className="py-1.5 pr-3 text-xs text-gray-500">{p.team}</td>
                    <td className="py-1.5 pr-3 text-xs">{p.position}</td>
                    <td className="py-1.5 pr-3 text-xs">{p.age ?? "?"}</td>
                    <td className="py-1.5 pr-3 text-right text-xs">{formatCurrency(p.market_value)}</td>
                    <td className="py-1.5 pr-3 text-right text-xs">
                      {p.predicted_value != null ? formatCurrency(p.predicted_value) : "—"}
                    </td>
                    <td className={`py-1.5 pr-3 text-right text-xs font-semibold ${
                      p.xgrowth != null && p.xgrowth >= 0 ? "text-green-600" : "text-red-600"
                    }`}>
                      {p.xgrowth != null ? (Math.abs(p.xgrowth) >= 99 ? "∞" : `${(p.xgrowth >= 0 ? "+" : "")}${(p.xgrowth * 100).toFixed(1)}%`) : "—"}
                    </td>
                    <td className="py-1.5 text-right text-xs">
                      {p.fair_price != null ? formatCurrency(p.fair_price) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination lang={lang} total={results.length} page={sPage} pageSize={sPageSize} onPage={setSPage} onPageSize={setSPageSize} />
        </>
      )}
    </div>
  );
}

const HORIZONS = [1, 2, 3] as const;
const SORT_OPTIONS = ["xgrowth", "predicted_value", "net_benefit", "roi", "growth_pct", "market_value"] as const;
type SortKey = typeof SORT_OPTIONS[number];
const SORT_LABELS: Record<string, Record<SortKey, string>> = {
  es: { xgrowth: "xGrowth", predicted_value: "Valor predicho", net_benefit: "Benef. Neto", roi: "ROI", growth_pct: "Crec. %", market_value: "Valor actual" },
  en: { xgrowth: "xGrowth", predicted_value: "Predicted value", net_benefit: "Net Benefit", roi: "ROI", growth_pct: "Growth %", market_value: "Market value" },
};

const DEFAULT_RANGES: XGrowthRanges = {
  age: [15, 45], market_value: [0, 200_000_000], predicted_value: [0, 200_000_000],
  fair_price: [0, 200_000_000], xgrowth: [-1, 3], net_benefit: [-100_000_000, 200_000_000],
  roi: [-1, 5], growth_pct: [0, 6],
};

function XGrowthTab({ lang, season, clubName, leagues }: Props) {
  // Heavy filters (trigger immediate re-fetch)
  const [horizon, setHorizon] = useState<number>(1);
  const [onlyAvailable, setOnlyAvailable] = useState(false);
  const [selectedLeagues, setSelectedLeagues] = useState<string[]>([]);
  const [selectedNationalities, setSelectedNationalities] = useState<string[]>([]);
  const [includeSecondNat, setIncludeSecondNat] = useState(false);
  const [excludeTopN, setExcludeTopN] = useState("");
  const [sortBy, setSortBy] = useState<SortKey>("net_benefit");
  const [availableNationalities, setAvailableNationalities] = useState<string[]>([]);

  // Slider / light filters (trigger debounced server re-fetch)
  const [position, setPosition] = useState("");
  const [teamQuery, setTeamQuery] = useState("");
  const [fAge, setFAge] = useState<[number, number]>([0, 99]);
  const [fMv, setFMv] = useState<[number, number]>([0, 1e12]);
  const [fPv, setFPv] = useState<[number, number]>([0, 1e12]);
  const [fFp, setFFp] = useState<[number, number]>([0, 1e12]);
  const [fXg, setFXg] = useState(-999);
  const [fNb, setFNb] = useState(-1e12);
  const [fRoi, setFRoi] = useState(-999);
  const [fGp, setFGp] = useState(-999);

  const [advOpen, setAdvOpen] = useState(false);
  const [allPlayers, setAllPlayers] = useState<XGrowthPlayer[]>([]);
  const [globalRanges, setGlobalRanges] = useState<XGrowthRanges>(DEFAULT_RANGES);
  const [loading, setLoading] = useState(false);
  const rangesInitRef = useRef(false);

  const heavyRef = useRef({ season, clubName, horizon, excludeTopN, sortBy });
  heavyRef.current = { season, clubName, horizon, excludeTopN, sortBy };

  const resetSliders = (r: XGrowthRanges) => {
    setFAge(r.age);
    setFMv(r.market_value);
    setFPv(r.predicted_value);
    setFFp(r.fair_price);
    setFXg(r.xgrowth[0]);
    setFNb(r.net_benefit[0]);
    setFRoi(r.roi[0]);
    setFGp(r.growth_pct[0]);
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const fetchPlayers = useCallback(async (initRanges: boolean) => {
    setLoading(true);
    const h = heavyRef.current;
    try {
      const res = await api.getXGrowth({
        season: h.season || undefined,
        horizon: h.horizon,
        excludeTopN: h.excludeTopN ? Number(h.excludeTopN) : undefined,
        sortBy: h.sortBy,
        limit: 0,
      });
      setAllPlayers(res.players);
      if (res.ranges) {
        if (initRanges) {
          setGlobalRanges(res.ranges);
          resetSliders(res.ranges);
        }
      }
    } catch {
      setAllPlayers([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // Heavy filter changes → immediate fetch
  useEffect(() => {
    const init = !rangesInitRef.current;
    rangesInitRef.current = true;
    fetchPlayers(init);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [season, clubName, horizon, excludeTopN, sortBy]);

  // Client-side filtering by league, nationality, sliders, position, team query, and availability
  const filteredPlayers = useMemo(() => {
    const tq = norm(teamQuery.trim());
    const leagueSet = selectedLeagues.length ? new Set(selectedLeagues) : null;
    const natSet = selectedNationalities.length ? new Set(selectedNationalities) : null;
    return allPlayers.filter((p) => {
      if (onlyAvailable && !p.is_available) return false;
      if (leagueSet && !leagueSet.has(p.league)) return false;
      if (natSet) {
        const mainMatch = natSet.has(p.nationality);
        const secondMatch = includeSecondNat && p.other_nationalities?.some((n) => natSet.has(n));
        if (!mainMatch && !secondMatch) return false;
      }
      if (position && p.position !== position) return false;
      if (tq && !norm(p.team).includes(tq)) return false;
      const age = p.age ?? 0;
      if (age < fAge[0] || age > fAge[1]) return false;
      if (p.market_value < fMv[0] || p.market_value > fMv[1]) return false;
      if (p.predicted_value < fPv[0] || p.predicted_value > fPv[1]) return false;
      if (p.fair_price < fFp[0] || p.fair_price > fFp[1]) return false;
      if (p.xgrowth < fXg) return false;
      if (p.net_benefit < fNb) return false;
      if (p.roi < fRoi) return false;
      if (p.growth_pct < fGp) return false;
      return true;
    });
  }, [allPlayers, onlyAvailable, selectedLeagues, selectedNationalities, includeSecondNat, position, teamQuery, fAge, fMv, fPv, fFp, fXg, fNb, fRoi, fGp]);

  const [xgPage, setXgPage] = useState(1);
  const [xgPageSize, setXgPageSize] = useState<number>(50);
  // Reset page when filters change
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { setXgPage(1); }, [onlyAvailable, selectedLeagues, selectedNationalities, includeSecondNat, position, teamQuery, fAge, fMv, fPv, fFp, fXg, fNb, fRoi, fGp]);

  const xgTotalPages = Math.max(1, Math.ceil(filteredPlayers.length / xgPageSize));
  const displayResults = filteredPlayers.slice((xgPage - 1) * xgPageSize, xgPage * xgPageSize);

  const toggleLeague = (id: string) => {
    setSelectedLeagues((prev) =>
      prev.includes(id) ? prev.filter((l) => l !== id) : [...prev, id],
    );
  };

  const toggleNationality = (nat: string) => {
    setSelectedNationalities((prev) =>
      prev.includes(nat) ? prev.filter((n) => n !== nat) : [...prev, nat],
    );
  };

  useEffect(() => {
    api.getNationalities().then(setAvailableNationalities).catch(() => {});
  }, []);

  const sortLabels = SORT_LABELS[lang] || SORT_LABELS.en;
  const fmtM = (v: number) => formatCurrency(v);
  const fmtPct = (v: number) => `${(v * 100).toFixed(1)}%`;
  const fmtPctInf = (v: number, sign = false) =>
    !isFinite(v) || Math.abs(v) >= 9000 ? (v > 0 ? "∞" : "-∞") : `${sign && v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%`;
  const r = globalRanges;

  return (
    <div>
      <p className="text-xs text-gray-500 mb-3">{t(lang, "xgrowth_help")}</p>

      {/* Horizon selector */}
      <div className="mb-3">
        <label className="block text-xs font-medium mb-1">{t(lang, "xgrowth_horizon")}</label>
        <div className="flex gap-2">
          {HORIZONS.map((h) => (
            <button
              key={h}
              onClick={() => { setHorizon(h); rangesInitRef.current = false; }}
              className={`chip ${horizon === h ? "chip-active" : "chip-inactive"}`}
            >
              {t(lang, `horizon_${h}`)}
            </button>
          ))}
        </div>
      </div>

      {/* Basic filters row */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mb-3">
        <select
          className="input-field"
          value={position}
          onChange={(e) => setPosition(e.target.value)}
        >
          <option value="">{t(lang, "xgrowth_all_positions")}</option>
          {POS_ORDER.map((p) => (
            <option key={p} value={p}>{t(lang, POS_KEYS[p])}</option>
          ))}
        </select>
        <input
          className="input-field"
          placeholder={lang === "es" ? "Buscar equipo..." : "Search team..."}
          value={teamQuery}
          onChange={(e) => setTeamQuery(e.target.value)}
        />
        <select
          className="input-field"
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as SortKey)}
        >
          {SORT_OPTIONS.map((k) => (
            <option key={k} value={k}>{sortLabels[k]}</option>
          ))}
        </select>
      </div>

      {clubName && (
        <label className="flex items-center gap-2 cursor-pointer select-none text-sm mb-3">
          <input
            type="checkbox"
            checked={onlyAvailable}
            onChange={(e) => setOnlyAvailable(e.target.checked)}
            className="w-4 h-4 accent-primary rounded"
          />
          {t(lang, "xgrowth_only_available")} <strong>{clubName}</strong>
        </label>
      )}

      {/* Advanced filters collapsible */}
      <div className="border border-gray-200 rounded-lg mb-3">
        <button
          onClick={() => setAdvOpen(!advOpen)}
          className="w-full flex items-center justify-between px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 rounded-lg"
        >
          {t(lang, "xgrowth_filters_title")}
          <span className="text-xs">{advOpen ? "▲" : "▼"}</span>
        </button>
        {advOpen && (
          <div className="px-3 pb-3 space-y-4">
            {/* League filter */}
            {leagues && leagues.length > 0 && (
              <div>
                <label className="block text-xs font-medium mb-1">{t(lang, "xgrowth_league_filter")}</label>
                <div className="flex flex-wrap gap-1.5 max-h-28 overflow-y-auto">
                  {leagues.map((l) => {
                    const active = selectedLeagues.includes(l.league_id);
                    return (
                      <button
                        key={l.league_id}
                        onClick={() => toggleLeague(l.league_id)}
                        className={`chip text-xs ${active ? "chip-active" : "chip-inactive"}`}
                      >
                        {l.name}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Nationality filter */}
            {availableNationalities.length > 0 && (
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-xs font-medium">
                    {lang === "es" ? "Nacionalidad" : "Nationality"}
                  </label>
                  <label className="flex items-center gap-1.5 cursor-pointer select-none text-[10px] text-gray-500">
                    <input
                      type="checkbox"
                      checked={includeSecondNat}
                      onChange={(e) => setIncludeSecondNat(e.target.checked)}
                      className="w-3 h-3 accent-primary rounded"
                    />
                    {lang === "es" ? "Incluir 2ª nacionalidad" : "Include 2nd nationality"}
                  </label>
                </div>
                <div className="flex flex-wrap gap-1.5 max-h-28 overflow-y-auto">
                  {availableNationalities.map((nat) => {
                    const active = selectedNationalities.includes(nat);
                    return (
                      <button
                        key={nat}
                        onClick={() => toggleNationality(nat)}
                        className={`chip text-xs ${active ? "chip-active" : "chip-inactive"}`}
                      >
                        {nat}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Exclude top N clubs */}
            <div>
              <label className="block text-xs font-medium mb-1">{t(lang, "xgrowth_exclude_top")}</label>
              <p className="text-[10px] text-gray-400 mb-1">{t(lang, "xgrowth_exclude_top_help")}</p>
              <input
                className="input-field w-24"
                type="number"
                min="0"
                placeholder="0"
                value={excludeTopN}
                onChange={(e) => setExcludeTopN(e.target.value)}
              />
            </div>

            {/* Dual-thumb range sliders */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-3">
              <DualRangeSlider
                label={lang === "es" ? "Edad" : "Age"}
                min={r.age[0]} max={r.age[1]} lo={fAge[0]} hi={fAge[1]}
                onChange={(lo, hi) => setFAge([lo, hi])}
              />
              <DualRangeSlider
                label={t(lang, "xgrowth_col_value")}
                min={r.market_value[0]} max={r.market_value[1]}
                lo={fMv[0]} hi={fMv[1]}
                step={500_000}
                onChange={(lo, hi) => setFMv([lo, hi])}
                format={fmtM}
              />
              <DualRangeSlider
                label={t(lang, "xgrowth_col_predicted")}
                min={r.predicted_value[0]} max={r.predicted_value[1]}
                lo={fPv[0]} hi={fPv[1]}
                step={500_000}
                onChange={(lo, hi) => setFPv([lo, hi])}
                format={fmtM}
              />
              <DualRangeSlider
                label={t(lang, "fair_price")}
                min={r.fair_price[0]} max={r.fair_price[1]}
                lo={fFp[0]} hi={fFp[1]}
                step={500_000}
                onChange={(lo, hi) => setFFp([lo, hi])}
                format={fmtM}
              />
            </div>

            {/* Single-thumb min-threshold sliders */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-3">
              <MinThresholdSlider
                label="xGrowth"
                min={r.xgrowth[0]} max={r.xgrowth[1]} value={fXg}
                step={0.01}
                onChange={setFXg}
                format={fmtPct}
              />
              <MinThresholdSlider
                label={t(lang, "xgrowth_col_net_benefit")}
                min={r.net_benefit[0]} max={r.net_benefit[1]} value={fNb}
                step={500_000}
                onChange={setFNb}
                format={fmtM}
              />
              <MinThresholdSlider
                label="ROI"
                min={r.roi[0]} max={r.roi[1]} value={fRoi}
                step={0.01}
                onChange={setFRoi}
                format={fmtPct}
              />
              <MinThresholdSlider
                label={t(lang, "xgrowth_col_growth_pct")}
                min={r.growth_pct[0]} max={r.growth_pct[1]} value={fGp}
                step={0.01}
                onChange={setFGp}
                format={fmtPct}
              />
            </div>
          </div>
        )}
      </div>

      {loading ? (
        <p className="text-xs text-gray-400 animate-pulse py-2">{t(lang, "loading_analytics")}</p>
      ) : (
        <>
          <p className="text-xs text-gray-500 mb-2">
            <strong>{filteredPlayers.length}</strong> / {allPlayers.length} {t(lang, "xgrowth_total")}
          </p>
          {displayResults.length > 0 && (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-xs text-gray-500">
                      <th className="py-2 pr-2">#</th>
                      <th className="py-2 pr-2">{t(lang, "xgrowth_col_player")}</th>
                      <th className="py-2 pr-2">Pos</th>
                      <th className="py-2 pr-2">{lang === "es" ? "Edad" : "Age"}</th>
                      <th className="py-2 pr-2 text-right">{t(lang, "xgrowth_col_value")}</th>
                      <th className="py-2 pr-2 text-right">{t(lang, "xgrowth_col_predicted")}</th>
                      <th className="py-2 pr-2 text-right">{t(lang, "xgrowth_label")}</th>
                      <th className="py-2 pr-2 text-right">{t(lang, "xgrowth_col_net_benefit")}</th>
                      <th className="py-2 pr-2 text-right">{t(lang, "xgrowth_col_roi")}</th>
                      <th className="py-2 pr-2 text-right">{t(lang, "xgrowth_col_growth_pct")}</th>
                      <th className="py-2 text-right">{t(lang, "fair_price")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {displayResults.map((p, i) => (
                      <tr key={p.player_id} className="border-b border-gray-100 hover:bg-gray-50">
                        <td className="py-1.5 pr-2 text-xs text-gray-400">{(xgPage - 1) * xgPageSize + i + 1}</td>
                        <td className="py-1.5 pr-2 font-medium">
                          <div className="flex items-center gap-2">
                            {p.img_url ? (
                              <img src={p.img_url} alt="" className="w-6 h-6 rounded-full object-cover bg-gray-200" />
                            ) : (
                              <div className="w-6 h-6 rounded-full bg-gray-200" />
                            )}
                            <span className="whitespace-nowrap">{p.name}</span>
                            <span className="text-[10px] text-gray-400 whitespace-nowrap">{p.team}</span>
                          </div>
                        </td>
                        <td className="py-1.5 pr-2 text-xs">{p.position}</td>
                        <td className="py-1.5 pr-2 text-xs">{p.age ?? "?"}</td>
                        <td className="py-1.5 pr-2 text-right text-xs">{formatCurrency(p.market_value)}</td>
                        <td className="py-1.5 pr-2 text-right text-xs">{formatCurrency(p.predicted_value)}</td>
                        <td className={`py-1.5 pr-2 text-right text-xs font-semibold ${p.xgrowth >= 0 ? "text-green-600" : "text-red-600"}`}>
                          {fmtPctInf(p.xgrowth, true)}
                        </td>
                        <td className={`py-1.5 pr-2 text-right text-xs font-semibold ${p.net_benefit >= 0 ? "text-green-600" : "text-red-600"}`}>
                          {formatCurrency(p.net_benefit)}
                        </td>
                        <td className={`py-1.5 pr-2 text-right text-xs font-semibold ${p.roi >= 0 ? "text-green-600" : "text-red-600"}`}>
                          {fmtPctInf(p.roi, true)}
                        </td>
                        <td className="py-1.5 pr-2 text-right text-xs">
                          {fmtPctInf(p.growth_pct)}
                        </td>
                        <td className="py-1.5 text-right text-xs">{formatCurrency(p.fair_price)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination lang={lang} total={filteredPlayers.length} page={xgPage} pageSize={xgPageSize} onPage={setXgPage} onPageSize={setXgPageSize} />
            </>
          )}
        </>
      )}
    </div>
  );
}

export default function PlayerSearch({ lang, season, clubName, leagues }: Props) {
  const [tab, setTab] = useState<"search" | "xgrowth">("xgrowth");

  return (
    <div className="card mt-4">
      <div className="flex gap-1 mb-4 border-b">
        {(["xgrowth", "search"] as const).map((key) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`px-3 py-1.5 text-sm font-medium border-b-2 transition-colors ${
              tab === key
                ? "border-primary text-primary-dark"
                : "border-transparent text-gray-400 hover:text-gray-600"
            }`}
          >
            {t(lang, `tab_${key}`)}
          </button>
        ))}
      </div>

      {tab === "search" && <SearchTab lang={lang} season={season} clubName={clubName} />}
      {tab === "xgrowth" && <XGrowthTab lang={lang} season={season} clubName={clubName} leagues={leagues} />}
    </div>
  );
}
