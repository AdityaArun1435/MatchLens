"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getHealth, getMoments, getSummary } from "@/lib/api";
import type { Health, MatchSummary, Moment } from "@/lib/types";
import { ErrorNotice, StatusPill } from "./Bits";
import { MomentPanel } from "./MomentPanel";
import { MomentsTimeline } from "./MomentsTimeline";
import { RecapPanel, type Settings } from "./RecapPanel";
import { ScoreHeader } from "./ScoreHeader";
import { XgChart } from "./XgChart";

export function MatchView({ matchId }: { matchId: number }) {
  const [summary, setSummary] = useState<MatchSummary | null>(null);
  const [moments, setMoments] = useState<Moment[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [attempt, setAttempt] = useState(0);
  const [minImportance, setMinImportance] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [highlightId, setHighlightId] = useState<string | null>(null);
  const [settings, setSettings] = useState<Settings>({ audience: "analyst", language: "en", length: "medium" });
  const flashTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let live = true;
    Promise.all([getSummary(matchId), getMoments(matchId)])
      .then(([s, m]) => {
        if (!live) return;
        setSummary(s);
        setMoments([...m].sort((x, y) => x.first_index - y.first_index));
      })
      .catch((e) => live && setError(e));
    getHealth()
      .then((h) => live && (setHealth(h), setHealthError(false)))
      .catch(() => live && setHealthError(true));
    return () => {
      live = false;
    };
  }, [matchId, attempt]);

  const byId = useMemo(() => new Map(moments.map((m) => [m.id, m])), [moments]);
  const visible = useMemo(() => moments.filter((m) => m.importance >= minImportance), [moments, minImportance]);
  const selected = selectedId ? (byId.get(selectedId) ?? null) : null;

  /** A chip or chart marker points at a moment: open it, make sure it is listed, and flash it. */
  const focusMoment = useCallback(
    (id: string) => {
      const m = byId.get(id);
      if (!m) return;
      setMinImportance((v) => (m.importance < v ? 0 : v));
      setSelectedId(id);
      setHighlightId(null);
      requestAnimationFrame(() => setHighlightId(id));
      if (flashTimer.current) clearTimeout(flashTimer.current);
      flashTimer.current = setTimeout(() => setHighlightId(null), 2600);
    },
    [byId],
  );

  if (error) {
    return (
      <div className="mx-auto max-w-3xl p-6">
        <ErrorNotice error={error} onRetry={() => { setError(null); setAttempt((n) => n + 1); }} />
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="mx-auto max-w-6xl space-y-4 p-4 sm:p-6" data-testid="match-loading" aria-busy>
        <div className="skeleton h-56" />
        <div className="skeleton h-72" />
      </div>
    );
  }

  const home = summary.meta.home_team;
  const away = summary.meta.away_team;
  const goals = moments.filter((m) => m.type === "goal");

  return (
    <main className="mx-auto max-w-6xl space-y-4 p-4 pb-16 sm:p-6">
      <div className="flex justify-end">
        <StatusPill health={health} error={healthError} />
      </div>
      <ScoreHeader summary={summary} />
      <section className="card p-5" aria-label="Expected goals timeline">
        <h2 className="display mb-3 text-xl font-semibold tracking-wide">xG timeline</h2>
        <XgChart timeline={summary.xg_timeline} home={home} away={away} goals={goals} highlightId={highlightId ?? selectedId} onSelect={focusMoment} />
      </section>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <RecapPanel matchId={matchId} settings={settings} onSettings={setSettings} byId={byId} onCite={focusMoment} model={health?.llm.model ?? null} />
        <div className="min-w-0">
          {selected && (
            <MomentPanel
              key={selected.id}
              matchId={matchId}
              moment={selected}
              settings={settings}
              home={home}
              away={away}
              byId={byId}
              onClose={() => setSelectedId(null)}
              onCite={focusMoment}
            />
          )}
          <div className="card p-4">
            <MomentsTimeline
              moments={visible}
              total={moments.length}
              minImportance={minImportance}
              onMinImportance={setMinImportance}
              selectedId={selectedId}
              highlightId={highlightId}
              home={home}
              onSelect={(id) => setSelectedId(id === selectedId ? null : id)}
            />
          </div>
        </div>
      </div>
    </main>
  );
}
