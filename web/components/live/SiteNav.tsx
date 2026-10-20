import Link from "next/link";
import { COMPETITIONS } from "@/lib/live/competitions";

export function SiteNav({ active }: { active?: string }) {
  return (
    <header className="border-b border-line bg-panel/60 backdrop-blur">
      <div className="mx-auto flex max-w-4xl flex-wrap items-center gap-x-5 gap-y-2 px-4 py-3">
        <Link href="/" className="display text-xl font-bold tracking-wide text-accent">MatchLens</Link>
        <nav className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted" aria-label="Main">
          <Link href="/" className="hover:text-ink">Today</Link>
          <Link href="/fixtures/PL" className="hover:text-ink">Fixtures</Link>
          <Link href="/standings/PL" className="hover:text-ink">Standings</Link>
          <Link href="/classic" className="hover:text-ink">Classic matches</Link>
        </nav>
      </div>
      {active ? (
        <div className="mx-auto flex max-w-4xl gap-1 overflow-x-auto px-4 pb-2" aria-label="Competitions">
          {COMPETITIONS.map((c) => (
            <Link
              key={c.code}
              href={`/${active.split("/")[0]}/${c.code}`}
              className={`whitespace-nowrap rounded-full border px-3 py-1 text-xs ${
                active.split("/")[1] === c.code ? "border-accent text-accent" : "border-line text-muted hover:text-ink"
              }`}
            >
              {c.name}
            </Link>
          ))}
        </div>
      ) : null}
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="mx-auto max-w-4xl px-4 py-8 text-xs text-muted">
      Data: <a className="underline" href="https://www.football-data.org">football-data.org</a> and{" "}
      <a className="underline" href="https://www.api-football.com">API-Football</a>. Live scores refresh every few minutes, not by the second.
      MatchLens is an independent project, not affiliated with any league or club.
    </footer>
  );
}
