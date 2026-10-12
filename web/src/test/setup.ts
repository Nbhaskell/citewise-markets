import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks(); // first: a test may have made localStorage throw, and clearing it below must work
  vi.unstubAllGlobals();
  window.localStorage.clear(); // saved conversations must never leak between tests
});
