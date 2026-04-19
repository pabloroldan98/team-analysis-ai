import { useState, useEffect, useRef } from "react";
import type { Lang, Player, Club, BuyMode, Approach, Objective, SimSpeed, BuyCounts, SellRecommendation, League, AdvancedFilters } from "../types";
import { t, formatCurrency, POS_ORDER, POS_KEYS } from "../i18n";
import { api } from "../api";

/* ── helpers ────────────────────────────────────────────────────────────── */

function totalCombinations(total: number, maxPerPos = 3): number[][] {
  const combos: number[][] = [];
  for (let gk = 0; gk <= Math.min(total, maxPerPos); gk++)
    for (let df = 0; df <= Math.min(total - gk, maxPerPos); df++)
      for (let mid = 0; mid <= Math.min(total - gk - df, maxPerPos); mid++) {
        const att = total - gk - df - mid;
        if (att >= 0 && att <= maxPerPos) combos.push([gk, df, mid, att]);
      }
  return combos;
}

const APPROACHES: Approach[] = ["max_value", "young_talents", "balanced", "veteran_players"];
const OBJECTIVES: Objective[] = ["smv", "net_benefit", "roi", "growth_pct"];
const SIM_SPEEDS: SimSpeed[] = ["standard", "fast", "local"];

/* ── sub-components ─────────────────────────────────────────────────────── */

function levenshtein(a: string, b: string): number {
  const m = a.length, n = b.length;
  if (m === 0) return n;
  if (n === 0) return m;
  let prev = Array.from({ length: n + 1 }, (_, i) => i);
  for (let i = 1; i <= m; i++) {
    const curr = [i];
    for (let j = 1; j <= n; j++) {
      curr[j] = Math.min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    }
    prev = curr;
  }
  return prev[n];
}

const NORM_RE = /[\u0300-\u036f]/g;
function norm(s: string) { return s.normalize("NFD").replace(NORM_RE, "").toLowerCase(); }

function clubMatchScore(query: string, clubName: string): number {
  const q = norm(query);
  const t = norm(clubName);

  // Full name starts with query → best
  if (t.startsWith(q)) return -2;

  const tWords = t.split(/\s+/).filter(Boolean);

  // Any word starts with query → very good
  if (tWords.some((w) => w.startsWith(q))) return -1;

  // Substring anywhere in name
  if (t.includes(q)) return 0;

  // Per-word fuzzy matching
  const qWords = q.split(/\s+/).filter(Boolean);
  let total = 0;
  for (const qw of qWords) {
    let best = Infinity;
    for (const tw of tWords) {
      if (tw.startsWith(qw)) { best = -1; break; }
      if (tw.includes(qw)) { best = 0; break; }
      if (qw.length >= 3 && Math.abs(qw.length - tw.length) <= 2)
        best = Math.min(best, levenshtein(qw, tw));
    }
    total += best;
  }
  return total;
}

