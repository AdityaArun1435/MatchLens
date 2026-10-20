"use client";

import { AlertTriangle, Loader2, ServerOff, WifiOff } from "lucide-react";
import { QUALITY } from "@/lib/format";
import { ApiError } from "@/lib/api";
import type { Health, Quality } from "@/lib/types";

export function QualityBadge({ quality }: { quality: Quality }) {
  const q = QUALITY[quality];
  return (
    <span
      title={q.hint}
      data-testid="quality-badge"
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${q.className}`}
    >
      {q.label}
    </span>
  );
}

export function Spinner({ className = "" }: { className?: string }) {
  return <Loader2 className={`animate-spin ${className}`} aria-hidden />;
}

/** One friendly card for each way a request can fail. */
export function ErrorNotice({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const err = error instanceof ApiError ? error : new ApiError("http", error instanceof Error ? error.message : "Something went wrong.");
  const view = {
    offline: {
      icon: WifiOff,
      title: "The MatchLens backend is not running",
      body: "Start it with .\\start.ps1 (or `python -m uvicorn matchlens.api:app`), then try again.",
    },
    llm_down: {
      icon: ServerOff,
      title: "Ollama is not running",
      body: "Recaps are written by a model on this computer. Start the Ollama app (or run `ollama serve`) and make sure the model is pulled, then try again.",
    },
    llm_error: { icon: AlertTriangle, title: "The model server returned an error", body: err.message },
    not_found: { icon: AlertTriangle, title: "Not found", body: err.message },
    http: { icon: AlertTriangle, title: "Something went wrong", body: err.message },
  }[err.kind];
  const Icon = view.icon;
  return (
    <div role="alert" data-testid="error-notice" className="flex gap-3 rounded-xl border border-danger/40 bg-danger/10 p-4">
      <Icon className="mt-0.5 h-5 w-5 shrink-0 text-danger" aria-hidden />
      <div className="min-w-0 text-sm">
        <p className="font-semibold text-danger">{view.title}</p>
        <p className="mt-1 text-ink/80">{view.body}</p>
        {onRetry && (
          <button onClick={onRetry} className="mt-3 rounded-lg border border-danger/50 px-3 py-1.5 text-xs font-medium text-danger hover:bg-danger/10">
            Try again
          </button>
        )}
      </div>
    </div>
  );
}

export function StatusPill({ health, error }: { health: Health | null; error: boolean }) {
  let dot = "bg-muted";
  let text = "Checking local model…";
  if (error) {
    dot = "bg-danger";
    text = "Backend offline";
  } else if (health) {
    dot = health.llm.available ? "bg-accent" : "bg-amber";
    text = health.llm.available ? `Local model ready: ${health.llm.model}` : "Ollama not running";
  }
  return (
    <span data-testid="status-pill" className="inline-flex items-center gap-2 rounded-full border border-line bg-panel px-3 py-1 text-xs text-muted">
      <span className={`h-2 w-2 rounded-full ${dot}`} />
      {text}
    </span>
  );
}

export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
  testId,
}: {
  label: string;
  value: T;
  options: { id: T; label: string; title?: string }[];
  onChange: (v: T) => void;
  testId?: string;
}) {
  return (
    <div role="group" aria-label={label} data-testid={testId} className="inline-flex rounded-lg border border-line bg-bg p-0.5">
      {options.map((o) => (
        <button
          key={o.id}
          type="button"
          title={o.title}
          aria-pressed={value === o.id}
          onClick={() => onChange(o.id)}
          className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
            value === o.id ? "bg-accent text-bg" : "text-muted hover:text-ink"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
