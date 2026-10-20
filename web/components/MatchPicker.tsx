"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getHealth, getMatches } from "@/lib/api";
import type { Health, MatchListItem } from "@/lib/types";
import { ErrorNotice, StatusPill } from "./Bits";

function MatchCard({ m }: { m: MatchListItem }) {
  const date = new Date(`${m.date}T12:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  const badges = [m.went_to_extra_time ? "After extra time" : null, m.shootout_winner ? `${m.shootout_winner} on penalties` : null].filter(Boolean);
  return (
    <Link
      href={`/classic/match/${m.match_id}`}
      data-testid={`match-card-${m.match_id}`}
      className="card group block p-5 transition-colors hover:border-accent/50"
    >
      <p className="text-[11px] uppercase tracking-[0.18em] text-muted">
        {m.competition} {m.season} · {m.stage}
      </p>
      <div className="mt-5 grid grid-cols-[1fr_auto_1fr] items-center gap-3">
        <span className="display text-right text-xl font-bold leading-tight text-home sm:text-2xl">{m.home_team}</span>
        <span className="display rounded-lg border border-line bg-bg/80 px-3 py-1 text-3xl font-bold tabular-nums">
          {m.home_score}<span className="mx-1 text-muted">-</span>{m.away_score}
        </span>
        <span className="display text-left text-xl font-bold leading-tight text-away sm:text-2xl">{m.away_team}</span>
      </div>
      <div className="mt-5 flex flex-wrap items-center gap-2 text-xs text-muted">
        <span>{date}</span>
        {badges.map((b) => (
          <span key={b} className="rounded-full border border-line px-2 py-0.5">{b}</span>
        ))}
        <span className="ml-auto text-accent opacity-0 transition-opacity group-hover:opacity-100">Open match →</span>
      </div>
    </Link>
  );
}

export function MatchPicker() {
  const [matches, setMatches] = useState<MatchListItem[] | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let live = true;
    getMatches().then((m) => live && setMatches(m)).catch((e) => live && setError(e));
    getHealth().then((h) => live && (setHealth(h), setHealthError(false))).catch(() => live && setHealthError(true));
    return () => {
      live = false;
    };
  }, [attempt]);

  return (
    <main className="mx-auto max-w-5xl p-4 pb-16 sm:p-8">
      <div className="mb-10 flex flex-wrap items-start justify-between gap-4 pt-4">
        <div>
          <h1 className="display text-5xl font-bold tracking-wide sm:text-6xl">
            Match<span className="text-accent">Lens</span>
          </h1>
          <p className="mt-3 max-w-xl text-ink/80">
            Football recaps written by a model on this computer, and checked line by line against the match data. Pick a match.
          </p>
        </div>
        <StatusPill health={health} error={healthError} />
      </div>

      {error ? (
        <ErrorNotice error={error} onRetry={() => { setError(null); setAttempt((n) => n + 1); }} />
      ) : !matches ? (
        <div className="grid gap-4 md:grid-cols-2" aria-busy>
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton h-40" />
          ))}
        </div>
      ) : matches.length === 0 ? (
        <p className="rounded-xl border border-line p-6 text-muted">No matches yet. Run <code>python scripts/fetch_data.py</code>.</p>
      ) : (
        <div className="grid gap-4 md:grid-cols-2" data-testid="match-list">
          {matches.map((m) => (
            <MatchCard key={m.match_id} m={m} />
          ))}
        </div>
      )}
      <p className="mt-10 text-xs text-muted">Data: StatsBomb Open Data. Hindi and Tamil are machine-translated from the checked English.</p>
    </main>
  );
}
