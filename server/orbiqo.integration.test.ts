import { describe, expect, it } from "vitest";
import { callOrbiqoPython, OrbiqoBridgeError } from "./orbiqoPython";

describe("Orbiqo Python reference bridge", () => {
  it("loads the real Draft 0.2–0.5-compatible Draft 0.6 reference package", async () => {
    const health = await callOrbiqoPython<{
      reference_version: string;
      supported_format_versions: number[];
      visual_identity_count: number;
    }>({ op: "health" });

    expect(health.reference_version).toBe("0.1.0a6");
    expect(health.supported_format_versions).toEqual([1, 2, 3, 4, 5]);
    expect(health.visual_identity_count).toBe(5);
  });

  it("publishes five registered visual identities with four COLOR4 states", async () => {
    const catalog = await callOrbiqoPython<{
      default_identity_id: string;
      custom_colors_supported: boolean;
      identities: Array<{ id: string; palette_id: number; colors: string[]; validation_status: string }>;
    }>({ op: "identities" });

    expect(catalog.default_identity_id).toBe("pulse");
    expect(catalog.custom_colors_supported).toBe(false);
    expect(catalog.identities.map(identity => identity.id)).toEqual([
      "reference", "pulse", "nocturne", "terra", "signal",
    ]);
    expect(catalog.identities.every(identity => identity.colors.length === 4)).toBe(true);
    expect(catalog.identities.every(identity => identity.validation_status === "digital-validated")).toBe(true);
  });

  it.each([
    ["reference", 0],
    ["pulse", 0],
    ["nocturne", 1],
    ["terra", 2],
    ["signal", 3],
  ] as const)("generates and detects the %s visual identity", async (identityId, paletteId) => {
    const generated = await callOrbiqoPython<{
      png_base64: string;
      metadata: {
        format_version: number;
        alphabet: string;
        attribution: string;
        visual_style: string;
        layout_name: string;
        columns: number;
        identity_id: string;
        identity_name: string;
        palette_id: number;
        palette_name: string;
        palette_colors: string[];
      };
    }>({
      op: "generate",
      payload_type: "url",
      text: "https://orbiqo.local/roundtrip",
      geometry: "small",
      diameter_mm: 30,
      alphabet: "color4",
      ecc: "balanced",
      compression: "auto",
      center_mark: "OQ",
      dpi: 600,
      identity_id: identityId,
    });

    expect(generated.metadata.format_version).toBe(5);
    expect(generated.metadata.layout_name).toBe("constant-columns");
    expect(generated.metadata.columns).toBe(160);
    expect(generated.metadata.alphabet).toBe("COLOR4");
    expect(generated.metadata.attribution).toContain("RadialCode");
    expect(generated.metadata.identity_id).toBe(identityId);
    expect(generated.metadata.palette_id).toBe(paletteId);
    expect(generated.metadata.palette_name).toMatch(/^C4-/);
    expect(generated.metadata.palette_colors).toHaveLength(4);

    const decoded = await callOrbiqoPython<{
      text: string;
      palette_id: number;
      palette_name: string;
      diagnostics: { average_confidence: number };
    }>({
      op: "decode",
      image_base64: generated.png_base64,
      canonical: false,
      output_size: 1024,
      erasure_threshold: 0.55,
    });
    expect(decoded.text).toBe("https://orbiqo.local/roundtrip");
    expect(decoded.palette_id).toBe(paletteId);
    expect(decoded.palette_name).toBe(generated.metadata.palette_name);
    expect(decoded.diagnostics.average_confidence).toBeGreaterThan(0.9);
  }, 30_000);

  it("rejects invalid images through a stable failure code", async () => {
    await expect(
      callOrbiqoPython({ op: "decode", image_base64: Buffer.from("not an image").toString("base64") }),
    ).rejects.toMatchObject<Partial<OrbiqoBridgeError>>({ bridgeCode: "INVALID_IMAGE" });
  });
});
