"use client";

import clsx from "clsx";
import type { FilterKey } from "@/lib/types";

const TABS: { key: FilterKey; label: string }[] = [
  { key: "all", label: "All" },
  { key: "inbound", label: "Inbound" },
  { key: "outbound", label: "Outbound" },
  { key: "needs_action", label: "Needs Action" },
];

export function Filters({
  active,
  onChange,
  needsActionCount,
  resultCount,
}: {
  active: FilterKey;
  onChange: (k: FilterKey) => void;
  needsActionCount: number;
  resultCount: number;
}) {
  return (
    <div className="filters">
      <div className="tabs">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => onChange(t.key)}
            className={clsx("tab", active === t.key && "on")}
          >
            {t.label}
            {t.key === "needs_action" && needsActionCount > 0 && (
              <span className="tab-count">{needsActionCount}</span>
            )}
          </button>
        ))}
      </div>
      <span className="filters-meta">
        {resultCount} {resultCount === 1 ? "call" : "calls"}
      </span>
    </div>
  );
}
