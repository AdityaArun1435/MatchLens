"use client";

import { useCallback, useEffect, useReducer, useRef } from "react";
import { API_URL } from "./api";
import type { Moment } from "./types";

export const SPEEDS = [1, 10, 30, 60] as const;
export type Speed = (typeof SPEEDS)[number];

export interface LiveEvent {
  t: number;
  clock: string;
  period: number;
  id: string;
  kind: string;
  team: string | null;
  player: string | null;
  outcome: string | null;
  xg: number | null;
  detail: { shot_type?: string; card?: string; replacement_display_name?: string; replacement?: string };
  in_play: boolean;
}

export interface LiveMoment extends Moment {
  anchor_t: number;
  caption: string | null;
}

export interface Hello {
  duration: number;
  periods: { period: number; start: number; end: number; label: string }[];
  home: string;
  away: string;
}

export interface LiveState {
  status: "connecting" | "live" | "closed" | "error";
  hello: Hello | null;
  t: number;
  clock: string;
  period: number;
  minute: number;
  score: [number, number];
  paused: boolean;
  speed: Speed;
  ended: boolean;
  events: LiveEvent[];
  moments: LiveMoment[];
  caption: { text: string; momentId: string; n: number } | null;
}

const initial: LiveState = {
  status: "connecting",
  hello: null,
  t: 0,
  clock: "1'",
  period: 1,
  minute: 0,
  score: [0, 0],
  paused: false,
  speed: 10,
  ended: false,
  events: [],
  moments: [],
  caption: null,
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Msg = { type: string } & Record<string, any>;
type Action = { kind: "message"; msg: Msg } | { kind: "status"; status: LiveState["status"] } | { kind: "restart" };

const KEEP_EVENTS = 40;

function toMoment(m: Msg): LiveMoment {
  return { ...(m.moment as Moment), anchor_t: m.anchor_t as number, caption: (m.caption as string | null) ?? null };
}

function reducer(s: LiveState, a: Action): LiveState {
  if (a.kind === "restart") return { ...initial, speed: s.speed };
  if (a.kind === "status") return { ...s, status: a.status };
  const m = a.msg;
  const time = { t: m.t as number, clock: m.clock as string, period: m.period as number, minute: m.minute as number };
  switch (m.type) {
    case "hello":
      return { ...s, status: "live", hello: m as unknown as Hello, speed: (m.speed as Speed) ?? s.speed };
    case "state":
      return { ...s, paused: m.paused as boolean, speed: m.speed as Speed };
    case "reset":
      return { ...s, events: [], moments: [], caption: null, ended: false, score: [0, 0] };
    case "catchup":
      return {
        ...s,
        ...time,
        score: m.score as [number, number],
        ended: m.ended as boolean,
        events: (m.events as LiveEvent[]).slice(-KEEP_EVENTS),
        moments: (m.moments as Msg[]).map(toMoment),
        caption: null,
      };
    case "tick":
      return { ...s, ...time, score: m.score as [number, number] };
    case "event":
      return { ...s, events: [...s.events, m as unknown as LiveEvent].slice(-KEEP_EVENTS) };
    case "score":
      return { ...s, score: m.score as [number, number] };
    case "moment": {
      const moment = toMoment(m);
      if (s.moments.some((x) => x.id === moment.id)) return s;
      const moments = [...s.moments, moment].sort((x, y) => x.first_index - y.first_index);
      const caption = moment.caption ? { text: moment.caption, momentId: moment.id, n: (s.caption?.n ?? 0) + 1 } : s.caption;
      return { ...s, moments, caption };
    }
    case "end":
      return { ...s, ...time, score: m.score as [number, number], ended: true };
    default:
      return s;
  }
}

function wsUrl(matchId: number, speed: number): string {
  return `${API_URL.replace(/^http/, "ws")}/matches/${matchId}/live?speed=${speed}`;
}

/** Connects to the replay WebSocket while `enabled`, and exposes the running state plus a command sender. */
export function useLiveReplay(matchId: number, enabled: boolean, firstSpeed: Speed = 10) {
  const [state, dispatch] = useReducer(reducer, { ...initial, speed: firstSpeed });
  const socket = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!enabled) return;
    const ws = new WebSocket(wsUrl(matchId, firstSpeed));
    socket.current = ws;
    ws.onmessage = (e) => dispatch({ kind: "message", msg: JSON.parse(e.data) });
    ws.onerror = () => dispatch({ kind: "status", status: "error" });
    ws.onclose = () => dispatch({ kind: "status", status: "closed" });
    return () => {
      ws.onclose = null;
      ws.close();
      socket.current = null;
    };
  }, [matchId, enabled, firstSpeed]);

  const send = useCallback((cmd: Record<string, unknown>) => {
    if (socket.current?.readyState === WebSocket.OPEN) socket.current.send(JSON.stringify(cmd));
  }, []);

  const restart = useCallback(() => {
    dispatch({ kind: "restart" });
    send({ cmd: "restart" });
  }, [send]);

  return { state, send, restart };
}
