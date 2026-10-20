"use client";

import { ArrowLeft, ArrowLeftRight, BookOpen, Flag, Pause, Play, RotateCcw, Square, Target } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { peekExplanation } from "@/lib/api";
import { SPEEDS, useLiveReplay, type LiveEvent, type Speed } from "@/lib/live";
import type { Audience, Language, MatchSummary } from "@/lib/types";
import { MomentsTimeline } from "./MomentsTimeline";
import { XgChart } from "./XgChart";

const OUTCOME: Record<string, string> = {
  Goal: "goal",
  Saved: "saved",
  "Saved to Post": "saved onto the post",
  "Saved Off Target": "saved, off target",
  "Off T": "off target",
  Blocked: "blocked",
  Post: "hit the post",
  Wayward: "wayward",
};

function describe(e: LiveEvent, periodLabel: (p: number) => string): { text: string; tone: string; icon: "shot" | "goal" | "sub" | "card" | "flag" } | null {
  const who = e.player ? `${e.player}${e.team ? ` (${e.team})` : ""}` : (e.team ?? "");
  const card = e.detail.card;
  if (card) return { text: `${who} shown a ${card.toLowerCase().replace(" card", "")} card`, tone: card === "Yellow Card" ? "text-amber" : "text-danger", icon: "card" };
  switch (e.kind) {
    case "Shot": {
      if (!e.in_play) return { text: `Shootout kick: ${who} ${e.outcome === "Goal" ? "scored" : (OUTCOME[e.outcome ?? ""] ?? "missed")}`, tone: "text-accent", icon: "shot" };
      if (e.outcome === "Goal") return { text: `GOAL: ${who}${e.detail.shot_type === "Penalty" ? " (penalty)" : ""}${e.xg != null ? `, xG ${e.xg.toFixed(2)}` : ""}`, tone: "text-accent font-semibold", icon: "goal" };
      return { text: `${who} shot, ${OUTCOME[e.outcome ?? ""] ?? (e.outcome ?? "").toLowerCase()}${e.xg != null ? `, xG ${e.xg.toFixed(2)}` : ""}`, tone: "text-ink", icon: "shot" };
    }
    case "Own Goal For":
      return { text: `Own goal, credited to ${e.team}`, tone: "text-accent font-semibold", icon: "goal" };
    case "Substitution":
      return { text: `${e.team} substitution: ${e.detail.replacement_display_name ?? e.detail.replacement ?? "?"} on for ${e.player}`, tone: "text-muted", icon: "sub" };
    case "Half Start":
      return { text: `Start of ${periodLabel(e.period)}`, tone: "text-muted", icon: "flag" };
    case "Half End":
      return { text: `End of ${periodLabel(e.period)}`, tone: "text-muted", icon: "flag" };
    default:
      return null;
  }
}

const ICONS = { shot: Target, goal: Target, sub: ArrowLeftRight, card: Square, flag: Flag };