function ClubSearchSelect({
  clubs, value, onChange,
}: {
  clubs: Club[]; value: string; onChange: (name: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
        setQuery("");
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const filtered = clubs.filter((c) =>
    norm(c.name).includes(norm(query)),
  );

  return (
    <div ref={containerRef} className="relative">
      <input
        ref={inputRef}
        type="text"
        className="input-field text-sm w-full"
        placeholder="Search..."
        value={open ? query : value}
        onFocus={() => { setOpen(true); setQuery(""); }}
        onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
      />
      {open && query.length > 0 && (
        <ul className="absolute z-40 mt-1 w-full max-h-60 overflow-y-auto bg-white border border-gray-200 rounded-lg shadow-lg">
          {filtered.length === 0 ? (
            <li className="px-3 py-2 text-sm text-gray-400 italic">
              No results
            </li>
          ) : (
            filtered.slice(0, 30).map((c) => (
              <li
                key={c.name}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  onChange(c.name);
                  setQuery("");
                  setOpen(false);
                  inputRef.current?.blur();
                }}
                className={`px-3 py-2 text-sm cursor-pointer hover:bg-primary/10 ${
                  c.name === value ? "bg-primary/5 font-semibold text-primary-dark" : ""
                }`}
              >
                {c.name}
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}

function SeasonClubSelector({
  lang, seasons, clubs, season, clubName,
  onSeasonChange, onClubChange,
}: {
  lang: Lang; seasons: string[]; clubs: Club[];
  season: string; clubName: string;
  onSeasonChange: (s: string) => void; onClubChange: (c: string) => void;
}) {
  const todayLabel = t(lang, "today_option");
  return (
    <div className="grid grid-cols-2 gap-4">
      <div>
        <label className="block text-sm font-medium mb-1">{t(lang, "select_season")}</label>
        <select
          className="input-field"
          value={season}
          onChange={(e) => onSeasonChange(e.target.value)}
        >
          {/* <option value="today">{todayLabel}</option> */}
          {seasons.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </div>
      <div>
        <label className="block text-sm font-medium mb-1">{t(lang, "select_club")}</label>
        <ClubSearchSelect clubs={clubs} value={clubName} onChange={onClubChange} />
      </div>
    </div>
  );
}

function SellRecList({
  lang, items, selected, onToggle, mode = "decline",
}: {
  lang: Lang; items: SellRecommendation[]; selected: string[];
  onToggle: (id: string) => void;
  mode?: "decline" | "squad";
}) {
  return (
    <div className="space-y-1 max-h-72 overflow-y-auto pr-1">
      {items.map((r) => {
        const loan = !!r.on_loan;
        const isSelected = !loan && selected.includes(r.player_id);
        const posKey = POS_KEYS[r.position] ?? "pos_def";
        const diff = r.predicted_value - r.market_value;
        const diffPct = r.market_value > 0 ? (diff / r.market_value) * 100 : 0;
        const isGrowth = diff >= 0;
        return (
          <button
            key={r.player_id}
            disabled={loan}
            onClick={() => !loan && onToggle(r.player_id)}
            title={loan ? t(lang, "on_loan_not_available") : undefined}
            className={`w-full flex items-center justify-between text-left px-3 py-1.5 rounded-lg text-sm transition-colors ${
              loan
                ? "bg-gray-50 border border-transparent opacity-40 cursor-not-allowed"
                : isSelected
                  ? "bg-red-50 border border-red-200"
                  : "bg-gray-50 border border-transparent hover:bg-gray-100"
            }`}
          >
            <div className="flex items-center gap-2 min-w-0">
              <span className={`font-medium truncate ${isSelected ? "text-red-700" : ""}`}>
                {r.name}
              </span>
              {loan && <span className="text-[10px] italic opacity-70">({t(lang, "on_loan_label")})</span>}
              <span className="text-xs text-gray-400">
                {t(lang, posKey)}, {r.age ?? "?"}
              </span>
            </div>
            <div className="flex items-center gap-3 shrink-0 ml-2">
              <span className="text-xs text-gray-500">
                {formatCurrency(r.market_value)} → {formatCurrency(r.predicted_value)}
              </span>
              {r.fair_price != null && (
                <span className="text-[10px] text-gray-400">
                  {t(lang, "fair_price")}: {formatCurrency(r.fair_price)}
                </span>
              )}
              {mode === "squad" ? (
                <span className={`text-xs font-semibold ${isGrowth ? "text-green-600" : "text-red-600"}`}>
                  {isGrowth ? "▲" : "▼"} {formatCurrency(Math.abs(diff))} ({diffPct >= 0 ? "+" : ""}{diffPct.toFixed(0)}%)
                </span>
              ) : (
                <span className="text-xs font-semibold text-red-600">
                  ▼ {formatCurrency(r.decline)} ({(r.decline_pct * 100).toFixed(0)}%)
                </span>
              )}
            </div>
          </button>
        );
      })}
    </div>
  );
}

function SellRecommendationsPanel({
  lang,
  recommendations,
  loading,
  selected,
  onToggle,
  onSelectAll,
}: {
  lang: Lang;
  recommendations: SellRecommendation[];
  loading: boolean;
  selected: string[];
  onToggle: (id: string) => void;
  onSelectAll: (ids: string[]) => void;
}) {
  const [tab, setTab] = useState<"squad" | "peak" | "decline">("squad");

  if (loading) {
    return (
      <div className="text-xs text-gray-400 animate-pulse py-2">
        {t(lang, "sell_rec_loading")}
      </div>
    );
  }

  const squadByValue = [...recommendations].sort((a, b) => b.market_value - a.market_value);
  const peakPlayers = recommendations.filter((r) => r.decline > 0 && !r.on_loan);
  const topDecline = [...peakPlayers].sort((a, b) => b.decline - a.decline).slice(0, 5);

  if (!recommendations.length) return null;

  const currentList = tab === "squad" ? squadByValue : tab === "peak" ? peakPlayers : topDecline;
  const selectableIds = currentList.filter((r) => !r.on_loan).map((r) => r.player_id);

  const handleSelectAll = () => {
    const newIds = selectableIds.filter((id) => !selected.includes(id));
    if (newIds.length > 0) onSelectAll([...selected, ...newIds]);
  };

  const handleDeselectAll = () => {
    onSelectAll(selected.filter((id) => !selectableIds.includes(id)));
  };

  const hasAnySelected = selectableIds.some((id) => selected.includes(id));

  return (
    <div>
      <h3 className="section-title">{t(lang, "sell_recommendations")}</h3>
      <p className="text-xs text-gray-500 mb-3">{t(lang, "sell_rec_help")}</p>

      <div className="flex gap-2 mb-3 flex-wrap">
        {(["squad", "peak", "decline"] as const).map((key) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`chip ${tab === key ? "chip-active" : "chip-inactive"}`}
          >
            {t(lang, `sell_rec_${key}`)}
          </button>
        ))}
      </div>

      <p className="text-[11px] text-gray-400 mb-2">
        {t(lang, `sell_rec_${tab}_desc`)}
      </p>

      {currentList.length === 0 ? (
        <p className="text-xs text-gray-400 italic">
          {t(lang, `sell_rec_no_${tab}`)}
        </p>
      ) : (
        <>
          <div className="flex gap-3 mb-2">
            <button
              onClick={handleSelectAll}
              className="text-xs text-primary hover:text-primary-dark underline"
            >
              {t(lang, `sell_rec_select_all_${tab}`)}
            </button>
            {hasAnySelected && (
              <button
                onClick={handleDeselectAll}
                className="text-xs text-gray-500 hover:text-red-600 underline"
              >
                {t(lang, "sell_rec_deselect_all")}
              </button>
            )}
          </div>
          <SellRecList lang={lang} items={currentList} selected={selected} onToggle={onToggle} mode={tab === "squad" ? "squad" : "decline"} />
        </>
      )}
    </div>
  );
}

function SellSelection({
  lang, squad, selected, onChange,
}: {
  lang: Lang; squad: Player[]; selected: string[]; onChange: (ids: string[]) => void;
}) {
  const byPos: Record<string, Player[]> = {};
  for (const pos of POS_ORDER) byPos[pos] = [];
  for (const p of squad) {
    const pos = POS_ORDER.includes(p.position as any) ? p.position : "DEF";
    byPos[pos].push(p);
  }
  for (const pos of POS_ORDER)
    byPos[pos].sort((a, b) => (b.market_value ?? 0) - (a.market_value ?? 0));

  const toggle = (id: string) => {
    onChange(
      selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]
    );
  };

  return (
    <div>
      <h3 className="section-title">{t(lang, "select_players_to_sell")}</h3>
      <p className="text-xs text-gray-500 mb-3">{t(lang, "sell_selection_help")}</p>
      {POS_ORDER.map((pos) => {
        const players = byPos[pos];
        if (!players.length) return null;
        return (
          <div key={pos} className="mb-3">
            <div className="text-sm font-semibold text-primary-dark mb-1">
              {t(lang, POS_KEYS[pos])}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {players.map((p) => {
                const loan = p.on_loan;
                const active = !loan && selected.includes(p.player_id);
                const mv = p.market_value ?? 0;
                const pv = p.predicted_value ?? mv;
                const growing = pv >= mv;
                return (
                  <button
                    key={p.player_id}
                    onClick={() => !loan && toggle(p.player_id)}
                    disabled={loan}
                    className={`chip ${loan ? "chip-inactive opacity-40 cursor-not-allowed" : active ? "chip-active" : "chip-inactive"}`}
                    title={loan ? t(lang, "on_loan_not_available") : undefined}
                  >
                    {p.name}
                    {loan && <span className="text-[10px] italic opacity-70">({t(lang, "on_loan_label")})</span>}
                    <span className={`text-[10px] ${active ? "opacity-80" : "opacity-70"}`}>
                      {formatCurrency(mv)}
                    </span>
                    <span className={`text-[10px] ${active ? "text-white/80" : growing ? "text-green-600" : "text-red-500"}`}>
                      → {formatCurrency(pv)}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function BuyCountsSelector({
  lang, buyMode, setBuyMode, exactCounts, setExactCounts,
  rangeCounts, setRangeCounts, totalCount, setTotalCount,
}: {
  lang: Lang;
  buyMode: BuyMode; setBuyMode: (m: BuyMode) => void;
  exactCounts: Record<string, number>; setExactCounts: (c: Record<string, number>) => void;
  rangeCounts: Record<string, [number, number]>;
  setRangeCounts: (c: Record<string, [number, number]>) => void;
  totalCount: number; setTotalCount: (n: number) => void;
}) {
  return (
    <div>
      <h3 className="section-title">{t(lang, "signings_per_position")}</h3>
      <div className="flex gap-2 mb-3">
        {(["total", "range", "exact"] as BuyMode[]).map((m) => (
          <button
            key={m}
            onClick={() => setBuyMode(m)}
            className={`chip ${buyMode === m ? "chip-active" : "chip-inactive"}`}
          >
            {t(lang, `buy_mode_${m}`)}
          </button>
        ))}
      </div>

      {buyMode === "exact" && (
        <>
          <p className="text-xs text-gray-500 mb-2">{t(lang, "signings_exact_help")}</p>
          <div className="grid grid-cols-4 gap-3">
            {POS_ORDER.map((pos) => (
              <div key={pos}>
                <label className="block text-xs font-medium mb-1">
                  {t(lang, POS_KEYS[pos])}
                </label>
                <input
                  type="number" min={0} max={3}
                  value={exactCounts[pos] ?? 1}
                  onChange={(e) =>
                    setExactCounts({ ...exactCounts, [pos]: Number(e.target.value) })
                  }
                  className="input-field"
                />
              </div>
            ))}
          </div>
        </>
      )}

      {buyMode === "range" && (
        <>
          <p className="text-xs text-gray-500 mb-2">{t(lang, "signings_range_help")}</p>
          <div className="grid grid-cols-4 gap-3">
            {POS_ORDER.map((pos) => {
              const [lo, hi] = rangeCounts[pos] ?? [0, 2];
              return (
                <div key={pos}>
                  <div className="text-xs font-semibold mb-1">{t(lang, POS_KEYS[pos])}</div>
                  <input
                    type="number" min={0} max={2} value={lo}
                    onChange={(e) => {
                      const v = Number(e.target.value);
                      setRangeCounts({
                        ...rangeCounts,
                        [pos]: [v, Math.max(v, hi)],
                      });
                    }}
                    className="input-field mb-1"
                    placeholder={t(lang, "buy_min")}
                  />
                  <input
                    type="number" min={lo} max={2} value={hi}
                    onChange={(e) =>
                      setRangeCounts({
                        ...rangeCounts,
                        [pos]: [lo, Number(e.target.value)],
                      })
                    }
                    className="input-field"
                    placeholder={t(lang, "buy_max")}
                  />
                </div>
              );
            })}
          </div>
        </>
      )}

      {buyMode === "total" && (
        <>
          <p className="text-xs text-gray-500 mb-2">{t(lang, "signings_total_help")}</p>
          <input
            type="number" min={0} max={10} value={totalCount}
            onChange={(e) => setTotalCount(Number(e.target.value))}
            className="input-field w-40"
          />
          <p className="text-xs text-gray-400 mt-1">
            {totalCombinations(totalCount).length} {lang === "es" ? "combinaciones" : "combinations"}
          </p>
        </>
      )}
    </div>
  );
}

function BudgetInput({
  lang, budget, setBudget, unlimited, setUnlimited,
}: {
  lang: Lang; budget: number; setBudget: (n: number) => void;
  unlimited: boolean; setUnlimited: (b: boolean) => void;
}) {
  const [draft, setDraft] = useState(String(budget));
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (document.activeElement !== inputRef.current) {
      setDraft(String(budget));
    }
  }, [budget]);

  const commit = (raw: string) => {
    const n = Math.round(Number(raw));
    if (!isNaN(n)) {
      const clamped = Math.max(-2000, Math.min(2000, n));
      setBudget(clamped);
      setDraft(String(clamped));
    } else {
      setDraft(String(budget));
    }
  };

  return (
    <div>
      <h3 className="section-title">{t(lang, "budget_title")}</h3>
      <p className="text-xs text-gray-500 mb-2">{t(lang, "budget_extra_note")}</p>
      <div className="flex items-end gap-4">
        <div className="flex-1">
          <input
            ref={inputRef}
            type="number" min={-2000} max={2000} step={10}
            value={draft} disabled={unlimited}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={(e) => commit(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") commit((e.target as HTMLInputElement).value); }}
            className="input-field"
          />
        </div>
        <label className="flex items-center gap-2 pb-1 cursor-pointer select-none">
          <input
            type="checkbox" checked={unlimited}
            onChange={(e) => setUnlimited(e.target.checked)}
            className="w-4 h-4 accent-primary rounded"
          />
          <span className="text-sm">{t(lang, "unlimited_budget")}</span>
        </label>
      </div>
    </div>
  );
}

function ApproachSelector({
  lang, approach, setApproach,
}: {
  lang: Lang; approach: Approach; setApproach: (a: Approach) => void;
}) {
  return (
    <div>
      <h3 className="section-title">{t(lang, "approach_title")}</h3>
      <div className="flex flex-wrap gap-2 mb-2">
        {APPROACHES.map((a) => (
          <button
            key={a}
            onClick={() => setApproach(a)}
            className={`chip ${approach === a ? "chip-active" : "chip-inactive"}`}
          >
            {t(lang, `approach_${a}`)}
          </button>
        ))}
      </div>
      <p className="text-xs text-gray-500">{t(lang, `approach_${approach}_help`)}</p>
    </div>
  );
}

function ObjectiveSelector({
  lang, objective, setObjective,
}: {
  lang: Lang; objective: Objective; setObjective: (o: Objective) => void;
}) {
  return (
    <div>
      <h3 className="section-title">{t(lang, "objective_title")}</h3>
      <div className="flex flex-wrap gap-2 mb-2">
        {OBJECTIVES.map((o) => (
          <button
            key={o}
            onClick={() => setObjective(o)}
            className={`chip ${objective === o ? "chip-active" : "chip-inactive"}`}
          >
            {t(lang, `objective_${o}`)}
          </button>
        ))}
      </div>
      <p className="text-xs text-gray-500">{t(lang, `objective_${objective}_help`)}</p>
    </div>
  );
}

function SimSpeedSelector({
  lang, speed, setSpeed,
}: {
  lang: Lang; speed: SimSpeed; setSpeed: (s: SimSpeed) => void;
}) {
  return (
    <div>
      <h3 className="section-title">{t(lang, "sim_speed_title")}</h3>
      <div className="flex flex-wrap gap-2 mb-2">
        {SIM_SPEEDS.map((s) => (
          <button
            key={s}
            onClick={() => setSpeed(s)}
            className={`chip ${speed === s ? "chip-active" : "chip-inactive"}`}
          >
            {t(lang, `sim_speed_${s}`)}
          </button>
        ))}
      </div>
      <p className="text-xs text-gray-500">{t(lang, `sim_speed_${speed}_help`)}</p>
    </div>
  );
}

const HORIZONS = [1, 2, 3] as const;

function SearchableMultiSelect({
  items,
  selected,
  onChange,
  placeholder,
  labelFn = (item) => String(item),
  keyFn = (item) => String(item),
}: {
  items: string[];
  selected: string[];
  onChange: (sel: string[]) => void;
  placeholder: string;
  labelFn?: (item: string) => string;
  keyFn?: (item: string) => string;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const available = items.filter(
    (item) =>
      !selected.includes(keyFn(item)) &&
      norm(labelFn(item)).includes(norm(query))
  );

  return (
    <div ref={containerRef} className="relative">
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-2">
          {selected.map((key) => (
            <span
              key={key}
              className="inline-flex items-center gap-1 bg-primary/10 text-primary-dark text-xs px-2 py-1 rounded-full"
            >
              {key}
              <button
                onClick={() => onChange(selected.filter((s) => s !== key))}
                className="hover:text-red-600 font-bold leading-none"
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
      <input
        type="text"
        className="input-field text-sm w-full"
        placeholder={placeholder}
        value={query}
        onFocus={() => setOpen(true)}
        onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
      />
      {open && query.length > 0 && (
        <ul className="absolute z-40 mt-1 w-full max-h-48 overflow-y-auto bg-white border border-gray-200 rounded-lg shadow-lg">
          {available.length === 0 && (
            <li className="px-3 py-2 text-sm text-gray-400">—</li>
          )}
          {available.slice(0, 30).map((item) => (
            <li
              key={keyFn(item)}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => {
                onChange([...selected, keyFn(item)]);
                setQuery("");
              }}
              className="px-3 py-2 text-sm cursor-pointer hover:bg-primary/10"
            >
              {labelFn(item)}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function PlayerSearchMultiSelect({
  season,
  selected,
  onChange,
  placeholder,
}: {
  season: string;
  selected: string[];
  onChange: (sel: string[]) => void;
  placeholder: string;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  useEffect(() => {
    if (query.length < 2) { setResults([]); return; }
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      api.searchPlayers({ q: query, season, limit: 20 })
        .then((res) => setResults(res.players.map((p) => p.name)))
        .catch(() => setResults([]));
    }, 300);
    return () => clearTimeout(debounceRef.current);
  }, [query, season]);

  const available = results.filter((name) => !selected.includes(name));

  return (
    <div ref={containerRef} className="relative">
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-2">
          {selected.map((name) => (
            <span
              key={name}
              className="inline-flex items-center gap-1 bg-primary/10 text-primary-dark text-xs px-2 py-1 rounded-full"
            >
              {name}
              <button
                onClick={() => onChange(selected.filter((s) => s !== name))}
                className="hover:text-red-600 font-bold leading-none"
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
      <input
        type="text"
        className="input-field text-sm w-full"
        placeholder={placeholder}
        value={query}
        onFocus={() => setOpen(true)}
        onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
      />
      {open && query.length >= 2 && (
        <ul className="absolute z-40 mt-1 w-full max-h-48 overflow-y-auto bg-white border border-gray-200 rounded-lg shadow-lg">
          {available.length === 0 && (
            <li className="px-3 py-2 text-sm text-gray-400">—</li>
          )}
          {available.map((name) => (
            <li
              key={name}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => {
                onChange([...selected, name]);
                setQuery("");
              }}
              className="px-3 py-2 text-sm cursor-pointer hover:bg-primary/10"
            >
              {name}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function AdvancedFiltersPanel({
  lang,
  leagues,
  clubs,
  squad,
  season,
  filters,
  setFilters,
}: {
  lang: Lang;
  leagues: League[];
  clubs: Club[];
  squad: Player[] | null;
  season: string;
  filters: AdvancedFilters;
  setFilters: (f: AdvancedFilters) => void;
}) {
  const [open, setOpen] = useState(false);

  const clubNames = clubs.map((c) => c.name);

  return (
    <div className="border border-gray-200 rounded-lg">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 rounded-lg"
      >
        {t(lang, "filters_title")}
        <span className="text-xs">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="px-4 pb-4 space-y-4">
          {/* League filter */}
          <div>
            <label className="block text-xs font-medium mb-1">{t(lang, "league_filter")}</label>
            <p className="text-[10px] text-gray-400 mb-1">{t(lang, "league_filter_help")}</p>
            <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto">
              {leagues.map((l) => {
                const active = (filters.leagueFilter ?? []).includes(l.league_id);
                return (
                  <button
                    key={l.league_id}
                    onClick={() => {
                      const current = filters.leagueFilter ?? [];
                      const next = active
                        ? current.filter((id) => id !== l.league_id)
                        : [...current, l.league_id];
                      setFilters({ ...filters, leagueFilter: next.length ? next : null });
                    }}
                    className={`chip text-xs ${active ? "chip-active" : "chip-inactive"}`}
                  >
                    {l.name}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Banned clubs */}
          <div>
            <label className="block text-xs font-medium mb-1">{t(lang, "banned_clubs")}</label>
            <p className="text-[10px] text-gray-400 mb-1">{t(lang, "banned_clubs_help")}</p>
            <SearchableMultiSelect
              items={clubNames}
              selected={filters.bannedClubs ?? []}
              onChange={(sel) => setFilters({ ...filters, bannedClubs: sel.length ? sel : null })}
              placeholder={t(lang, "banned_clubs_placeholder")}
            />
          </div>

          {/* Banned players */}
          <div>
            <label className="block text-xs font-medium mb-1">{t(lang, "banned_players")}</label>
            <p className="text-[10px] text-gray-400 mb-1">{t(lang, "banned_players_help")}</p>
            <PlayerSearchMultiSelect
              season={season}
              selected={filters.bannedPlayers ?? []}
              onChange={(sel) => setFilters({ ...filters, bannedPlayers: sel.length ? sel : null })}
              placeholder={t(lang, "banned_players_placeholder")}
            />
          </div>

          {/* Horizon */}
          <div>
            <label className="block text-xs font-medium mb-1">{t(lang, "horizon_title")}</label>
            <p className="text-[10px] text-gray-400 mb-1">{t(lang, "horizon_help")}</p>
            <div className="flex gap-2">
              {HORIZONS.map((h) => (
                <button
                  key={h}
                  onClick={() => setFilters({ ...filters, horizon: h })}
                  className={`chip ${filters.horizon === h ? "chip-active" : "chip-inactive"}`}
                >
                  {t(lang, `horizon_${h}`)}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── main export ────────────────────────────────────────────────────────── */

export interface ConfigState {
  season: string;
  clubName: string;
  playersToSell: string[];
  buyCounts: BuyCounts | null;
  transferBudget: number;
  unlimited: boolean;
  approach: Approach;
  objective: Objective;
  simSpeed: SimSpeed;
  filters: AdvancedFilters;
}

interface Props {
  lang: Lang;
  seasons: string[];
  clubs: Club[];
  squad: Player[] | null;
  loadingSquad: boolean;
  onSeasonChange: (s: string) => void;
  onClubChange: (c: string) => void;
  onLoadSquad: () => void;
  onSimulate: (cfg: ConfigState) => void;
  simulating: boolean;
  season: string;
  clubName: string;
  hideSimConfig?: boolean;
}

export default function ConfigPanel({
  lang, seasons, clubs, squad, loadingSquad,
  onSeasonChange, onClubChange, onLoadSquad, onSimulate, simulating,
  season, clubName, hideSimConfig = false,
}: Props) {
  const [playersToSell, setPlayersToSell] = useState<string[]>([]);
  const [buyMode, setBuyMode] = useState<BuyMode>("total");
  const [exactCounts, setExactCounts] = useState<Record<string, number>>(
    { GK: 1, DEF: 1, MID: 1, ATT: 1 }
  );
  const [rangeCounts, setRangeCounts] = useState<Record<string, [number, number]>>(
    { GK: [0, 2], DEF: [0, 2], MID: [0, 2], ATT: [0, 2] }
  );
  const [totalCount, setTotalCount] = useState(5);
  const [budget, setBudget] = useState(0);
  const [unlimited, setUnlimited] = useState(false);
  const [approach, setApproach] = useState<Approach>("max_value");
  const [objective, setObjective] = useState<Objective>("net_benefit");
  const [simSpeed, setSimSpeed] = useState<SimSpeed>("standard");
  const [filters, setFilters] = useState<AdvancedFilters>({
    leagueFilter: null,
    bannedClubs: null,
    bannedPlayers: null,
    horizon: 1,
  });
  const [leagues, setLeagues] = useState<League[]>([]);
  const [sellRecs, setSellRecs] = useState<SellRecommendation[]>([]);
  const [loadingRecs, setLoadingRecs] = useState(false);

  useEffect(() => {
    if (hideSimConfig || !season) return;
    api.getLeagues(season).then(setLeagues).catch(() => setLeagues([]));
  }, [hideSimConfig, season]);

  useEffect(() => {
    if (hideSimConfig || !squad || !clubName || !season) {
      setSellRecs([]);
      return;
    }
    setLoadingRecs(true);
    api
      .getSellRecommendations(clubName, season)
      .then((res) => setSellRecs(res.peak_players))
      .catch(() => setSellRecs([]))
      .finally(() => setLoadingRecs(false));
  }, [hideSimConfig, squad, clubName, season]);

  const buildBuyCounts = (): BuyCounts | null => {
    if (buyMode === "exact") {
      const bc: BuyCounts = {};
      for (const pos of POS_ORDER) {
        const n = exactCounts[pos] ?? 1;
        bc[pos] = [n, n];
      }
      return bc;
    }
    if (buyMode === "range") {
      const bc: BuyCounts = {};
      for (const pos of POS_ORDER) bc[pos] = rangeCounts[pos] ?? [0, 2];
      return bc;
    }
    return { _formations: totalCombinations(totalCount) };
  };

  const handleSimulate = () => {
    onSimulate({
      season,
      clubName,
      playersToSell,
      buyCounts: buildBuyCounts(),
      transferBudget: budget,
      unlimited,
      approach,
      objective,
      simSpeed,
      filters,
    });
  };

  return (
    <div className="card space-y-6">
      <SeasonClubSelector
        lang={lang} seasons={seasons} clubs={clubs}
        season={season} clubName={clubName}
        onSeasonChange={onSeasonChange} onClubChange={onClubChange}
      />

      <button
        onClick={onLoadSquad}
        disabled={loadingSquad || !clubName}
        className="btn-secondary"
      >
        {loadingSquad ? t(lang, "loading_data") : t(lang, "load_data")}
      </button>

      {!squad && !loadingSquad && (
        <p className="text-xs text-gray-400">{t(lang, "load_data_hint")}</p>
      )}

      {squad && !hideSimConfig && (
        <>
          <div className="bg-secondary-light text-primary-dark text-sm font-medium px-4 py-2 rounded-lg border border-secondary/30">
            {t(lang, "data_loaded")} — {t(lang, "squad_loaded", { count: squad.length })}
          </div>

          <SellRecommendationsPanel
            lang={lang}
            recommendations={sellRecs}
            loading={loadingRecs}
            selected={playersToSell}
            onToggle={(id) =>
              setPlayersToSell((prev) =>
                prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
              )
            }
            onSelectAll={setPlayersToSell}
          />

          <SellSelection
            lang={lang} squad={squad}
            selected={playersToSell} onChange={setPlayersToSell}
          />

          <BuyCountsSelector
            lang={lang}
            buyMode={buyMode} setBuyMode={setBuyMode}
            exactCounts={exactCounts} setExactCounts={setExactCounts}
            rangeCounts={rangeCounts} setRangeCounts={setRangeCounts}
            totalCount={totalCount} setTotalCount={setTotalCount}
          />

          <BudgetInput
            lang={lang} budget={budget} setBudget={setBudget}
            unlimited={unlimited} setUnlimited={setUnlimited}
          />

          <ApproachSelector
            lang={lang} approach={approach} setApproach={setApproach}
          />

          <ObjectiveSelector
            lang={lang} objective={objective} setObjective={setObjective}
          />

          <SimSpeedSelector
            lang={lang} speed={simSpeed} setSpeed={setSimSpeed}
          />

          <AdvancedFiltersPanel
            lang={lang}
            leagues={leagues}
            clubs={clubs}
            squad={squad}
            season={season}
            filters={filters}
            setFilters={setFilters}
          />

          <button
            onClick={handleSimulate}
            disabled={simulating}
            className="btn-accent text-lg py-3"
          >
            {simulating ? t(lang, "simulating") : t(lang, "run_simulation")}
          </button>

          {simulating && (
            <p className="text-xs text-gray-400 text-center animate-pulse">
              {t(lang, "sim_may_take")}
            </p>
          )}
        </>
      )}
    </div>
  );
}
