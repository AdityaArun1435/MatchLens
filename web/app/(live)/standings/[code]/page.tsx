import { notFound } from "next/navigation";
import { SiteNav } from "@/components/live/SiteNav";
import { StandingsTable } from "@/components/live/StandingsTable";
import { COMPETITIONS } from "@/lib/live/competitions";
import { getStandings } from "@/lib/live/db";
import type { Standings } from "@/lib/live/types";

// Standings only change when matches finish. The table is read per request and cached briefly at the edge.
export const revalidate = 60;

export default async function StandingsPage({ params }: { params: Promise<{ code: string }> }) {
  const code = (await params).code.toUpperCase();
  const comp = COMPETITIONS.find((c) => c.code === code);
  if (!comp) notFound();
  let standings: Standings | null = null;
  let failed = false;
  try {
    standings = await getStandings(code);
  } catch {
    failed = true;
  }
  return (
    <>
      <SiteNav active={`standings/${code}`} />
      <main className="mx-auto max-w-4xl px-4 py-6">
        <h1 className="display mb-4 text-3xl font-bold">{comp.name} table</h1>
        {failed ? <p className="card p-6 text-sm text-danger">The table could not be loaded. Try again in a minute.</p> : null}
        {standings && standings.tables.length === 0 ? (
          <p className="card p-6 text-sm text-muted">No table yet. It appears after the first refresh for this competition.</p>
        ) : null}
        {standings?.tables.map((t) => <StandingsTable key={t.group} table={t} />)}
      </main>
    </>
  );
}
