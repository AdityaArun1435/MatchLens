"use client";

import { useEffect, useRef } from "react";
import { MOMENT_META, sideColor } from "@/lib/format";
import type { Moment } from "@/lib/types";

export function MomentIcon({ type, className = "h-4 w-4" }: { type: Moment["type"]; className?: string }) {
  const meta = MOMENT_META[type];
  const Icon = meta.icon;
  const fill = type === "red_card" || type === "second_yellow" ? "currentColor" : "none";
  return <Icon className={`${className} ${meta.tone}`} fill={fill} aria-hidden />;
}

/** Vertical list of moments in match order, with a slider that hides the less important ones. */
export function MomentsTimeline({
  moments,
  total,
  minImportance,
  onMinImportance,
  selectedId,
  highlightId,
  home,
  onSelect,
  animate = false,
}: {
  moments: Moment[];
  total: number;
  minImportance: number;
  onMinImportance: (v: number) => void;
  selectedId: string | null;
  highlightId: string | null;
  home: string;
  onSelect: (id: string) => void;
  /** Live replay: new items slide in. */
  animate?: boolean;
}) {
  const listRef = useRef<HTMLOListElement>(null);

  // A chip or chart marker elsewhere asked for this moment: bring it into view inside the list.
  useEffect(() => {
    if (!highlightId) return;
    const el = listRef.current?.querySelector<HTMLElement>(`[data-moment-id="${highlightId}"]`);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [highlightId]);

  return (
    <section aria-label="Moments timeline">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="display text-xl font-semibold tracking-wide">Key moments</h2>
        <span className="text-xs text-muted" data-testid="moment-count">showing {moments.length} of {total}</span>
      </div>
      <label className="mb-4 block text-xs text-muted">
        <span className="mb-1 flex justify-between"><span>Minimum importance</span><span className="tabular-nums">{minImportance.toFixed(2)}</span></span>
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={minImportance}
          onChange={(e) => onMinImportance(Number(e.target.value))}
          className="w-full"
          aria-label="Minimum importance"
          data-testid="importance-slider"
        />
      </label>
      {moments.length === 0 ? (
        <p className="rounded-lg border border-line p-4 text-sm text-muted">No moments at this importance. Lower the slider.</p>
      ) : (
        <div className="max-h-[min(70vh,720px)] overflow-y-auto pr-1" data-testid="moments-scroll">
        <ol ref={listRef} className="relative space-y-1.5 before:absolute before:bottom-3 before:left-[66px] before:top-3 before:w-px before:bg-line">
          {moments.map((m) => {
            const selected = m.id === selectedId;
            const flash = m.id === highlightId;
            return (
              <li key={m.id} data-moment-id={m.id} data-testid={`moment-${m.id}`} className={`${flash ? "flash " : ""}${animate ? "pop-in " : ""}rounded-xl`} data-moment-type={m.type}>
                <button
                  type="button"
                  onClick={() => onSelect(m.id)}
                  aria-pressed={selected}
                  className={`grid w-full grid-cols-[52px_30px_1fr] items-start gap-x-3 rounded-xl border px-2 py-2.5 text-left transition-colors ${
                    selected ? "border-accent/60 bg-accent/5" : flash ? "border-amber/70 bg-amber/5" : "border-transparent hover:bg-panel2"
                  }`}
                >
                  <span className="display pt-0.5 text-right text-lg font-semibold leading-none tabular-nums">{m.clock_label}</span>
                  <span className="relative z-10 mt-0.5 flex h-[26px] w-[26px] items-center justify-center rounded-full border border-line bg-panel">
                    <MomentIcon type={m.type} />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-sm leading-snug">{m.headline}</span>
                    <span className="mt-1 flex items-center gap-2 text-[11px] text-muted">
                      <span className={m.team ? sideColor(m.team, home) : ""}>{MOMENT_META[m.type].label}</span>
                      <span
                        className="h-[3px] w-14 overflow-hidden rounded-full bg-line"
                        title={`importance ${m.importance.toFixed(2)}`}
                        role="img"
                        aria-label={`importance ${m.importance.toFixed(2)} out of 1`}
                      >
                        <span className="block h-full rounded-full bg-muted/70" style={{ width: `${m.importance * 100}%` }} />
                      </span>
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
        </div>
      )}
    </section>
  );
}
