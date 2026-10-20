import { getMatchDetail } from "@/lib/live/db";
import { failure, json } from "@/lib/live/respond";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const id = Number((await params).id);
  if (!Number.isInteger(id) || id <= 0) return json({ error: "bad match id" }, 400);
  try {
    const detail = await getMatchDetail(id);
    return detail ? json(detail) : json({ error: "match not found" }, 404);
  } catch (err) {
    return failure(err);
  }
}
