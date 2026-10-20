"use client";

import Link from "next/link";
import { IDLE_POLL_MS, LIVE_POLL_MS } from "@/lib/live/competitions";
import { usePoll } from "@/lib/live/usePoll";
import type { Lineup, MatchDetail, MatchEvent, MatchView } from "@/lib/live/types";
import { Crest, LocalTime, StatusBadge, Updated } from "./Bits";

const isLive = (m: MatchView) => m.state === "live" || m.state === "halftime";

function eventIcon(e: MatchEvent): string {
  if (e.type === "Goal") return e.detail === "Missed Penalty" ? "Missed pen" : e.detail === "Own Goal" ? "Own goal" : "Goal";
  if (e.type === "Card") return e.detail === "Red Card" ? "Red card" : "Yellow card";
  if (e.type === "subst") return "Sub";
  if (e.type === "Var") return "VAR";
  return e.type;
}

function eventText(e: MatchEvent): string {
  if (e.type === "subst") return `${e.assist ?? "?"} on, ${e.player ?? "?"} off`;
  const assist = e.type === "Goal" && e.assist ? ` (assist ${e.assist})` : "";
  const note = e.type === "Var" && e.detail ? ` ${e.detail}` : "";
  return `${e.player ?? "Unknown"}${assist}${note}`;
}

function Header({ m }: { m: MatchView }) {
  const started = m.state !== "upcoming" && m.state !== "postponed";
  return (
    <section className="card p-5 text-center">
      <p className="mb-3 text-xs text-muted">
        <Link href={`/fixtures/${m.competition.code}`} className="hover:text-ink">{m.competition.name}</Link>
        {m.matchday ? ` · Matchday ${m.matchday}` : ""} · <LocalTime iso={m.kickoff} mode="datetime" />
      </p>
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
        <div className="flex flex-col items-center gap-2"><Crest team={m.home} size={48} /><span className="text-sm font-semibold">{m.home.name}</span></div>
        <div>
          <div className="display text-5xl font-bold tabular-nums">{started ? `${m.homeScore ?? 0} - ${m.awayScore ?? 0}` : "v"}</div>
          <div className="mt-1"><StatusBadge match={m} /></div>
        </div>
        <div className="flex flex-col items-center gap-2"><Crest team={m.away} size={48} /><span className="text-sm font-semibold">{m.away.name}</span></div>
      </div>
    </section>
  );
}

/** What to say when there is nothing to show, by match status. `what` is "events" or "lineups". */
export function emptyMessage(m: MatchView, what: "events" | "lineups", hasOtherData: boolean): string {
  if (m.state === "upcoming") return what === "lineups" ? "Lineups usually appear about an hour before kick-off." : "Events appear here once the match starts.";
  if (m.state === "postponed") return "This match has not been played.";
  if (m.state === "live" || m.state === "halftime") return "Waiting for data.";
  if (m.detailStatus === "pending") return "Details for this match are queued and will appear here automatically.";
  if (m.detailStatus === "ok" && what === "events" && hasOtherData) return "No events were recorded for this match.";
  return "Event data isn't available for this match on our free data plan.";
}

function Events({ d }: { d: MatchDetail }) {
  const { match: m, events } = d;
  if (events.length === 0) {
    return <p className="card p-4 text-sm text-muted">{emptyMessage(m, "events", d.lineups.length > 0)}</p>;
  }
  return (
    <ol className="card divide-y divide-line">
      {events.map((e) => {
        const home = e.teamId === m.home.id;
        return (
          <li key={e.id} className="grid grid-cols-[3rem_1fr] items-baseline gap-2 px-3 py-2 text-sm">
            <span className="tabular-nums text-muted">{e.extraMinute ? `${e.minute}+${e.extraMinute}'` : `${e.minute}'`}</span>
            <span>
              <span className={`mr-2 text-xs font-semibold ${home ? "text-home" : "text-away"}`}>{eventIcon(e)}</span>
              {eventText(e)}
              <span className="ml-2 text-xs text-muted">{home ? m.home.short : m.away.short}</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function LineupCard({ lineup, name, empty }: { lineup: Lineup | undefined; name: string; empty: string }) {
  return (
    <div className="card p-3">
      <h3 className="mb-2 text-sm font-semibold">{name}{lineup?.formation ? <span className="ml-2 text-xs font-normal text-muted">{lineup.formation}</span> : null}</h3>
      {lineup ? (
        <>
          <ul className="space-y-1 text-sm">
            {lineup.starters.map((p, i) => (
              <li key={i} className="flex gap-2"><span className="w-6 text-right tabular-nums text-muted">{p.number ?? ""}</span>{p.name}</li>
            ))}
          </ul>
          {lineup.substitutes.length ? (
            <>
              <h4 className="mb-1 mt-3 text-xs uppercase tracking-wide text-muted">Substitutes</h4>
              <ul className="space-y-1 text-sm text-muted">
                {lineup.substitutes.map((p, i) => (
                  <li key={i} className="flex gap-2"><span className="w-6 text-right tabular-nums">{p.number ?? ""}</span>{p.name}</li>
                ))}
              </ul>
            </>
          ) : null}
          {lineup.coach ? <p className="mt-3 text-xs text-muted">Coach: {lineup.coach}</p> : null}
        </>
      ) : (
        <p className="text-sm text-muted">{empty}</p>
      )}
    </div>
  );
}

export function MatchLive({ id }: { id: number }) {
  const { data, error, fetchedAt, loading } = usePoll<MatchDetail>(`/api/matches/${id}`, (d) =>
    d && d.match.state === "finished" ? null : d && isLive(d.match) ? LIVE_POLL_MS : IDLE_POLL_MS,
  );
  if (loading && !data) return <p className="card p-6 text-sm text-muted">Loading match</p>;
  if (!data) return <p className="card p-6 text-sm text-danger">This match could not be loaded{error ? `: ${error}` : ""}.</p>;
  const m = data.match;
  return (
    <div className="space-y-4">
      <div className="flex justify-end"><Updated fetchedAt={fetchedAt} error={error} /></div>
      <Header m={m} />
      <section>
        <h2 className="display mb-2 text-xl font-semibold">Events</h2>
        <Events d={data} />
      </section>
      <section>
        <h2 className="display mb-2 text-xl font-semibold">Lineups</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <LineupCard lineup={data.lineups.find((l) => l.teamId === m.home.id)} name={m.home.name} empty={emptyMessage(m, "lineups", false)} />
          <LineupCard lineup={data.lineups.find((l) => l.teamId === m.away.id)} name={m.away.name} empty={emptyMessage(m, "lineups", false)} />
        </div>
      </section>
    </div>
  );
}