export function LiveMode({
  matchId,
  summary,
  audience,
  language,
  onClose,
  onReadRecap,
}: {
  matchId: number;
  summary: MatchSummary;
  audience: Audience;
  language: Language;
  onClose: () => void;
  onReadRecap: () => void;
}) {
  const { state, send, restart } = useLiveReplay(matchId, true, 10);
  const home = summary.meta.home_team;
  const away = summary.meta.away_team;
  const duration = state.hello?.duration ?? 1;
  const [scrub, setScrub] = useState<number | null>(null);
  const seekTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const periodLabel = (p: number) => state.hello?.periods.find((x) => x.period === p)?.label ?? `period ${p}`;

  const chartIndex = useMemo(
    () => summary.xg_timeline.findIndex((p) => p.period === state.period && p.minute === state.minute),
    [summary.xg_timeline, state.period, state.minute],
  );
  const goals = useMemo(() => state.moments.filter((m) => m.type === "goal"), [state.moments]);
  const ticker = useMemo(
    () => [...state.events].reverse().map((e) => ({ e, d: describe(e, periodLabel) })).filter((x) => x.d !== null).slice(0, 12),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [state.events, state.hello],
  );

  // A cached explanation for the moment in the caption, if one exists. Replay never asks the model to write one.
  const [why, setWhy] = useState<{ id: string; text: string } | null>(null);
  const captionMoment = state.caption?.momentId ?? null;
  useEffect(() => {
    if (!captionMoment) return;
    const ctl = new AbortController();
    peekExplanation(matchId, captionMoment, audience, language, ctl.signal)
      .then((hit) => hit && setWhy({ id: captionMoment, text: hit.explanation.why_it_mattered }))
      .catch(() => undefined);
    return () => ctl.abort();
  }, [captionMoment, matchId, audience, language]);

  function onScrub(v: number) {
    setScrub(v);
    if (seekTimer.current) clearTimeout(seekTimer.current);
    seekTimer.current = setTimeout(() => {
      send({ cmd: "seek", t: v });
      setScrub(null);
    }, 150);
  }

  const value = scrub ?? state.t;
  const [h, a] = state.score;
  const live = state.status === "live" && !state.ended;
  const failed = state.status === "error" || (state.status === "closed" && !state.ended);

  return (
    <div className="space-y-4" data-testid="live-mode">
      <section className="card p-4 sm:p-6" aria-label="Live scoreboard">
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" onClick={onClose} data-testid="live-close" className="inline-flex items-center gap-1 text-xs text-muted hover:text-ink">
            <ArrowLeft className="h-3.5 w-3.5" aria-hidden /> Back to the match
          </button>
          <span
            data-testid="live-status"
            className={`ml-auto inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wider ${
              state.ended ? "border-line text-muted" : state.paused ? "border-amber/50 text-amber" : "border-accent/50 text-accent"
            }`}
          >
            <span className={`h-2 w-2 rounded-full ${live && !state.paused ? "animate-pulse bg-accent" : state.paused ? "bg-amber" : "bg-muted"}`} />
            {state.ended ? "Full time" : state.paused ? "Paused" : state.status === "connecting" ? "Connecting" : "Replay"}
          </span>
        </div>

        <div className="mt-4 grid grid-cols-[1fr_auto_1fr] items-center gap-3 sm:gap-6">
          <p className="display text-right text-xl font-bold text-home sm:text-4xl">{home}</p>
          <div className="text-center">
            <div className="display rounded-xl border border-line bg-bg/80 px-5 py-1 text-4xl font-bold tabular-nums sm:px-8 sm:text-6xl" data-testid="live-score" aria-live="polite">
              {h}<span className="mx-1.5 text-muted">-</span>{a}
            </div>
          </div>
          <p className="display text-left text-xl font-bold text-away sm:text-4xl">{away}</p>
        </div>

        <div className="mt-3 text-center">
          <span className="display text-4xl font-semibold tabular-nums text-accent sm:text-5xl" data-testid="live-clock">{state.clock}</span>
          <span className="ml-3 text-sm text-muted" data-testid="live-period">{periodLabel(state.period)}</span>
        </div>

        <div className="mt-5 flex flex-wrap items-center justify-center gap-3">
          <button
            type="button"
            data-testid="live-pause"
            onClick={() => send({ cmd: state.paused ? "resume" : "pause" })}
            disabled={state.ended}
            className="inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg disabled:opacity-40"
          >
            {state.paused ? <Play className="h-4 w-4" aria-hidden /> : <Pause className="h-4 w-4" aria-hidden />}
            {state.paused ? "Resume" : "Pause"}
          </button>
          <div role="group" aria-label="Speed" data-testid="live-speed" className="inline-flex rounded-lg border border-line bg-bg p-0.5">
            {SPEEDS.map((s: Speed) => (
              <button
                key={s}
                type="button"
                aria-pressed={state.speed === s}
                onClick={() => send({ cmd: "speed", value: s })}
                className={`rounded-md px-3 py-1.5 text-sm font-medium tabular-nums ${state.speed === s ? "bg-accent text-bg" : "text-muted hover:text-ink"}`}
              >
                {s}x
              </button>
            ))}
          </div>
          <button type="button" onClick={restart} data-testid="live-restart" className="inline-flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-sm text-muted hover:text-ink">
            <RotateCcw className="h-4 w-4" aria-hidden /> Restart
          </button>
        </div>

        <div className="relative mt-5">
          <input
            type="range"
            min={0}
            max={Math.round(duration)}
            step={1}
            value={Math.round(value)}
            onChange={(e) => onScrub(Number(e.target.value))}
            aria-label="Match time"
            data-testid="live-scrubber"
            className="relative z-10 w-full"
          />
          <div className="pointer-events-none absolute inset-x-0 top-1/2 -z-0 h-1 -translate-y-1/2">
            {state.hello?.periods.slice(1).map((p) => (
              <span key={p.period} className="absolute top-[-4px] h-3 w-px bg-muted/60" style={{ left: `${(p.start / duration) * 100}%` }} title={p.label} />
            ))}
            {goals.map((g) => (
              <span key={g.id} className="absolute top-[-3px] h-2.5 w-2.5 -translate-x-1/2 rounded-full bg-amber" style={{ left: `${(g.anchor_t / duration) * 100}%` }} title={g.headline} />
            ))}
          </div>
        </div>
      </section>

      {failed && (
        <div role="alert" data-testid="live-error" className="rounded-xl border border-danger/40 bg-danger/10 p-4 text-sm">
          <p className="font-semibold text-danger">The live stream is not connected</p>
          <p className="mt-1 text-ink/80">Start the backend with .\start.ps1 and open the match again. Live replay needs the backend only; Ollama is not used.</p>
        </div>
      )}

      <div className="card min-h-[3.5rem] px-4 py-3" data-testid="live-caption" aria-live="polite">
        {state.caption ? (
          <div key={state.caption.n} className="caption-in">
            <p className="text-[15px] font-medium">{state.caption.text}</p>
            {why && why.id === state.caption.momentId && <p className="mt-1 text-sm text-muted" data-testid="live-why">{why.text}</p>}
          </div>
        ) : (
          <p className="text-sm text-muted">Commentary appears here when an important moment happens.</p>
        )}
      </div>

      <section className="card p-5" aria-label="Expected goals so far">
        <h2 className="display mb-3 text-xl font-semibold tracking-wide">xG as it happens</h2>
        <XgChart timeline={summary.xg_timeline} home={home} away={away} goals={goals} highlightId={null} onSelect={() => undefined} upTo={chartIndex >= 0 ? chartIndex : 0} />
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="card p-4">
          <MomentsTimeline moments={state.moments} total={state.moments.length} minImportance={0} onMinImportance={() => undefined} selectedId={null} highlightId={null} home={home} onSelect={() => undefined} animate />
          <p className="sr-only" data-testid="live-moment-count">{state.moments.length}</p>
        </div>
        <section className="card p-4" aria-label="Recent events">
          <h2 className="display mb-3 text-xl font-semibold tracking-wide">Latest events</h2>
          {ticker.length === 0 ? (
            <p className="text-sm text-muted">Waiting for the first events…</p>
          ) : (
            <ul className="space-y-2" data-testid="live-ticker">
              {ticker.map(({ e, d }) => {
                const Icon = ICONS[d!.icon];
                return (
                  <li key={e.id} className="caption-in flex items-start gap-3 text-sm">
                    <span className="display w-14 shrink-0 text-right text-base font-semibold tabular-nums">{e.clock}</span>
                    <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${d!.tone}`} aria-hidden />
                    <span className={d!.tone}>{d!.text}</span>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      </div>

      {state.ended && (
        <div className="card flex flex-wrap items-center justify-between gap-3 border-accent/40 p-5" data-testid="live-fulltime">
          <p className="display text-2xl font-semibold">
            Full time: {home} {h}-{a} {away}
          </p>
          <button
            type="button"
            onClick={onReadRecap}
            data-testid="live-read-recap"
            className="inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg hover:brightness-110"
          >
            <BookOpen className="h-4 w-4" aria-hidden /> Read the recap
          </button>
        </div>
      )}
    </div>
  );
}
