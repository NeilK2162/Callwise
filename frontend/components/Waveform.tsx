"use client";

import { useEffect, useRef } from "react";

type WaveformProps = {
  bars?: number;
  className?: string;
  height?: number;
  animated?: boolean;
  speaking?: boolean;
};

export function Waveform({
  bars = 44,
  className = "wave",
  height = 54,
  animated = true,
  speaking = true,
}: WaveformProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!animated || !ref.current) return;
    const els = ref.current.querySelectorAll("i");
    let t = 0;
    let frame = 0;

    const loop = () => {
      t += 0.08;
      els.forEach((el, i) => {
        const base = Math.sin(i * 0.55 + t) * 0.5 + 0.5;
        const n = Math.sin(i * 1.7 - t * 1.3) * 0.5 + 0.5;
        const amp = speaking ? 0.25 + 0.75 * base * n : 0.08 + 0.05 * base;
        const h = 4 + amp * height;
        (el as HTMLElement).style.height = `${h.toFixed(1)}px`;
      });
      frame = requestAnimationFrame(loop);
    };

    frame = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(frame);
  }, [animated, height, speaking]);

  return (
    <div ref={ref} className={className}>
      {Array.from({ length: bars }, (_, i) => (
        <i key={i} />
      ))}
    </div>
  );
}

export function StaticWave({
  bars,
  className = "wave",
  seed = 0,
}: {
  bars: number;
  className?: string;
  seed?: number;
}) {
  return (
    <div className={className}>
      {Array.from({ length: bars }, (_, i) => {
        const h = 4 + Math.abs(Math.sin(i * 0.6 + seed)) * 28;
        return <i key={i} style={{ height: `${h.toFixed(0)}px` }} />;
      })}
    </div>
  );
}

export function FinalWave() {
  return (
    <div className="wave2">
      {Array.from({ length: 60 }, (_, i) => {
        const h = 6 + Math.abs(Math.sin(i * 0.4)) * 38;
        const opacity = 0.35 + 0.5 * Math.abs(Math.sin(i * 0.4));
        return <i key={i} style={{ height: `${h.toFixed(0)}px`, opacity }} />;
      })}
    </div>
  );
}
