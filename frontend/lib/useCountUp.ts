import { useEffect, useRef, useState } from "react";

/** Animate a number from its previous value to `target` (eased). Used for the money/stat
 * counters that tick up as calls land — the small delight that sells the dashboard. */
export function useCountUp(target: number, durationMs = 900): number {
  const [value, setValue] = useState(target);
  const fromRef = useRef(target);

  useEffect(() => {
    const from = fromRef.current;
    if (from === target) return;
    const start = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / durationMs);
      const eased = 1 - Math.pow(1 - p, 3);
      const current = from + (target - from) * eased;
      setValue(current);
      if (p < 1) {
        raf = requestAnimationFrame(tick);
      } else {
        fromRef.current = target;
        setValue(target);
      }
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, durationMs]);

  return value;
}
