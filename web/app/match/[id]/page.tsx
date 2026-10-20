"use client";

import { useParams } from "next/navigation";
import { MatchView } from "@/components/MatchView";

export default function MatchPage() {
  const { id } = useParams<{ id: string }>();
  return <MatchView matchId={Number(id)} />;
}
