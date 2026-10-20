/** Short CDN cache so a burst of visitors shares one database read. Data itself only changes when the scheduled refresh runs. */
const CACHE = "public, s-maxage=15, stale-while-revalidate=30";

export function json(body: unknown, status = 200): Response {
  return Response.json(body, { status, headers: status === 200 ? { "Cache-Control": CACHE } : { "Cache-Control": "no-store" } });
}

export function failure(err: unknown): Response {
  const message = err instanceof Error ? err.message : "Unknown error";
  return json({ error: message }, 502);
}
