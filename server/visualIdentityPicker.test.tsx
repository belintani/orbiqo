// @vitest-environment jsdom

import React from "react";
import { useState } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { OrbiqoVisualIdentity } from "@shared/orbiqo";
import { VisualIdentityPicker } from "../client/src/components/VisualIdentityPicker";

const identity: OrbiqoVisualIdentity = {
  id: "signal",
  name: "Signal",
  description: "Blue, coral and mint tuned for a crisp contemporary presence.",
  tone: "Clear / contemporary",
  palette_id: 3,
  palette_name: "C4-SIGNAL-1",
  colors: ["#111111", "#219EBC", "#FF4D6D", "#80ED99"],
  visual_style: "pulse",
  angular_fill: 0.82,
  radial_fill: 0.8,
  recommended_for: "Services, wayfinding and communications",
  validation_status: "digital-validated",
  format_version: 3,
};

const pulseIdentity: OrbiqoVisualIdentity = {
  ...identity,
  id: "pulse",
  name: "Pulse",
  palette_id: 0,
  palette_name: "C4-PRINT-1",
  colors: ["#111111", "#00A6D6", "#D81B60", "#F0C808"],
  tone: "Signature / vivid",
};

describe("VisualIdentityPicker", () => {
  it("renders palette, technical profile, conformance and validation metadata", () => {
    const html = renderToStaticMarkup(
      <VisualIdentityPicker identities={[identity]} loading={false} selectedId="signal" onSelect={vi.fn()} />,
    );

    expect(html).toContain("Signal");
    expect(html).toContain("C4-SIGNAL-1");
    expect(html).toContain("Clear / contemporary");
    expect(html).toContain("pulse profile");
    expect(html).toContain("Registered · v3");
    expect(html).toContain("Validated");
    const normalizedHtml = html.toLowerCase();
    for (const color of identity.colors) expect(normalizedHtml).toContain(color.toLowerCase());
  });

  it("changes the active radio state when a template is selected", async () => {
    function Harness() {
      const [selectedId, setSelectedId] = useState<"pulse" | "signal">("pulse");
      return (
        <VisualIdentityPicker
          identities={[pulseIdentity, identity]}
          loading={false}
          selectedId={selectedId}
          onSelect={value => setSelectedId(value as "pulse" | "signal")}
        />
      );
    }

    const user = userEvent.setup();
    render(<Harness />);
    const pulse = screen.getByRole("radio", { name: /^Pulse\b/i });
    const signal = screen.getByRole("radio", { name: /^Signal\b/i });
    expect(pulse.getAttribute("aria-checked")).toBe("true");
    expect(signal.getAttribute("aria-checked")).toBe("false");

    await user.click(signal);

    expect(pulse.getAttribute("aria-checked")).toBe("false");
    expect(signal.getAttribute("aria-checked")).toBe("true");
  });
});
