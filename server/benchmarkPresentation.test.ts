import { describe, expect, it } from "vitest";
import { externalTimingCopy } from "../client/src/lib/benchmarkPresentation";

describe("benchmark timing presentation", () => {
  it("distinguishes raster production from the encoder core", () => {
    expect(externalTimingCopy.eyebrow).toBe("Equal-area raster production");
    expect(externalTimingCopy.rasterLabel).toBe("RASTER");
    expect(externalTimingCopy.scope).toContain("not encoder-only");
    expect(externalTimingCopy.scope).toContain("2× supersampling");
  });
});
