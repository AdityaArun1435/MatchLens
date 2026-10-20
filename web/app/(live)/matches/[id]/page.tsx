import { notFound } from "next/navigation";
import { MatchLive } from "@/components/live/MatchLive";
import { SiteNav } from "@/components/live/SiteNav";

export default async function MatchPage({ params }: { params: Promise<{ id: string }> }) {
  const id = Number((await params).id);
  if (!Number.isInteger(id) || id <= 0) notFound();
  return (
    <>
      <SiteNav />
      <main className="mx-auto max-w-4xl px-4 py-6">
        <MatchLive id={id} />
      </main>
    </>
  );
}
