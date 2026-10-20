import type { NextRequest } from "next/server";
import { getMatches } from "@/lib/live/db";
import { failure, json } from "@/lib/live/respond";

const MAX_SPAN_MS = 14 * 24 * 3600 * 1000;

/** GET /api/matches?from=ISO&to=ISO[&competition=PL]. The browser sends its own local-day bounds. */
export async function GET(request: NextRequest) {
  const q = request.nextUrl.searchParams;
  const from = new Date(q.get("from") ?? "");
  const to = new Date(q.get("to") ?? "");
  if (Number.isNaN(from.getTime()) || Number.isNaN(to.getTime()) || to <= from || to.getTime() - from.getTime() > MAX_SPAN_MS) {
    return json({ error: "from and to must be ISO times, to after from, at most 14 days apart" }, 400);
  }
  const competition = q.get("competition") ?? undefined;
  if (competition && !/^[A-Z0-9]{2,4}$/.test(competition)) return json({ error: "bad competition code" }, 400);
  try {
    // Round to the minute so equal requests share a CDN cache entry.
    const round = (d: Date) => new Date(Math.floor(d.getTime() / 60000) * 60000).toISOString();
    return json(await getMatches(round(from), round(to), competition));
  } catch (err) {
    return failure(err);
  }
}
