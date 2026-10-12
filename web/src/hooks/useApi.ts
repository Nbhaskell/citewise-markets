import { useCallback, useEffect, useState } from "react";
import { ApiError, isAbort } from "../api/client";

export interface ApiState<T> {
  data: T | null;
  error: string | null;
  /** HTTP status of the failed request (0 if the API couldn't be reached), or null if there was no error. */
  errorStatus: number | null;
  loading: boolean;
  reload: () => void;
}

/** Runs `load` on mount and whenever `deps` change; cancels the request if the component goes away first. */
export function useApi<T>(load: (signal: AbortSignal) => Promise<T>, deps: readonly unknown[] = []): ApiState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setErrorStatus(null);
    load(controller.signal)
      .then((result) => {
        setData(result);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (isAbort(err)) return;
        setError(err instanceof Error ? err.message : "Something went wrong.");
        setErrorStatus(err instanceof ApiError ? err.status : 0);
        setLoading(false);
      });
    return () => controller.abort();
    // `load` is recreated every render; `deps` says when a new request is really needed.
  }, [...deps, attempt]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  return { data, error, errorStatus, loading, reload };
}
