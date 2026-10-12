import { useEffect, useRef, useState } from "react";

/** Tracks an element's pixel width so an SVG can be drawn at its real size (text stays readable on phones). */
export function useElementWidth<T extends HTMLElement>(fallback = 640) {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(fallback);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => {
      const w = Math.round(el.getBoundingClientRect().width);
      if (w > 0) setWidth(w);
    };
    update();
    if (typeof ResizeObserver === "undefined") return; // older test environments
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return [ref, width] as const;
}
