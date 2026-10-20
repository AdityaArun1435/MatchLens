export type MatchState = "upcoming" | "live" | "halftime" | "finished" | "postponed";

export interface TeamRef {
  id: number;
  name: string;
  short: string;
  tla: string | null;
  crest: string | null;
}

export interface CompetitionRef {
  code: string;
  name: string;
  emblem: string | null;
}

export interface MatchView {
  id: number;
  kickoff: string;
  competition: CompetitionRef;
  matchday: number | null;
  stage: string | null;
  home: TeamRef;
  away: TeamRef;
  homeScore: number | null;
  awayScore: number | null;
  state: MatchState;
  /** Minute with a prime mark, for example 67' or 45+2', only when the live feed provided it. */
  minute: string | null;
  /** `live`: from the live feed. `delayed`: from football-data.org, which is delayed on the free plan. */
  source: "live" | "delayed";
  updatedAt: string;
}

export interface MatchEvent {
  id: number;
  minute: number;
  extraMinute: number | null;
  type: string;
  detail: string | null;
  teamId: number | null;
  player: string | null;
  assist: string | null;
}

export interface LineupPlayer {
  name: string;
  number: number | null;
  pos: string | null;
  grid: string | null;
}

export interface Lineup {
  teamId: number;
  formation: string | null;
  coach: string | null;
  starters: LineupPlayer[];
  substitutes: LineupPlayer[];
}

export interface MatchDetail {
  match: MatchView;
  events: MatchEvent[];
  lineups: Lineup[];
}

export interface StandingRow {
  position: number;
  team: TeamRef;
  played: number;
  won: number;
  draw: number;
  lost: number;
  points: number;
  goalsFor: number;
  goalsAgainst: number;
  goalDifference: number;
  form: string | null;
}

export interface StandingTable {
  group: string;
  rows: StandingRow[];
}

export interface Standings {
  competition: CompetitionRef | null;
  season: number | null;
  tables: StandingTable[];
  updatedAt: string | null;
}
