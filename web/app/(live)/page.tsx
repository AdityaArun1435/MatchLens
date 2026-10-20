import { MatchList } from "@/components/live/MatchList";
import { SiteNav } from "@/components/live/SiteNav";

export default function Home() {
  return (
    <>
      <SiteNav />
      <main className="mx-auto max-w-4xl px-4 py-6">
        <h1 className="display mb-4 text-3xl font-bold">Today</h1>
        <MatchList range={{ kind: "today" }} emptyText="No tracked matches today. Check Fixtures for what is coming up." />
      </main>
    </>
  );
}
