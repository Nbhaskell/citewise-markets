import { renderHook, waitFor } from "@testing-library/react";
import { ApiError } from "../api/client";
import { useApi } from "./useApi";

describe("useApi", () => {
  it("returns the data once loaded", async () => {
    const { result } = renderHook(() => useApi(async () => "hello", []));
    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.data).toBe("hello"));
    expect(result.current).toMatchObject({ loading: false, error: null, errorStatus: null });
  });

  it("reports the HTTP status so pages can tell 'not found' from 'broken'", async () => {
    const { result } = renderHook(() => useApi(async () => Promise.reject(new ApiError("No such company", 404)), []));
    await waitFor(() => expect(result.current.error).toBe("No such company"));
    expect(result.current.errorStatus).toBe(404);
  });

  it("uses status 0 for a failure that isn't an API error", async () => {
    const { result } = renderHook(() => useApi(async () => Promise.reject(new Error("kaboom")), []));
    await waitFor(() => expect(result.current.error).toBe("kaboom"));
    expect(result.current.errorStatus).toBe(0);
  });

  it("loads again when its inputs change and when reload is called", async () => {
    const load = vi.fn(async () => "x");
    const { result, rerender } = renderHook(({ id }) => useApi(load, [id]), { initialProps: { id: 1 } });
    await waitFor(() => expect(result.current.data).toBe("x"));
    expect(load).toHaveBeenCalledTimes(1);

    rerender({ id: 2 });
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2));

    result.current.reload();
    await waitFor(() => expect(load).toHaveBeenCalledTimes(3));
  });

  it("cancels the request when the component goes away", async () => {
    let signal: AbortSignal | undefined;
    const { unmount } = renderHook(() =>
      useApi((s) => {
        signal = s;
        return new Promise<string>(() => undefined);
      }, []),
    );
    expect(signal?.aborted).toBe(false);
    unmount();
    expect(signal?.aborted).toBe(true);
  });
});
