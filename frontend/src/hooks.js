import { createContext, useContext, useEffect, useState } from "react";
import { api } from "./api";

// Run `fn` now and then every `ms` milliseconds. Returns [data, reload].
export function usePoll(fn, ms, deps = []) {
  const [data, setData] = useState(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true, timer;
    const run = async () => {
      try { const d = await fn(); if (alive) setData(d); } catch (_) {}
      if (alive) timer = setTimeout(run, ms);
    };
    run();
    return () => { alive = false; clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  return [data, () => setTick((t) => t + 1)];
}

export const ToastContext = createContext(() => {});
export const useToast = () => useContext(ToastContext);

// Returns a function that stops a running camera or starts a stopped one.
export function useCameraToggle(reload) {
  const toast = useToast();
  return async (cam) => {
    try {
      await api(`/api/cameras/${cam.id}/${cam.paused ? "start" : "stop"}`, { method: "POST" });
      reload();
    } catch (e) { toast(e.message, true); }
  };
}

export function ago(ts) {
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 60) return "just now";
  if (s < 3600) return Math.floor(s / 60) + " min ago";
  if (s < 86400) return Math.floor(s / 3600) + " h ago";
  return new Date(ts * 1000).toLocaleDateString([], { month: "short", day: "numeric" });
}

export const fmtTime = (ts) =>
  new Date(ts * 1000).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" });
