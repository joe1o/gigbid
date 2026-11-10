// hooks.ts - small React helpers.
import { useCallback, useEffect, useRef, useState } from "react";

/** Load data with loading/error states. Optionally re-poll every `pollMs` while `keepPolling(data)` is true. */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[] = [], pollMs = 0, keepPolling?: (d: T) => boolean) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  const reload = useCallback(async () => {
    try {
      const d = await fnRef.current();
      setData(d);
      setError(null);
      return d;
    } catch (e) {
      setError((e as Error).message);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  // Load when the inputs (deps) change.
  useEffect(() => {
    setLoading(true);
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  // Polling: after EVERY load (automatic or a manual reload()), decide whether to check again.
  // (A one-shot loop would stop for good if the first load had nothing to wait for - e.g. an
  // empty inbox - and then miss jobs started later by "Find new jobs".)
  const keepRef = useRef(keepPolling);
  keepRef.current = keepPolling;
  useEffect(() => {
    if (!pollMs || data === null) return;
    if (keepRef.current && !keepRef.current(data)) return;
    const timer = window.setTimeout(reload, pollMs);
    return () => window.clearTimeout(timer);
  }, [data, pollMs, reload]);

  return { data, error, loading, reload, setData };
}

/** Listen to a Server-Sent Events stream of JSON events (the live run viewer). */
export function useEventStream<T>(url: string | null) {
  const [events, setEvents] = useState<T[]>([]);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!url) return;
    setEvents([]);
    const es = new EventSource(url, { withCredentials: true });
    es.onopen = () => setOpen(true);
    es.onmessage = (m) => setEvents((prev) => [...prev, JSON.parse(m.data) as T]);
    es.onerror = () => setOpen(false);
    return () => es.close();
  }, [url]);
  return { events, open };
}
