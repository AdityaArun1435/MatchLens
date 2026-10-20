/** Competitions shown in the navigation. The refresh job fills the data; this list only drives links and labels. */
export const COMPETITIONS: { code: string; name: string }[] = [
  { code: "PL", name: "Premier League" },
  { code: "PD", name: "La Liga" },
  { code: "SA", name: "Serie A" },
  { code: "BL1", name: "Bundesliga" },
  { code: "FL1", name: "Ligue 1" },
  { code: "CL", name: "Champions League" },
  { code: "DED", name: "Eredivisie" },
  { code: "PPL", name: "Primeira Liga" },
  { code: "ELC", name: "Championship" },
];

export const LIVE_POLL_MS = 30_000;
export const IDLE_POLL_MS = 60_000;
