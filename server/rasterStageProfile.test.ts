import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

type RasterStageProfile = {
  method: { payload_bytes: number; ecc: string; scope: string };
  median_ms: {
    encoder_core: number;
    direct_png_renderer: number;
    png_open_convert: number;
    normalize_canvas: number;
    sequential_total: number;
  };
};

describe("Orbiqo raster-stage profile", () => {
  it("keeps encoder timing separate from PNG-ready raster production", () => {
    const source = readFileSync(resolve(process.cwd(), "benchmark/results/orbiqo_raster_stage_profile.json"), "utf8");
    const profile = JSON.parse(source) as RasterStageProfile;

    expect(profile.method).toMatchObject({ payload_bytes: 64, ecc: "balanced" });
    expect(profile.method.scope).toContain("not a cross-format benchmark");
    expect(profile.median_ms.encoder_core).toBeGreaterThan(0);
    expect(profile.median_ms.direct_png_renderer).toBeGreaterThan(profile.median_ms.encoder_core);
    expect(profile.median_ms.sequential_total).toBeGreaterThan(profile.median_ms.direct_png_renderer);
  });
});
