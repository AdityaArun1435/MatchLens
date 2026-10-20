import type { StandingTable } from "@/lib/live/types";
import { Crest } from "./Bits";

const formClass = (c: string) => (c === "W" ? "bg-accent/80" : c === "L" ? "bg-danger/80" : "bg-muted/60");

export function StandingsTable({ table }: { table: StandingTable }) {
  return (
    <section className="card mb-4 overflow-x-auto">
      {table.group ? <h2 className="border-b border-line px-3 py-2 text-xs font-semibold uppercase tracking-wide text-muted">{table.group.replace("_", " ")}</h2> : null}
      <table className="w-full min-w-[34rem] text-sm tabular-nums">
        <thead>
          <tr className="text-left text-xs text-muted">
            <th className="w-8 px-3 py-2">#</th>
            <th className="py-2">Team</th>
            <th className="px-2 text-right">P</th>
            <th className="px-2 text-right">W</th>
            <th className="px-2 text-right">D</th>
            <th className="px-2 text-right">L</th>
            <th className="px-2 text-right">GD</th>
            <th className="px-2 text-right">Pts</th>
            <th className="px-3 text-right">Form</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {table.rows.map((r) => (
            <tr key={r.position}>
              <td className="px-3 py-2 text-muted">{r.position}</td>
              <td className="py-2">
                <span className="flex items-center gap-2"><Crest team={r.team} size={20} />{r.team.short}</span>
              </td>
              <td className="px-2 text-right">{r.played}</td>
              <td className="px-2 text-right">{r.won}</td>
              <td className="px-2 text-right">{r.draw}</td>
              <td className="px-2 text-right">{r.lost}</td>
              <td className="px-2 text-right">{r.goalDifference > 0 ? `+${r.goalDifference}` : r.goalDifference}</td>
              <td className="px-2 text-right font-semibold">{r.points}</td>
              <td className="px-3">
                <span className="flex justify-end gap-0.5">
                  {(r.form ?? "").split(",").filter(Boolean).slice(-5).map((c, i) => (
                    <span key={i} className={`h-2 w-2 rounded-full ${formClass(c)}`} title={c} />
                  ))}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
