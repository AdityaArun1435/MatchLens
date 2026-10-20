import Link from "next/link";
import { notFound } from "next/navigation";
import { MatchList } from "@/components/live/MatchList";
import { SiteNav } from "@/components/live/SiteNav";
import { COMPETITIONS } from "@/lib/live/competitions";

export default async function Fixtures({ params }: { params: Promise<{ code: string }> }) {
  const code = (await params).code.toUpperCase();
  const comp = COMPETITIONS.find((c) => c.code === code);
  if (!comp) notFound();
  return (
    <>
      <SiteNav active={`fixtures/${code}`} />
      <main className="mx-auto max-w-4xl px-4 py-6">
        <h1 className="display mb-1 text-3xl font-bold">{comp.name} fixtures</h1>
        <p className="mb-4 text-sm text-muted">Last 2 days and next 7 days.</p>
        <MatchList range={{ kind: "window", backDays: 2, forwardDays: 7 }} competition={code} groupBy="date" emptyText="No fixtures in this window." />
        <p className="mt-6 text-sm"><Link className="text-accent underline" href={`/standings/${code}`}>View the {comp.name} table</Link></p>
      </main>
    </>
  );
}
