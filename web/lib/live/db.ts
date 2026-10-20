import type {
  CompetitionRef,
  DetailStatus,
  Lineup,
  MatchDetail,
  MatchEvent,
  MatchState,
  MatchView,
  StandingRow,
  Standings,
  TeamRef,
} from "./types";

/**
 * Server-side reads from Supabase with the publishable key and row-level security (public read only).
 * Visitors never reach a data source: the scheduled refresh fills these tables.
 */
function config() {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_ANON_KEY;
  if (!url || !key) throw new Error("SUPABASE_URL and SUPABASE_ANON_KEY are not set");
  return { url, key };
}

async function select<T>(table: string, params: Record<string, string>): Promise<T[]> {
  const { url, key } = config();
  const q = new URLSearchParams(params);
  const res = await fetch(`${url}/rest/v1/${table}?${q}`, {
    headers: { apikey: key, Authorization: `Bearer ${key}` },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Supabase ${table}: ${res.status}`);
  return (await res.json()) as T[];
}

const TEAM = "id,name,short_name,tla,crest";
const FIXTURE_SELECT =
  `*,home:teams!fixtures_home_team_id_fkey(${TEAM}),away:teams!fixtures_away_team_id_fkey(${TEAM}),` +
  "competition:competitions(code,name,emblem),live:live_state(*)";

interface TeamRow {
  id: number;
  name: string;
  short_name: string | null;
  tla: string | null;
  crest: string | null;
}
interface LiveRow {
  status_short: string;
  elapsed: number | null;
  extra: number | null;
  home_goals: number | null;
  away_goals: number | null;
  updated_at: string;
}
export interface FixtureRow {
  id: number;
  utc_date: string;
  status: string;
  matchday: number | null;
  stage: string | null;
  home_score: number | null;
  away_score: number | null;
  updated_at: string;
  detail_status: Exclude<DetailStatus, "pending"> | null;
  home: TeamRow | null;
  away: TeamRow | null;
  competition: CompetitionRef | null;
  live: LiveRow | null;
}

const LIVE_SHORT = new Set(["1H", "2H", "ET", "BT", "P", "LIVE", "SUSP", "INT"]);
const FINAL_SHORT = new Set(["FT", "AET", "PEN", "AWD", "WO"]);
const POSTPONED_SHORT = new Set(["PST", "CANC", "ABD"]);

const toTeam = (t: TeamRow | null): TeamRef =>
  t
    ? { id: t.id, name: t.name, short: t.short_name ?? t.name, tla: t.tla, crest: t.crest }
    : { id: 0, name: "To be decided", short: "TBD", tla: null, crest: null };

export function minuteLabel(elapsed: number | null, extra: number | null): string | null {
  if (elapsed == null) return null;
  return extra ? `${elapsed}+${extra}'` : `${elapsed}'`;
}

/** Merge the delayed football-data.org row with the live feed row into what the site shows. */
export function toMatchView(f: FixtureRow): MatchView {
  const live = f.live;
  let state: MatchState;
  if (f.status === "FINISHED" || f.status === "AWARDED" || (live && FINAL_SHORT.has(live.status_short))) state = "finished";
  else if (["POSTPONED", "CANCELLED", "SUSPENDED"].includes(f.status) || (live && POSTPONED_SHORT.has(live.status_short))) state = "postponed";
  else if (live?.status_short === "HT") state = "halftime";
  else if (live && LIVE_SHORT.has(live.status_short)) state = "live";
  else if (f.status === "IN_PLAY") state = "live";
  else if (f.status === "PAUSED") state = "halftime";
  else state = "upcoming";

  // The live row wins unless the match is over and the official result is already in.
  const useLive = live != null && live.home_goals != null && state !== "upcoming" && !(state === "finished" && f.home_score != null);
  return {
    id: f.id,
    kickoff: f.utc_date,
    competition: f.competition ?? { code: "", name: "", emblem: null },
    matchday: f.matchday,
    stage: f.stage,
    home: toTeam(f.home),
    away: toTeam(f.away),
    homeScore: useLive ? live.home_goals : f.home_score,
    awayScore: useLive ? live.away_goals : f.away_score,
    state,
    detailStatus: f.detail_status ?? "pending",
    minute: state === "live" && live ? minuteLabel(live.elapsed, live.extra) : null,
    source: useLive ? "live" : "delayed",
    updatedAt: useLive ? live.updated_at : f.updated_at,
  };
}

export async function getMatches(from: string, to: string, competition?: string): Promise<MatchView[]> {
  const params: Record<string, string> = {
    select: competition ? FIXTURE_SELECT.replace("competition:competitions", "competition:competitions!inner") : FIXTURE_SELECT,
    and: `(utc_date.gte.${from},utc_date.lt.${to})`,
    order: "utc_date.asc",
    limit: "300",
  };
  if (competition) params["competition.code"] = `eq.${competition}`;
  const rows = await select<FixtureRow>("fixtures", params);
  return rows.map(toMatchView);
}

export async function getMatchDetail(id: number): Promise<MatchDetail | null> {
  const [rows, events, lineups] = await Promise.all([
    select<FixtureRow>("fixtures", { select: FIXTURE_SELECT, id: `eq.${id}` }),
    select<{
      id: number;
      minute: number;
      extra_minute: number | null;
      type: string;
      detail: string | null;
      team_id: number | null;
      player_name: string | null;
      assist_name: string | null;
    }>("events", { fixture_id: `eq.${id}`, order: "minute.asc,extra_minute.asc.nullsfirst,id.asc" }),
    select<{ team_id: number; formation: string | null; coach: string | null; starters: Lineup["starters"]; substitutes: Lineup["substitutes"] }>(
      "lineups",
      { fixture_id: `eq.${id}` },
    ),
  ]);
  if (rows.length === 0) return null;
  const mapped: MatchEvent[] = events.map((e) => ({
    id: e.id,
    minute: e.minute,
    extraMinute: e.extra_minute,
    type: e.type,
    detail: e.detail,
    teamId: e.team_id,
    player: e.player_name,
    assist: e.assist_name,
  }));
  return {
    match: toMatchView(rows[0]),
    events: mapped,
    lineups: lineups.map((l) => ({ teamId: l.team_id, formation: l.formation, coach: l.coach, starters: l.starters, substitutes: l.substitutes })),
  };
}

export async function getCompetitions(): Promise<(CompetitionRef & { id: number })[]> {
  return select("competitions", { select: "id,code,name,emblem", order: "name.asc" });
}

export async function getStandings(code: string): Promise<Standings> {
  const comps = await select<CompetitionRef & { id: number; season: number | null }>("competitions", {
    select: "id,code,name,emblem,season",
    code: `eq.${code}`,
  });
  if (comps.length === 0) return { competition: null, season: null, tables: [], updatedAt: null };
  const comp = comps[0];
  interface Row {
    grp: string;
    position: number;
    played: number;
    won: number;
    draw: number;
    lost: number;
    points: number;
    goals_for: number;
    goals_against: number;
    goal_difference: number;
    form: string | null;
    updated_at: string;
    team: TeamRow;
  }
  const rows = await select<Row>("standings", {
    select: `*,team:teams(${TEAM})`,
    competition_id: `eq.${comp.id}`,
    season: `eq.${comp.season ?? 0}`,
    type: "eq.TOTAL",
    order: "grp.asc,position.asc",
  });
  const groups = new Map<string, StandingRow[]>();
  for (const r of rows) {
    const list = groups.get(r.grp) ?? [];
    list.push({
      position: r.position,
      team: toTeam(r.team),
      played: r.played,
      won: r.won,
      draw: r.draw,
      lost: r.lost,
      points: r.points,
      goalsFor: r.goals_for,
      goalsAgainst: r.goals_against,
      goalDifference: r.goal_difference,
      form: r.form,
    });
    groups.set(r.grp, list);
  }
  return {
    competition: { code: comp.code, name: comp.name, emblem: comp.emblem },
    season: comp.season,
    tables: [...groups.entries()].map(([group, list]) => ({ group, rows: list })),
    updatedAt: rows[0]?.updated_at ?? null,
  };
}
