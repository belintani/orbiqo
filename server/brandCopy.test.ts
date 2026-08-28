import { describe, expect, it } from "vitest";
import { brandCopy } from "../client/src/lib/brandCopy";

describe("brand copy", () => {
  it("presents Orbiqo as the visible product and RadialCode only as its technical reference", () => {
    expect(`${brandCopy.heroLead} ${brandCopy.heroEmphasis}`).toBe("Give a round touchpoint a face and an action.");
    expect(brandCopy.productDescription).toContain("reserved non-functional center");
    expect(brandCopy.productDescription).toContain("destination or message");
    expect(brandCopy.productDescription).not.toContain("COLOR4");
    expect(brandCopy.adoptionPitch.reasons[2].body).not.toContain("COLOR4");
    expect(brandCopy.productDescription).not.toMatch(/QR|Aztec|JAB|trust/i);
    expect(brandCopy.artifactAttribution).toBe("Orbiqo protocol · reference implementation: RadialCode");
    expect(brandCopy.footerProtocol).toContain("Orbiqo Protocol");
    expect(brandCopy.footerProtocol).toContain("Reference implementation: RadialCode");
  });

  it("frames circular geometry as a compositional advantage rather than an unmeasured performance claim", () => {
    expect(brandCopy.circularPositioning.footprint).toContain("63.7%");
    expect(brandCopy.circularPositioning.footprintLimit).toContain("does not imply 63.7% more payload");
    expect(brandCopy.circularPositioning.benchmarkLimit).toContain("does not automatically beat QR, Aztec or JAB");
    expect(brandCopy.adoptionPitch.description).toContain("not a square label added at the end");
    expect(brandCopy.adoptionPitch.reasons[1].body).toContain("not payload");
    expect(brandCopy.adoptionPitch.description).not.toMatch(/faster|more payload|better scan/i);
  });
});
