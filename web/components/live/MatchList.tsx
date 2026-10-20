"use client";

import Link from "next/link";
import { useMemo } from "react";
import { IDLE_POLL_MS, LIVE_POLL_MS } from "@/lib/live/competitions";
import { usePoll } from "@/lib/live/usePoll";
import type { MatchView } from "@/lib/live/types";
import { Crest, StatusBadge, Updated } from "./Bits";

type Range = { kind: "today" } | { kind: "window"; backDays: number; forwardDays: number };
type Grouping = "competition" | "date";

const isLive = (m: MatchView) => m.state === "live" || m.state === "halftime";

function bounds(range: Range): { from: string; to: string } {
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  const from = new Date(start);
  const to = new Date(start);
  if (range.kind === "today") {
    to.setDate(to.getDate() + 1);
  } else {
    from.setDate(from.getDate() - range.backDays);
    to.setDate(to.getDate() + range.forwardDays + 1);
  }
  return { from: from.toISOString(), to: to.toISOString() };
}

export function MatchRow({ m }: { m: MatchView }) {
  const started = m.state !== "upcoming" && m.state !== "postponed";
  return (
    <Link href={`/matches/${m.id}`} className="grid grid-cols-[3.5rem_1fr_auto_1fr] items-center gap-2 px-3 py-2.5 hover:bg-panel2 sm:grid-cols-[4.5rem_1fr_auto_1fr]">
      <span className="text-center"><StatusBadge match={m} /></span>
      <span className="flex items-center justify-end gap-2 text-right text-sm">
        <span className="truncate">{m.home.short}</span>
        <Crest team={m.home} />
      </span>
      <span className="display min-w-[4rem] text-center text-lg font-semibold tabular-nums">
        {started ? `${m.homeScore ?? 0} - ${m.awayScore ?? 0}` : "v"}
      </span>
      <span className="flex items-center gap-2 text-sm">
        <Crest team={m.away} />
        <span className="truncate">{m.away.short}</span>
      </span>
    </Link>
  );
}

function Group({ title, href, matches }: { title: React.ReactNode; href?: string; matches: MatchView[] }) {
  return (
    <section className="card overflow-hidden">
      <h2 className="flex items-center justify-between border-b border-line px-3 py-2 text-xs font-semibold uppercase tracking-wide text-muted">
        {href ? <Link href={href} className="hover:text-ink">{title}</Link> : title}
      </h2>
      <div className="divide-y divide-line">{matches.map((m) => <MatchRow key={m.id} m={m} />)}</div>
    </section>
  );
}

export function MatchList({ range, competition, groupBy = "competition", emptyText = "No matches in this window." }: {
  range: Range;
  competition?: string;
  groupBy?: Grouping;
  emptyText?: string;
}) {
  const rangeKey = JSON.stringify(range);
  // Day bounds use the viewer's own time zone; the URL is only used in effects, so the server render never shows it.
  const url = useMemo(() => {
    const { from, to } = bounds(JSON.parse(rangeKey) as Range);
    const q = new URLSearchParams({ from, to });
    if (competition) q.set("competition", competition);
    return `/api/matches?${q}`;
  }, [rangeKey, competition]);

  const { data, error, fetchedAt, loading } = usePoll<MatchView[]>(url, (d) => (d?.some(isLive) ? LIVE_POLL_MS : IDLE_POLL_MS));

  const groups = useMemo(() => {
    const list = data ?? [];
    const map = new Map<string, { title: string; href?: string; matches: MatchView[] }>();
    for (const m of list) {
      const key = groupBy === "competition" ? m.competition.code : new Date(m.kickoff).toDateString();
      const entry = map.get(key) ?? {
        title: groupBy === "competition" ? m.competition.name : new Date(m.kickoff).toLocaleDateString([], { weekday: "long", day: "numeric", month: "long" }),
        href: groupBy === "competition" ? `/fixtures/${m.competition.code}` : undefined,
        matches: [],
      };
      entry.matches.push(m);
      map.set(key, entry);
    }
    // Competitions with a live match first.
    return [...map.values()].sort((a, b) => Number(b.matches.some(isLive)) - Number(a.matches.some(isLive)));
  }, [data, groupBy]);

  const liveFirst = (matches: MatchView[]) => (groupBy === "competition" ? [...matches].sort((a, b) => Number(isLive(b)) - Number(isLive(a))) : matches);

  return (
    <div className="space-y-4">
      <div className="flex justify-end"><Updated fetchedAt={fetchedAt} error={error} /></div>
      {loading && !data ? <p className="card p-6 text-sm text-muted">Loading matches</p> : null}
      {data && data.length === 0 ? <p className="card p-6 text-sm text-muted">{emptyText}</p> : null}
      {groups.map((g) => (
        <Group key={g.title} title={g.title} href={g.href} matches={liveFirst(g.matches)} />
      ))}
      {data?.some((m) => m.source === "delayed" && m.state !== "upcoming") ? (
        <p className="text-xs text-muted">Scores marked from the schedule feed can lag by a few minutes. Live matches update from the live feed.</p>
      ) : null}
    </div>
  );
}
