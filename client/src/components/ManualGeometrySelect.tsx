import React from "react";
import { ChevronDown } from "lucide-react";
import type { OrbiqoGeometry } from "@shared/orbiqo";

export const MANUAL_GEOMETRY_OPTIONS: ReadonlyArray<{ value: OrbiqoGeometry; label: string }> = [
  { value: "micro-1", label: "Micro 1 · 1 ring · 16 B · Fast only · ID 6" },
  { value: "micro-2", label: "Micro 2 · 2 rings · ID 0" },
  { value: "micro-4", label: "Micro 4 · 4 rings · ID 5" },
  { value: "small", label: "Small · 12 rings · ID 1" },
  { value: "medium", label: "Medium · 18 rings · ID 2" },
  { value: "large", label: "Large · 24 rings · ID 3" },
  { value: "xl", label: "XL · 30 rings · ID 4" },
];

export function resolveManualGeometryDefaults(value: OrbiqoGeometry) {
  return value === "micro-1"
    ? { geometry: value, ecc: "fast" as const, diameterMm: 16 }
    : { geometry: value, ecc: undefined, diameterMm: undefined };
}

type ManualGeometrySelectProps = {
  value: OrbiqoGeometry;
  onChange: (value: OrbiqoGeometry) => void;
};

export function ManualGeometrySelect({ value, onChange }: ManualGeometrySelectProps) {
  return (
    <div className="field-stack">
      <label className="field-label" htmlFor="manual-geometry">Geometry</label>
      <div className="select-wrap">
        <select
          id="manual-geometry"
          aria-label="Geometry"
          value={value}
          onChange={event => onChange(event.target.value as OrbiqoGeometry)}
        >
          {MANUAL_GEOMETRY_OPTIONS.map(option => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
        <ChevronDown size={15} />
      </div>
    </div>
  );
}
