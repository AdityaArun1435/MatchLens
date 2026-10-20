"use client";

import { MOMENT_META } from "@/lib/format";
import type { Moment } from "@/lib/types";
import { MomentIcon } from "./MomentsTimeline";

/** The moments a paragraph is based on. Clicking one scrolls to it and highlights it. */
export function CiteChips({ cites, byId, onCite }: { cites: string[]; byId: Map<string, Moment>; onCite: (id: string) => void }) {
  return (
    <span className="mt-2 flex flex-wrap gap-1.5" lang="en">
      {cites.map((id) => {
        const m = byId.get(id);
        return (
          <button
            key={id}
            type="button"
            data-testid={`chip-${id}`}
            onClick={() => onCite(id)}
            title={m ? m.headline : id}
            className="inline-flex items-center gap-1.5 rounded-full border border-line bg-panel2 px-2.5 py-1 text-xs text-muted transition-colors hover:border-accent/60 hover:text-ink"
          >
            {m && <MomentIcon type={m.type} className="h-3 w-3" />}
            <span className="font-medium tabular-nums text-ink">{m ? m.clock_label : id}</span>
            <span>{m ? MOMENT_META[m.type].label : "moment"}</span>
          </button>
        );
      })}
    </span>
  );
}
