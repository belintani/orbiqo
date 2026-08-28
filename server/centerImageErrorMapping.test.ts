import { describe, expect, it } from "vitest";
import { describeCenterImageError } from "../client/src/lib/centerImageError";

describe("center image bridge error mapping", () => {
  it("translates a bridge reachability failure into the generator-safe message", () => {
    expect(describeCenterImageError("center image host could not be resolved")).toBe(
      "The image could not be reached. Check that the public HTTPS URL is available.",
    );
  });

  it("translates bridge format and host-policy failures", () => {
    expect(describeCenterImageError("center image PNG, JPEG, or WebP required")).toContain("PNG, JPEG, or WebP");
    expect(describeCenterImageError("center image forbidden host")).toContain("not publicly reachable");
  });
});
