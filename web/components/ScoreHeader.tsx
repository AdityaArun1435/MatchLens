import Link from "next/link";
import { ChevronLeft } from "lucide-react";
import { pct } from "@/lib/format";
import type { MatchSummary } from "@/lib/types";

function Stat({ label, home, away, h, a }: { label: string; home: string; away: string; h: number; a: number }) {
  const total = h + a || 1;
  return (
    <div className="min-w-0">
      <div className="mb-1 flex items-baseline justify-between text-sm tabular-nums">
        <b className="display text-lg text-home">{home}</b>
        <span className="text-xs text-muted">{label}</span>
        <b className="display text-lg text-away">{away}</b>
      </div>
      <div className="flex h-1.5 overflow-hidden rounded-full bg-line" aria-hidden>
        <span className="bg-home" style={{ width: `${(h / total) * 100}%` }} />
        <span className="bg-away" style={{ width: `${(a / total) * 100}%` }} />
      </div>
    </div>
  );
}

export function ScoreHeader({ summary }: { summary: MatchSummary }) {
  const { meta } = summary;
  const [h, a] = summary.final_score;
  const home = meta.home_team;
  const away = meta.away_team;
  const so = summary.shootout;
  const lines: string[] = [];
  if (summary.went_to_extra_time) lines.push(`After extra time (${summary.score_after_90[0]}-${summary.score_after_90[1]} after 90 minutes)`);
  if (so) lines.push(`${so.winner} won ${Math.max(...Object.values(so.score))}-${Math.min(...Object.values(so.score))} on penalties`);
  const date = new Date(`${meta.date}T12:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });

  return (
    <header className="card relative overflow-hidden p-5 sm:p-7" data-testid="score-header">
      <Link href="/" className="mb-4 inline-flex items-center gap-1 text-xs text-muted hover:text-ink">
        <ChevronLeft className="h-3.5 w-3.5" aria-hidden /> All matches
      </Link>
      <p className="text-xs uppercase tracking-[0.18em] text-muted">
        {meta.competition} {meta.season} · {meta.stage} · {date}
        {meta.stadium ? ` · ${meta.stadium}` : ""}
      </p>
      <div className="mt-4 grid grid-cols-[1fr_auto_1fr] items-center gap-3 sm:gap-6">
        <h1 className="display text-right text-2xl font-bold leading-tight text-home sm:text-5xl" data-testid="home-team">{home}</h1>
        <div className="display rounded-xl border border-line bg-bg/80 px-4 py-1.5 text-4xl font-bold tabular-nums sm:px-7 sm:text-6xl" data-testid="final-score" aria-label={`Final score ${h} ${a}`}>
          {h}<span className="mx-1.5 text-muted">-</span>{a}
        </div>
        <h1 className="display text-left text-2xl font-bold leading-tight text-away sm:text-5xl" data-testid="away-team">{away}</h1>
      </div>
      {lines.length > 0 && (
        <p className="mt-3 text-center text-sm text-ink/80" data-testid="result-detail">{lines.join(" · ")}</p>
      )}
      <div className="mt-6 grid gap-x-8 gap-y-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="xG" home={summary.total_xg[home].toFixed(2)} away={summary.total_xg[away].toFixed(2)} h={summary.total_xg[home]} a={summary.total_xg[away]} />
        <Stat label="Shots" home={String(summary.shots[home])} away={String(summary.shots[away])} h={summary.shots[home]} a={summary.shots[away]} />
        <Stat label="On target" home={String(summary.shots_on_target[home])} away={String(summary.shots_on_target[away])} h={summary.shots_on_target[home]} a={summary.shots_on_target[away]} />
        <Stat label="Possession" home={pct(summary.possession_share[home])} away={pct(summary.possession_share[away])} h={summary.possession_share[home]} a={summary.possession_share[away]} />
      </div>
    </header>
  );
}
