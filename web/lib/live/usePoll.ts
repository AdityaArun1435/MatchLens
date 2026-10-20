"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface PollState<T> {
  data: T | null;
  error: string | null;
  /** When the browser last got an answer from our API. */
  fetchedAt: number | null;
  loading: boolean;
  refresh: () => void;
}

/**
 * Fetch `url` now and then again every `intervalFor(data)` milliseconds (null stops polling).
 * Pauses while the tab is hidden and fetches once when it becomes visible again.
 * Always calls our own API, never a data source.
 */
export function usePoll<T>(url: string | null, intervalFor: (data: T | null) => number | null): PollState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fetchedAt, setFetchedAt] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const intervalRef = useRef(intervalFor);
  useEffect(() => {
    intervalRef.current = intervalFor;
  });

  useEffect(() => {
    if (!url) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;
    let latest: T | null = null;
    const controller = new AbortController();

    async function load() {
      try {
        const res = await fetch(url as string, { signal: controller.signal });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        latest = (await res.json()) as T;
        if (cancelled) return;
        setData(latest);
        setError(null);
        setFetchedAt(Date.now());
      } catch (err) {
        if (cancelled || (err instanceof DOMException && err.name === "AbortError")) return;
        setError(err instanceof Error ? err.message : "Request failed");
      } finally {
        if (!cancelled) setLoading(false);
      }
      schedule();
    }

    function schedule() {
      const wait = intervalRef.current(latest);
      if (wait == null || cancelled) return;
      timer = setTimeout(() => {
        if (document.visibilityState === "visible") void load();
        else schedule();
      }, wait);
    }

    function onVisible() {
      if (document.visibilityState === "visible") {
        clearTimeout(timer);
        void load();
      }
    }

    void load();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      clearTimeout(timer);
      controller.abort();
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [url, tick]);

  const refresh = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, fetchedAt, loading, refresh };
}
