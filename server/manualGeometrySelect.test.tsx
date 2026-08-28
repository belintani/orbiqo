// @vitest-environment jsdom

import React, { useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MANUAL_GEOMETRY_OPTIONS, ManualGeometrySelect, resolveManualGeometryDefaults } from "../client/src/components/ManualGeometrySelect";

afterEach(cleanup);

describe("ManualGeometrySelect", () => {
  it("renders Micro 1 as a Fast-only one-ring option", () => {
    render(<ManualGeometrySelect value="small" onChange={() => undefined} />);

    expect(MANUAL_GEOMETRY_OPTIONS).toHaveLength(7);
    expect(screen.getByRole("option", { name: "Micro 1 · 1 ring · 16 B · Fast only · ID 6" })).toBeTruthy();
  });

  it("emits micro-1 when the user selects the one-ring geometry", () => {
    const onChange = vi.fn();
    render(<ManualGeometrySelect value="small" onChange={onChange} />);

    fireEvent.change(screen.getByRole("combobox", { name: "Geometry" }), { target: { value: "micro-1" } });

    expect(onChange).toHaveBeenCalledWith("micro-1");
  });

  it("applies Fast ECC, 16 mm and the 16-byte nominal capacity for Micro 1", () => {
    function Harness() {
      const [geometry, setGeometry] = useState<"micro-1" | "small">("small");
      const [ecc, setEcc] = useState<"fast" | "balanced">("balanced");
      const [diameter, setDiameter] = useState(30);
      const capacity = geometry === "micro-1" && ecc === "fast" ? 16 : 334;

      return (
        <>
          <ManualGeometrySelect value={geometry} onChange={value => {
            const defaults = resolveManualGeometryDefaults(value);
            setGeometry(defaults.geometry as "micro-1" | "small");
            if (defaults.ecc) setEcc(defaults.ecc);
            if (defaults.diameterMm) setDiameter(defaults.diameterMm);
          }} />
          <output aria-label="Resolved manual sizing">{geometry} · {ecc} · {diameter} mm · {capacity} bytes</output>
        </>
      );
    }

    render(<Harness />);
    fireEvent.change(screen.getByRole("combobox", { name: "Geometry" }), { target: { value: "micro-1" } });

    expect(screen.getByLabelText("Resolved manual sizing").textContent).toBe("micro-1 · fast · 16 mm · 16 bytes");
  });
});
