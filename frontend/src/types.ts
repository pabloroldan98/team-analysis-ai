export type Lang = "es" | "en";

export interface Club {
  name: string;
  league: string;
  logo_url: string;
  total_market_value: number | null;
}

export interface Player {
  player_id: string;
  name: string;
  team: string;
  team_id: string;
  position: string;
  age: number | null;
  nationality: string;
  market_value: number | null;
  predicted_value: number | null;
  fair_price: number | null;
  img_url: string;
  on_loan: boolean;
  alternatives?: Player[];
}

export interface SoldPlayer {
  player_id: string;
  name: string;
  position: string;
  market_value: number | null;
  destination_team: string | null;
  was_sold: boolean;
  img_url: string;
}

export interface SimulationResult {
  club_name: string;
  season: string;
  initial_budget: number;
  sales_revenue: number;
  total_budget: number;
  players_sold: SoldPlayer[];
  formation_needed: number[];
  recommended_signings: Player[];
  recommended_formation: number[];
  total_signing_cost: number;
  total_predicted_value: number;
}

export interface SellRecommendation {
  player_id: string;
  name: string;
  position: string;
  age: number | null;
  market_value: number;
  predicted_value: number;
  fair_price: number | null;
  decline: number;
  decline_pct: number;
  img_url: string;
  on_loan?: boolean;
}

export interface SellRecommendations {
  peak_players: SellRecommendation[];
}

export type BuyMode = "exact" | "range" | "total";
export type Approach = "max_value" | "young_talents" | "veteran_players" | "balanced";
export type Objective = "smv" | "net_benefit" | "roi" | "growth_pct";
export type SimSpeed = "local" | "fast" | "standard";

export interface BuyCounts {
  [key: string]: [number, number] | number[][] | undefined;
  _formations?: number[][];
}

export interface League {
  league_id: string;
  name: string;
  country: string;
}

export interface AdvancedFilters {
  leagueFilter: string[] | null;
  bannedClubs: string[] | null;
  bannedPlayers: string[] | null;
  horizon: number;
}

export interface XGrowthPlayer {
  player_id: string;
  name: string;
  position: string;
  age: number | null;
  team: string;
  league: string;
  nationality: string;
  other_nationalities: string[];
  market_value: number;
  predicted_value: number;
  xgrowth: number;
  fair_price: number;
  net_benefit: number;
  roi: number;
  growth_pct: number;
  img_url: string;
  is_available: boolean;
}

export interface SimilarPlayer extends XGrowthPlayer {
  similarity: number;
}

export interface PlayerAnalysis {
  player_id: string;
  name: string;
  position: string;
  age: number | null;
  team: string;
  market_value: number;
  predicted_value: number;
  xgrowth: number;
  fair_price: number;
  similar_players: SimilarPlayer[];
  img_url: string;
}

export interface Analytics {
  xgrowth_ranking: XGrowthPlayer[];
  signing_analysis: PlayerAnalysis[];
}

export interface SearchPlayer {
  player_id: string;
  name: string;
  position: string;
  age: number | null;
  team: string;
  nationality: string;
  market_value: number;
  predicted_value: number | null;
  xgrowth: number | null;
  fair_price: number | null;
  img_url: string;
}

export interface SearchResults {
  players: SearchPlayer[];
  total: number;
}

export interface XGrowthRanges {
  age: [number, number];
  market_value: [number, number];
  predicted_value: [number, number];
  fair_price: [number, number];
  xgrowth: [number, number];
  net_benefit: [number, number];
  roi: [number, number];
  growth_pct: [number, number];
}

export interface XGrowthResults {
  players: XGrowthPlayer[];
  total: number;
  ranges: XGrowthRanges;
}
