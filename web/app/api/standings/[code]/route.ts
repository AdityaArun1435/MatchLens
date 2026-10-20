import { getStandings } from "@/lib/live/db";
import { failure, json } from "@/lib/live/respond";

export async function GET(_request: Request, { params }: { params: Promise<{ code: string }> }) {
  const code = (await params).code.toUpperCase();
  if (!/^[A-Z0-9]{2,4}$/.test(code)) return json({ error: "bad competition code" }, 400);
  try {
    return json(await getStandings(code));
  } catch (err) {
    return failure(err);
  }
}
