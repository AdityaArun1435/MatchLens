"use client";

import { Check, CircleAlert, CircleX, ChevronDown } from "lucide-react";
import { splitError } from "@/lib/format";
import type { Quality, ValidationReport } from "@/lib/types";
import { QualityBadge } from "./Bits";

const CHECKS = [
  ["Citations", "every paragraph cites real moments, and only ones the model was shown"],
  ["Numbers", "every score, minute and xG figure must appear in the cited moments"],
  ["Names", "a player must be named in a cited moment; invented or misplaced names fail"],
  ["Who led", "'took the lead', 'equalised', 'won', 'drew' are compared with the score before and after each goal"],
  ["Wording", "banned phrases (trophies, history, hosts…) and, except for fans, opinion words"],
  ["Penalties", "an in-play penalty is 'penalty in regular/extra time', a shootout kick is 'in the shootout'"],
  ["Repetition", "repeated sentences and impossible score lines are rejected"],
  ["Shootout", "this paragraph is written from the kick list, never by the model"],
  ["Translation", "Hindi and Tamil keep the English numbers, mapped names and fixed football terms"],
];

function Chip({ children, tone = "neutral", testId }: { children: React.ReactNode; tone?: "good" | "warn" | "bad" | "neutral"; testId?: string }) {
  const cls = {
    good: "border-accent/40 bg-accent/10 text-accent",
    warn: "border-amber/40 bg-amber/10 text-amber",
    bad: "border-danger/40 bg-danger/10 text-danger",
    neutral: "border-line bg-panel2 text-muted",
  }[tone];
  return <span data-testid={testId} className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs ${cls}`}>{children}</span>;
}

export function ValidationReportView({
  report,
  model,
  seconds,
  cached,
  quality,
  noun = "recap",
}: {
  report: ValidationReport;
  model: string;
  seconds: number;
  cached: boolean;
  quality: Quality;
  noun?: string;
}) {
  const tr = report.translation;
  const retries = Math.max(0, report.attempts.length - 1);
  const dropped = report.dropped.length;
  const fallbacks = tr?.fallbacks ?? 0;
  const usedTemplate = report.method === "fallback";

  return (
    <details data-testid="report" className="group rounded-xl border border-line bg-bg/60">
      <summary data-testid="report-toggle" className="flex cursor-pointer list-none flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3">
        <ChevronDown className="h-4 w-4 text-muted transition-transform group-open:rotate-180" aria-hidden />
        <span className="font-semibold">How was this checked?</span>
        <span className="flex flex-wrap gap-1.5">
          <Chip tone={usedTemplate ? "bad" : "good"}>{usedTemplate ? "template used" : "written by the model, checked"}</Chip>
          <Chip tone={retries ? "warn" : "good"} testId="chip-retries">{retries ? `${retries} retry` : "no retries"}</Chip>
          <Chip tone={dropped ? "bad" : "good"} testId="chip-dropped">{dropped} dropped</Chip>
          {tr && <Chip tone={fallbacks ? "warn" : "good"} testId="chip-fallbacks">{fallbacks} in English</Chip>}
        </span>
      </summary>

      <div className="space-y-5 border-t border-line px-4 py-4 text-sm">
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            ["Model", model],
            ["Generated in", `${seconds.toFixed(1)}s${cached ? " (cached)" : ""}`],
            ["Attempts", String(report.attempts.length)],
            ["Language quality", ""],
          ].map(([k, v]) => (
            <div key={k}>
              <dt className="text-xs text-muted">{k}</dt>
              <dd className="mt-0.5 font-medium">{k === "Language quality" ? <QualityBadge quality={quality} /> : v}</dd>
            </div>
          ))}
        </dl>

        {report.fallback_reason && (
          <p className="rounded-lg border border-danger/40 bg-danger/10 p-3 text-danger">
            The model&apos;s answer could not be used ({report.fallback_reason}), so a plain template recap built straight from the data is shown instead.
          </p>
        )}

        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Attempts</h3>
          <ol className="space-y-3">
            {report.attempts.map((a) => {
              const ok = a.llm_error === null && a.errors.length === 0;
              return (
                <li key={a.attempt} data-testid={`attempt-${a.attempt}`} className="flex gap-3">
                  {ok ? <Check className="mt-0.5 h-4 w-4 shrink-0 text-accent" /> : <CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber" />}
                  <div className="min-w-0">
                    <p className="font-medium">
                      Attempt {a.attempt}:{" "}
                      {a.llm_error ? `no usable answer (${a.llm_error})` : `${a.items_valid} of ${a.items_total} paragraphs passed`}
                    </p>
                    {a.attempt > 1 && <p className="text-xs text-muted">Asked again with the exact problems listed.</p>}
                    {a.errors.length > 0 && (
                      <ul className="mt-1.5 space-y-1">
                        {a.errors.map((e, i) => {
                          const s = splitError(e);
                          return (
                            <li key={i} className="text-xs text-ink/80">
                              {s.where && <span className="mr-1.5 rounded bg-panel2 px-1.5 py-0.5 text-muted">{s.where}</span>}
                              {s.text}
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
        </div>

        {dropped > 0 && (
          <div data-testid="dropped">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Dropped paragraphs</h3>
            <ul className="space-y-2">
              {report.dropped.map((d) => (
                <li key={d.index} className="flex gap-3 rounded-lg border border-danger/30 bg-danger/5 p-3">
                  <CircleX className="mt-0.5 h-4 w-4 shrink-0 text-danger" />
                  <div className="min-w-0 text-xs">
                    <p className="text-ink/70 line-through decoration-danger/50">{d.text}</p>
                    <p className="mt-1 text-danger">{d.errors.join(" · ")}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}

        {tr && (
          <div data-testid="translation-report">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Translation, paragraph by paragraph</h3>
            <ul className="grid gap-1.5 sm:grid-cols-2">
              {tr.units.map((u) => (
                <li key={u.unit} className="rounded-lg border border-line px-3 py-2 text-xs">
                  <span className="flex items-center justify-between gap-2">
                    <span className="font-medium capitalize">{u.unit}</span>
                    {u.status === "translated" ? (
                      <Chip tone={u.attempts > 1 ? "warn" : "good"}>{u.attempts > 1 ? "translated after retry" : "translated"}</Chip>
                    ) : (
                      <Chip tone="bad">shown in English</Chip>
                    )}
                  </span>
                  {u.errors.map((e, i) => (
                    <span key={i} className="mt-1 block text-muted">{e}</span>
                  ))}
                  {u.notes.map((n, i) => (
                    <span key={i} className="mt-1 block text-muted">{n}</span>
                  ))}
                </li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-muted">
              Translated from the already-checked English in {tr.seconds.toFixed(1)}s. A paragraph that fails twice is shown in English, never removed.
              {tr.names_missing.length > 0 && ` Names without a spelling: ${tr.names_missing.join(", ")}.`}
            </p>
          </div>
        )}

        {report.notes.length > 0 && (
          <ul className="list-inside list-disc space-y-1 text-xs text-muted">
            {report.notes.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        )}

        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">What every {noun} paragraph is checked for</h3>
          <ul className="grid gap-x-6 gap-y-1.5 text-xs sm:grid-cols-2">
            {CHECKS.map(([name, what]) => (
              <li key={name}>
                <span className="font-semibold text-ink">{name}.</span> <span className="text-muted">{what}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </details>
  );
}
