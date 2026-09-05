import { useEffect, useRef, useState } from "react";

export const API = (import.meta as any).env?.VITE_API ?? "http://localhost:8000";

export async function get<T = any>(path: string): Promise<T> {
  const r = await fetch(API + path);
  return r.json();
}
export async function post<T = any>(path: string, body?: any): Promise<T> {
  const r = await fetch(API + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  return r.json();
}

export type Evt = { kind: string; ts: string; data: any };

/** Subscribe to the backend SSE stream. */
export function useEventStream(onEvent: (e: Evt) => void) {
  const [connected, setConnected] = useState(false);
  const cb = useRef(onEvent);
  cb.current = onEvent;
  useEffect(() => {
    const es = new EventSource(API + "/stream");
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);
    es.onmessage = (m) => {
      try {
        cb.current(JSON.parse(m.data));
      } catch {}
    };
    return () => es.close();
  }, []);
  return connected;
}

/** Poll a JSON endpoint on an interval. */
export function usePoll<T>(path: string, ms: number, deps: any[] = []): T | null {
  const [data, setData] = useState<T | null>(null);
  useEffect(() => {
    let alive = true;
    const tick = () => get<T>(path).then((d) => alive && setData(d)).catch(() => {});
    tick();
    const id = setInterval(tick, ms);
    return () => {
      alive = false;
      clearInterval(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return data;
}

export const inr = (n: number) =>
  "₹" + Math.round(n || 0).toLocaleString("en-IN");
