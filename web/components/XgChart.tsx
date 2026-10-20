"use client";

import { useMemo, useState } from "react";
import type { Moment, TimelinePoint } from "@/lib/types";

const W = 800;
const H = 290;
const PAD = { l: 42, r: 18, t: 20, b: 34 };
const PERIOD_LABEL: Record<number, string> = { 2: "2nd half", 3: "Extra time", 4: "ET 2nd half" };

function niceMax(v: number): number {
  const steps = [0.5, 1, 1.5, 2, 2.5, 3, 4, 5, 6];
  return steps.find((s) => s >= v) ?? Math.ceil(v);
}

/** Cumulative xG per team across the match, with a marker on each goal. Hand-drawn SVG: no chart library needed. */
export function XgChart({
  timeline,
  home,
  away,
  goals,
  highlightId,
  onSelect,
}: {
  timeline: TimelinePoint[];
  home: string;
  away: string;
  goals: Moment[];
  highlightId: string | null;
  onSelect: (id: string) => void;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const n = timeline.length;
  const geometry = useMemo(() => {
    const maxV = niceMax(Math.max(0.5, ...timeline.flatMap((p) => [p.cumulative_xg[home] ?? 0, p.cumulative_xg[away] ?? 0])) * 1.05);
    const x = (i: number) => PAD.l + (n > 1 ? (i / (n - 1)) * (W - PAD.l - PAD.r) : 0);
    const y = (v: number) => PAD.t + (1 - v / maxV) * (H - PAD.t - PAD.b);
    const line = (team: string) => timeline.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.cumulative_xg[team] ?? 0).toFixed(1)}`).join(" ");
    const area = (team: string) => `${line(team)} L${x(n - 1).toFixed(1)},${y(0)} L${x(0).toFixed(1)},${y(0)} Z`;
    const ticks: { i: number; label: string }[] = [];
    for (const m of [0, 15, 30, 45, 60, 75, 90, 105, 120]) {
      const i = timeline.findIndex((p) => p.minute === m);
      if (i >= 0) ticks.push({ i, label: `${m}'` });
    }
    const dividers: { i: number; label: string }[] = [];
    timeline.forEach((p, i) => {
      if (i > 0 && p.period !== timeline[i - 1].period) dividers.push({ i, label: PERIOD_LABEL[p.period] ?? "" });
    });
    const yTicks = Array.from({ length: 5 }, (_, k) => (maxV / 4) * k);
    return { maxV, x, y, line, area, ticks, dividers, yTicks };
  }, [timeline, home, away, n]);

  const markers = goals
    .map((g) => {
      const i = timeline.findIndex((p) => p.period === g.period && p.minute === g.minute);
      const team = g.score_after[0] > g.score_before[0] ? home : away;
      return i < 0 ? null : { g, i, team };
    })
    .filter((m): m is { g: Moment; i: number; team: string } => m !== null);

  const { x, y } = geometry;
  const at = hover === null ? null : timeline[hover];

  function onMove(e: React.PointerEvent<SVGSVGElement>) {
    const box = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - box.left) / box.width) * W;
    const i = Math.round(((px - PAD.l) / (W - PAD.l - PAD.r)) * (n - 1));
    setHover(Math.max(0, Math.min(n - 1, i)));
  }

  return (
    <div className="relative" data-testid="xg-chart">
      <div className="mb-2 flex flex-wrap items-center gap-x-5 gap-y-1 text-sm">
        <span className="flex items-center gap-2"><i className="h-2.5 w-2.5 rounded-full bg-home" />{home} <b className="display text-lg">{(timeline[n - 1]?.cumulative_xg[home] ?? 0).toFixed(2)}</b></span>
        <span className="flex items-center gap-2"><i className="h-2.5 w-2.5 rounded-full bg-away" />{away} <b className="display text-lg">{(timeline[n - 1]?.cumulative_xg[away] ?? 0).toFixed(2)}</b></span>
        <span className="ml-auto text-xs text-muted">cumulative xG, dots are goals</span>
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full touch-pan-y select-none"
        role="img"
        aria-label={`Cumulative expected goals for ${home} and ${away} through the match, with goals marked`}
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
      >
        <defs>
          <linearGradient id="homeFill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#5aa9ff" stopOpacity="0.28" /><stop offset="100%" stopColor="#5aa9ff" stopOpacity="0" /></linearGradient>
          <linearGradient id="awayFill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#ff8a4c" stopOpacity="0.25" /><stop offset="100%" stopColor="#ff8a4c" stopOpacity="0" /></linearGradient>
        </defs>
        {geometry.yTicks.map((v) => (
          <g key={v}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} stroke="#1e2836" strokeWidth="1" />
            <text x={PAD.l - 8} y={y(v) + 4} textAnchor="end" fontSize="11" fill="#8794a8">{v.toFixed(v % 1 ? 1 : 0)}</text>
          </g>
        ))}
        {geometry.dividers.map((d) => (
          <g key={d.i}>
            <line x1={x(d.i)} x2={x(d.i)} y1={PAD.t} y2={H - PAD.b} stroke="#2a3647" strokeDasharray="3 4" />
            <text x={x(d.i) + 5} y={H - PAD.b - 8} fontSize="10" fill="#8794a8">{d.label}</text>
          </g>
        ))}
        {geometry.ticks.map((t) => (
          <text key={t.i} x={x(t.i)} y={H - 12} textAnchor="middle" fontSize="11" fill="#8794a8">{t.label}</text>
        ))}
        <path d={geometry.area(home)} fill="url(#homeFill)" />
        <path d={geometry.area(away)} fill="url(#awayFill)" />
        <path d={geometry.line(home)} fill="none" stroke="#5aa9ff" strokeWidth="2.4" strokeLinejoin="round" />
        <path d={geometry.line(away)} fill="none" stroke="#ff8a4c" strokeWidth="2.4" strokeLinejoin="round" />
        {at && hover !== null && (
          <line x1={x(hover)} x2={x(hover)} y1={PAD.t} y2={H - PAD.b} stroke="#8794a8" strokeOpacity="0.6" />
        )}
        {markers.map(({ g, i, team }, k) => {
          const crowded = k > 0 && Math.abs(x(i) - x(markers[k - 1].i)) < 34;
          const color = team === home ? "#5aa9ff" : "#ff8a4c";
          const cx = x(i);
          const cy = y(timeline[i].cumulative_xg[team] ?? 0);
          const active = g.id === highlightId;
          return (
            <g
              key={g.id}
              role="button"
              tabIndex={0}
              aria-label={`${g.headline}`}
              data-testid={`goal-marker-${g.id}`}
              className="cursor-pointer"
              onClick={() => onSelect(g.id)}
              onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onSelect(g.id)}
            >
              <title>{g.headline}</title>
              <circle cx={cx} cy={cy} r={active ? 11 : 8} fill="#070a0f" stroke={color} strokeWidth={active ? 3 : 2.2} />
              <circle cx={cx} cy={cy} r={active ? 5 : 3.5} fill={color} />
              <text x={cx} y={crowded ? cy + 24 : cy - 14} textAnchor="middle" fontSize="11" fontWeight="600" fill="#e8eef6">{g.clock_label}</text>
            </g>
          );
        })}
      </svg>
      {at && (
        <div
          className="pointer-events-none absolute top-8 z-10 rounded-lg border border-line bg-panel2/95 px-3 py-2 text-xs shadow-lg"
          style={{ left: `clamp(8px, ${(x(hover!) / W) * 100}%, calc(100% - 150px))` }}
        >
          <div className="mb-1 font-semibold">{at.label}</div>
          <div className="text-home">{home}: {(at.cumulative_xg[home] ?? 0).toFixed(2)}</div>
          <div className="text-away">{away}: {(at.cumulative_xg[away] ?? 0).toFixed(2)}</div>
        </div>
      )}
    </div>
  );
}
