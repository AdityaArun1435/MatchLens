import type {
  Audience,
  ExplainResult,
  Health,
  Language,
  Length,
  MatchListItem,
  MatchSummary,
  Moment,
  RecapResult,
} from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** `offline`: the backend itself did not answer. `llm_down`: Ollama is not running (HTTP 503). `llm_error`: HTTP 502. */
export type ApiErrorKind = "offline" | "llm_down" | "llm_error" | "not_found" | "http";

export class ApiError extends Error {
  constructor(
    public kind: ApiErrorKind,
    message: string,
    public status = 0,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError("offline", `Cannot reach the MatchLens backend at ${API_URL}.`);
  }
  if (res.ok) return (await res.json()) as T;
  let detail = res.statusText;
  try {
    const body = await res.json();
    detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
  } catch {
    /* keep statusText */
  }
  const kind: ApiErrorKind = res.status === 503 ? "llm_down" : res.status === 502 ? "llm_error" : res.status === 404 ? "not_found" : "http";
  throw new ApiError(kind, detail, res.status);
}

export const getMatches = () => request<MatchListItem[]>("/matches");
export const getSummary = (id: number) => request<MatchSummary>(`/matches/${id}/summary`);
export const getMoments = (id: number) => request<Moment[]>(`/matches/${id}/moments`);
export const getHealth = () => request<Health>("/health");

export function postRecap(
  id: number,
  body: { audience: Audience; length: Length; language: Language },
  signal?: AbortSignal,
) {
  return request<RecapResult>(`/matches/${id}/recap`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
}

export function getExplanation(id: number, momentId: string, audience: Audience, language: Language, signal?: AbortSignal) {
  const q = new URLSearchParams({ audience, language });
  return request<ExplainResult>(`/matches/${id}/moments/${momentId}/explain?${q}`, { signal });
}
