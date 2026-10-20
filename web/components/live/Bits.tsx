"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import type { MatchView, TeamRef } from "@/lib/live/types";

export function Crest({ team, size = 24 }: { team: TeamRef; size?: number }) {
  if (!team.crest) {
    return (
      <span className="inline-flex items-center justify-center rounded-full bg-panel2 text-[10px] text-muted" style={{ width: size, height: size }}>
        {team.tla?.slice(0, 2) ?? "?"}
      </span>
    );
  }
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={team.crest} alt="" width={size} height={size} className="object-contain" style={{ width: size, height: size }} loading="lazy" />;
}

export function StatusBadge({ match }: { match: MatchView }) {
  if (match.state === "live") {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-amber">
        <span className="h-2 w-2 animate-pulse rounded-full bg-amber" />
        {match.minute ?? "LIVE"}
      </span>
    );
  }
  if (match.state === "halftime") return <span className="text-xs font-semibold text-amber">HT</span>;
  if (match.state === "finished") return <span className="text-xs text-muted">FT</span>;
  if (match.state === "postponed") return <span className="text-xs text-danger">Postponed</span>;
  return <LocalTime iso={match.kickoff} className="text-xs text-muted" />;
}

const subscribeNever = () => () => {};

function formatLocal(iso: string, mode: "time" | "datetime" | "date"): string {
  const d = new Date(iso);
  const time = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const date = d.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" });
  return mode === "time" ? time : mode === "date" ? date : `${date}, ${time}`;
}

/** Times are rendered in the viewer's own time zone. The server snapshot is empty, so server and browser output cannot disagree. */
export function LocalTime({ iso, className, mode = "time" }: { iso: string; className?: string; mode?: "time" | "datetime" | "date" }) {
  const text = useSyncExternalStore(subscribeNever, () => formatLocal(iso, mode), () => "");
  return <time dateTime={iso} className={className}>{text || " "}</time>;
}

export function Updated({ fetchedAt, error }: { fetchedAt: number | null; error: string | null }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 5000);
    return () => clearInterval(t);
  }, []);
  if (error && fetchedAt == null) return <span className="text-xs text-danger">Could not load: {error}</span>;
  if (fetchedAt == null) return <span className="text-xs text-muted">Loading</span>;
  const secs = Math.max(0, Math.round((now - fetchedAt) / 1000));
  return (
    <span className="text-xs text-muted">
      {error ? <span className="text-danger">Connection problem, showing the last data. </span> : null}
      Checked {secs < 5 ? "just now" : `${secs}s ago`}
    </span>
  );
}
