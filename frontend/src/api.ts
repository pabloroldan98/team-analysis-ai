import type { Club, Player, SimulationResult, BuyCounts, Approach, Objective, SimSpeed, SellRecommendations, League, AdvancedFilters, Analytics, SearchResults, XGrowthResults } from "./types";

const BASE = "";

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, init);
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(detail);
  }
  return res.json();
}

export interface ProgressEvent {
  percent: number;
  step: string;
}

export const api = {
  getSeasons: () => json<string[]>("/api/seasons"),

  getClubs: (season: string) =>
    json<Club[]>(`/api/clubs?season=${encodeURIComponent(season)}`),

  getLeagues: (season: string) =>
    json<League[]>(`/api/leagues?season=${encodeURIComponent(season)}`),

  getNationalities: () => json<string[]>("/api/nationalities"),

  loadSquad: (clubName: string, season: string) =>
    json<Player[]>("/api/load-squad", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ club_name: clubName, season }),
    }),

  getSellRecommendations: (clubName: string, season: string) =>
    json<SellRecommendations>(
      `/api/sell-recommendations?club_name=${encodeURIComponent(clubName)}&season=${encodeURIComponent(season)}`
    ),

  /** Synchronous simulate (no progress). */
  simulate: (params: {
    clubName: string;
    season: string;
    transferBudget: number;
    unlimited: boolean;
    playersToSell: string[];
    buyCounts: BuyCounts | null;
    approach: Approach;
    objective: Objective;
    simSpeed: SimSpeed;
    filters: AdvancedFilters;
  }) =>
    json<SimulationResult>("/api/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        club_name: params.clubName,
        season: params.season,
        transfer_budget: params.transferBudget,
        unlimited: params.unlimited,
        players_to_sell: params.playersToSell,
        buy_counts: params.buyCounts,
        approach: params.approach,
        objective: params.objective,
        sim_speed: params.simSpeed,
        league_filter: params.filters.leagueFilter,
        banned_clubs: params.filters.bannedClubs,
        banned_players: params.filters.bannedPlayers,
        horizon: params.filters.horizon,
      }),
    }),

  /**
   * SSE simulate — streams progress events, then the final result.
   * Inspired by knapsack_football_formations/api.py calculate-stream.
   */
  simulateStream: async (
    params: {
      clubName: string;
      season: string;
      transferBudget: number;
      unlimited: boolean;
      playersToSell: string[];
      buyCounts: BuyCounts | null;
      approach: Approach;
      objective: Objective;
      simSpeed: SimSpeed;
      filters: AdvancedFilters;
    },
    onProgress: (ev: ProgressEvent) => void,
  ): Promise<SimulationResult> => {
    const res = await fetch(`${BASE}/api/simulate-stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        club_name: params.clubName,
        season: params.season,
        transfer_budget: params.transferBudget,
        unlimited: params.unlimited,
        players_to_sell: params.playersToSell,
        buy_counts: params.buyCounts,
        approach: params.approach,
        objective: params.objective,
        sim_speed: params.simSpeed,
        league_filter: params.filters.leagueFilter,
        banned_clubs: params.filters.bannedClubs,
        banned_players: params.filters.bannedPlayers,
        horizon: params.filters.horizon,
      }),
    });

    if (!res.ok) {
      const detail = await res.text().catch(() => res.statusText);
      throw new Error(detail);
    }

    const reader = res.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let result: SimulationResult | null = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data: ")) continue;
        const payload = JSON.parse(trimmed.slice(6));

        if (payload.type === "progress") {
          onProgress({ percent: payload.percent, step: payload.step });
        } else if (payload.type === "result") {
          result = payload.data as SimulationResult;
        } else if (payload.type === "error") {
          throw new Error(payload.detail);
        }
      }
    }

    if (!result) throw new Error("No result received from stream");
    return result;
  },

  searchPlayers: (params: {
    q?: string; season?: string; position?: string;
    minValue?: number; maxValue?: number;
    minAge?: number; maxAge?: number; limit?: number;
  }) => {
    const sp = new URLSearchParams();
    if (params.q) sp.set("q", params.q);
    if (params.season) sp.set("season", params.season);
    if (params.position) sp.set("position", params.position);
    if (params.minValue) sp.set("min_value", String(params.minValue));
    if (params.maxValue) sp.set("max_value", String(params.maxValue));
    if (params.minAge) sp.set("min_age", String(params.minAge));
    if (params.maxAge) sp.set("max_age", String(params.maxAge));
    sp.set("limit", String(params.limit ?? 50));
    return json<SearchResults>(`/api/search-players?${sp.toString()}`);
  },

  getAnalytics: (clubName: string, season: string) =>
    json<Analytics>(
      `/api/analytics?club_name=${encodeURIComponent(clubName)}&season=${encodeURIComponent(season)}`
    ),

  getXGrowth: (params: {
    season?: string; position?: string;
    minValue?: number; maxValue?: number;
    minAge?: number; maxAge?: number;
    clubName?: string; limit?: number;
    horizon?: number;
    leagueFilter?: string[];
    excludeTopN?: number;
    minMarketValue?: number;
    sortBy?: string;
    fAgeMin?: number; fAgeMax?: number;
    fMvMin?: number; fMvMax?: number;
    fPvMin?: number; fPvMax?: number;
    fFpMin?: number; fFpMax?: number;
    fXgMin?: number; fNbMin?: number;
    fRoiMin?: number; fGpMin?: number;
    teamQuery?: string;
    nationalityFilter?: string[];
    includeSecondNationality?: boolean;
  }) => {
    const sp = new URLSearchParams();
    if (params.season) sp.set("season", params.season);
    if (params.position) sp.set("position", params.position);
    if (params.minValue) sp.set("min_value", String(params.minValue));
    if (params.maxValue) sp.set("max_value", String(params.maxValue));
    if (params.minAge) sp.set("min_age", String(params.minAge));
    if (params.maxAge) sp.set("max_age", String(params.maxAge));
    if (params.clubName) sp.set("club_name", params.clubName);
    if (params.horizon && params.horizon > 1) sp.set("horizon", String(params.horizon));
    if (params.leagueFilter?.length) sp.set("league_filter", params.leagueFilter.join(","));
    if (params.excludeTopN) sp.set("exclude_top_n", String(params.excludeTopN));
    if (params.minMarketValue) sp.set("min_market_value", String(params.minMarketValue));
    if (params.sortBy) sp.set("sort_by", params.sortBy);
    if (params.fAgeMin != null) sp.set("f_age_min", String(params.fAgeMin));
    if (params.fAgeMax != null) sp.set("f_age_max", String(params.fAgeMax));
    if (params.fMvMin != null) sp.set("f_mv_min", String(params.fMvMin));
    if (params.fMvMax != null) sp.set("f_mv_max", String(params.fMvMax));
    if (params.fPvMin != null) sp.set("f_pv_min", String(params.fPvMin));
    if (params.fPvMax != null) sp.set("f_pv_max", String(params.fPvMax));
    if (params.fFpMin != null) sp.set("f_fp_min", String(params.fFpMin));
    if (params.fFpMax != null) sp.set("f_fp_max", String(params.fFpMax));
    if (params.fXgMin != null) sp.set("f_xg_min", String(params.fXgMin));
    if (params.fNbMin != null) sp.set("f_nb_min", String(params.fNbMin));
    if (params.fRoiMin != null) sp.set("f_roi_min", String(params.fRoiMin));
    if (params.fGpMin != null) sp.set("f_gp_min", String(params.fGpMin));
    if (params.teamQuery) sp.set("team_query", params.teamQuery);
    if (params.nationalityFilter?.length) sp.set("nationality_filter", params.nationalityFilter.join(","));
    if (params.includeSecondNationality) sp.set("include_second_nationality", "true");
    sp.set("limit", String(params.limit ?? 50));
    return json<XGrowthResults>(`/api/xgrowth?${sp.toString()}`);
  },

  aiSummary: (apiKey: string, language: string, result?: SimulationResult) =>
    json<{ summary: string }>("/api/ai-summary", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: apiKey, language, result_data: result ?? null }),
    }),
};
