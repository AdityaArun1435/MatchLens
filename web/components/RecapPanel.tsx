"use client";

import { Sparkles } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { postRecap } from "@/lib/api";
import { AUDIENCES, LANGUAGES } from "@/lib/format";
import type { Audience, Language, Length, Moment, Quality, RecapResult } from "@/lib/types";
import { ErrorNotice, QualityBadge, Segmented, Spinner } from "./Bits";
import { CiteChips } from "./CiteChips";
import { ValidationReportView } from "./ValidationReportView";

export interface Settings {
  audience: Audience;
  language: Language;
  length: Length;
}

const LENGTHS: { id: Length; label: string }[] = [
  { id: "short", label: "Short" },
  { id: "medium", label: "Medium" },
];

const qualityOf: Record<Language, Quality> = { en: "stable", hi: "machine-translated", ta: "experimental" };

function useElapsed(active: boolean): number {
  const [s, setS] = useState(0);
  useEffect(() => {
    if (!active) return;
    const start = Date.now();
    const t = setInterval(() => setS(Math.floor((Date.now() - start) / 1000)), 500);
    return () => {
      clearInterval(t);
      setS(0);
    };
  }, [active]);
  return s;
}

export function RecapPanel({
  matchId,
  settings,
  onSettings,
  byId,
  onCite,
  model,
}: {
  matchId: number;
  settings: Settings;
  onSettings: (s: Settings) => void;
  byId: Map<string, Moment>;
  onCite: (id: string) => void;
  model: string | null;
}) {
  const key = `${settings.audience}|${settings.length}|${settings.language}`;
  const [results, setResults] = useState<Record<string, RecapResult>>({});
  const [loadingKey, setLoadingKey] = useState<string | null>(null);
  const [error, setError] = useState<{ key: string; err: unknown } | null>(null);
  const abort = useRef<AbortController | null>(null);
  const loading = loadingKey === key;
  const elapsed = useElapsed(loading);
  const result = results[key];

  useEffect(() => () => abort.current?.abort(), []);

  const generate = useCallback(async () => {
    abort.current?.abort();
    const ctl = new AbortController();
    abort.current = ctl;
    const forKey = key;
    setLoadingKey(forKey);
    setError(null);
    try {
      const res = await postRecap(matchId, settings, ctl.signal);
      setResults((r) => ({ ...r, [forKey]: res }));
    } catch (err) {
      if (!(err instanceof DOMException && err.name === "AbortError")) setError({ key: forKey, err });
    } finally {
      if (abort.current === ctl) setLoadingKey(null);
    }
  }, [key, matchId, settings]);

  const translated = settings.language !== "en";
  const pending = loadingKey !== null && loadingKey !== key; // a request for another combination is still running

  return (
    <section aria-label="Recap" className="card p-5" data-testid="recap-panel">
      <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-3">
        <h2 className="display mr-auto text-xl font-semibold tracking-wide">Match recap</h2>
        <QualityBadge quality={qualityOf[settings.language]} />
      </div>

      <div className="mb-5 flex flex-wrap gap-3">
        <Segmented label="Audience" testId="audience-toggle" value={settings.audience} options={AUDIENCES} onChange={(audience) => onSettings({ ...settings, audience })} />
        <Segmented
          label="Language"
          testId="language-toggle"
          value={settings.language}
          options={LANGUAGES.map((l) => ({ id: l.id, label: l.label, title: l.native }))}
          onChange={(language) => onSettings({ ...settings, language })}
        />
        <Segmented label="Length" testId="length-toggle" value={settings.length} options={LENGTHS} onChange={(length) => onSettings({ ...settings, length })} />
      </div>

      {!result && !loading && !(error && error.key === key) && (
        <div className="rounded-xl border border-dashed border-line p-6 text-center">
          <p className="text-sm text-muted">
            Nothing generated yet for {AUDIENCES.find((a) => a.id === settings.audience)?.label.toLowerCase()} / {settings.length} / {settings.language.toUpperCase()}.
          </p>
          <button
            type="button"
            data-testid="recap-generate"
            onClick={generate}
            className="mt-4 inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg hover:brightness-110"
          >
            <Sparkles className="h-4 w-4" aria-hidden /> Generate recap
          </button>
          {pending && <p className="mt-3 text-xs text-amber">Another recap is still being written; starting this one stops it.</p>}
        </div>
      )}

      {loading && (
        <div role="status" data-testid="recap-loading" className="rounded-xl border border-line bg-bg/60 p-5">
          <div className="flex items-center gap-3">
            <Spinner className="h-5 w-5 text-accent" />
            <p className="text-sm font-medium">Writing on this computer{model ? ` with ${model}` : ""}… {elapsed}s</p>
          </div>
          <p className="mt-2 text-xs text-muted">
            Nothing leaves your machine, so this can take about 30 seconds the first time
            {translated ? ". Hindi and Tamil are written in English first, checked, then translated paragraph by paragraph, so allow a minute or more" : ""}. The same
            request is instant once it has been generated.
          </p>
          <div className="mt-4 space-y-2" aria-hidden>
            <div className="skeleton h-4 w-3/4" />
            <div className="skeleton h-4 w-full" />
            <div className="skeleton h-4 w-5/6" />
          </div>
        </div>
      )}

      {error && error.key === key && !loading && <ErrorNotice error={error.err} onRetry={generate} />}

      {result && !loading && (
        <div data-testid="recap-result">
          <h3 lang={result.language} className="display text-2xl font-semibold" data-testid="recap-title">{result.recap.title}</h3>
          <div className="mt-4 space-y-5">
            {result.recap.paragraphs.map((p, i) => (
              <p key={i} lang={p.language ?? result.language} data-testid="recap-paragraph" className="text-[15px] leading-relaxed">
                {p.text}
                {p.note && <span lang="en" className="mt-1.5 block rounded-md border border-amber/30 bg-amber/5 px-2.5 py-1.5 text-xs text-amber" data-testid="paragraph-note">{p.note}</span>}
                <CiteChips cites={p.cites} byId={byId} onCite={onCite} />
              </p>
            ))}
          </div>
          <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
            <ValidationWrapper result={result} />
          </div>
          <button type="button" onClick={generate} className="mt-4 text-xs text-muted underline-offset-2 hover:text-ink hover:underline" data-testid="recap-regenerate">
            Generate again
          </button>
        </div>
      )}
    </section>
  );
}

function ValidationWrapper({ result }: { result: RecapResult }) {
  return (
    <div className="w-full">
      <ValidationReportView report={result.report} model={result.model} seconds={result.generation_seconds} cached={result.cached} quality={result.quality} />
    </div>
  );
}
