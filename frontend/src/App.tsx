import { useEffect, useState } from "react";
import type { Lang, Club, Player, League, Objective, SimulationResult } from "./types";
import { t } from "./i18n";
import { api } from "./api";
import Header from "./components/Header";
import Footer from "./components/Footer";
import ConfigPanel, { type ConfigState } from "./components/ConfigPanel";
import ResultsPanel from "./components/ResultsPanel";
import PlayerSearch from "./components/PlayerSearch";

/* ── Loading Overlay (pattern from knapsack_football_formations) ────────── */

function LoadingOverlay({
  visible, text, percent, subtitle,
}: {
  visible: boolean; text: string; percent: number; subtitle?: string;
}) {
  if (!visible) return null;
  return (
    <div className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center">
      <div className="flex flex-col items-center gap-3 min-w-[280px]">
        <div className="w-8 h-8 border-[3px] border-gray-500 border-t-secondary rounded-full animate-spin" />
        <span className="text-white text-sm">{text}</span>
        {subtitle && (
          <span className="text-gray-400 text-xs">{subtitle}</span>
        )}
        {percent > 0 && (
          <div className="w-full max-w-xs flex items-center gap-2.5">
            <div className="flex-1 h-2 bg-gray-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-secondary rounded-full transition-[width] duration-300"
                style={{ width: `${percent}%` }}
              />
            </div>
            <span className="text-xs text-gray-400 min-w-[36px] text-right">
              {percent}%
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── App ────────────────────────────────────────────────────────────────── */

type MainTab = "simulation" | "players";

export default function App() {
  const [lang, setLang] = useState<Lang>("es");

  const [seasons, setSeasons] = useState<string[]>([]);
  const [clubs, setClubs] = useState<Club[]>([]);
  const [season, setSeason] = useState("");
  const [clubName, setClubName] = useState("");

  const [squad, setSquad] = useState<Player[] | null>(null);
  const [loadingSquad, setLoadingSquad] = useState(false);
  const [leagues, setLeagues] = useState<League[]>([]);
  const [mainTab, setMainTab] = useState<MainTab>("simulation");

  const [result, setResult] = useState<SimulationResult | null>(null);
  const [lastObjective, setLastObjective] = useState<Objective>("smv");
  const [simulating, setSimulating] = useState(false);
  const [progressPct, setProgressPct] = useState(0);
  const [progressStep, setProgressStep] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getSeasons().then((s) => {
      setSeasons(s);
      if (s.length && !s.includes(season)) {
        setSeason(s[0]);
      }
    }).catch(console.error);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!season) return;
    api.getClubs(season).then((c) => {
      const sorted = [...c].sort((a, b) => a.name.localeCompare(b.name));
      setClubs(sorted);
      if (sorted.length && !sorted.find((x) => x.name === clubName)) {
        const rm = sorted.find((x) => x.name === "Real Madrid");
        setClubName(rm ? rm.name : sorted[0].name);
      }
    }).catch(console.error);
    api.getLeagues(season).then(setLeagues).catch(() => setLeagues([]));
  }, [season]);

  const handleSeasonChange = (s: string) => {
    setSeason(s);
    setSquad(null);
    setResult(null);
  };

  const handleClubChange = (c: string) => {
    setClubName(c);
    setSquad(null);
    setResult(null);
  };

  const handleLoadSquad = async () => {
    setLoadingSquad(true);
    setError(null);
    setSquad(null);
    setResult(null);
    try {
      const players = await api.loadSquad(clubName, season);
      setSquad(players);
    } catch (err: any) {
      setError(err.message || "Error loading squad");
    } finally {
      setLoadingSquad(false);
    }
  };

  const handleSimulate = async (cfg: ConfigState) => {
    setSimulating(true);
    setProgressPct(0);
    setProgressStep("");
    setError(null);
    setResult(null);
    setLastObjective(cfg.objective);
    try {
      const res = await api.simulateStream(
        {
          clubName: cfg.clubName,
          season: cfg.season,
          transferBudget: cfg.transferBudget,
          unlimited: cfg.unlimited,
          playersToSell: cfg.playersToSell,
          buyCounts: cfg.buyCounts,
          approach: cfg.approach,
          objective: cfg.objective,
          simSpeed: cfg.simSpeed,
          filters: cfg.filters,
        },
        (ev) => {
          setProgressPct(ev.percent);
          setProgressStep(ev.step);
        },
      );
      setResult(res);
    } catch (err: any) {
      setError(err.message || "Simulation failed");
    } finally {
      setSimulating(false);
      setProgressPct(0);
    }
  };

  const loadingText = progressStep
    ? t(lang, progressStep)
    : t(lang, "simulating");

  return (
    <div className="min-h-screen flex flex-col">
      <Header lang={lang} onLangChange={setLang} />

      <LoadingOverlay
        visible={loadingSquad || simulating}
        text={loadingSquad ? t(lang, "loading_data") : loadingText}
        percent={loadingSquad ? 0 : progressPct}
        subtitle={simulating ? t(lang, "sim_may_take") : undefined}
      />

      <main className="flex-1 max-w-6xl mx-auto w-full px-4 py-6 space-y-6">
        {/* Main tab bar — always visible */}
        <div className="flex gap-1 border-b border-gray-200">
          {(["simulation", "players"] as const).map((key) => (
            <button
              key={key}
              onClick={() => setMainTab(key)}
              className={`px-4 py-2 text-sm font-semibold border-b-2 transition-colors ${
                mainTab === key
                  ? "border-primary text-primary-dark"
                  : "border-transparent text-gray-400 hover:text-gray-600"
              }`}
            >
              {t(lang, `main_tab_${key}`)}
            </button>
          ))}
        </div>

        {/* ─── Simulation tab ────────────────────────────────────── */}
        <div className={mainTab !== "simulation" ? "hidden" : "space-y-6"}>
          <ConfigPanel
            lang={lang}
            seasons={seasons}
            clubs={clubs}
            squad={squad}
            loadingSquad={loadingSquad}
            onSeasonChange={handleSeasonChange}
            onClubChange={handleClubChange}
            onLoadSquad={handleLoadSquad}
            onSimulate={handleSimulate}
            simulating={simulating}
            season={season}
            clubName={clubName}
          />

          {error && (
            <div className="bg-danger-light border border-danger text-danger-dark text-sm p-3 rounded-lg">
              {error}
            </div>
          )}
          {result && squad && (
            <ResultsPanel
              lang={lang}
              result={result}
              clubs={clubs}
              squad={squad}
              objective={lastObjective}
            />
          )}
        </div>

        {/* ─── Players tab ───────────────────────────────────────── */}
        <div className={mainTab !== "players" ? "hidden" : "space-y-6"}>
          <ConfigPanel
            lang={lang}
            seasons={seasons}
            clubs={clubs}
            squad={squad}
            loadingSquad={loadingSquad}
            onSeasonChange={handleSeasonChange}
            onClubChange={handleClubChange}
            onLoadSquad={handleLoadSquad}
            onSimulate={handleSimulate}
            simulating={simulating}
            season={season}
            clubName={clubName}
            hideSimConfig
          />

          {squad && (
            <PlayerSearch lang={lang} season={season} clubName={clubName} leagues={leagues} />
          )}
        </div>
      </main>

      <Footer lang={lang} />
    </div>
  );
}
