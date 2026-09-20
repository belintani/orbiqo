import { describe, expect, it } from "vitest";
import type { TrpcContext } from "./_core/context";
import { appRouter } from "./routers";

function createPublicContext(): TrpcContext {
  return {
    user: null,
    req: { protocol: "https", headers: {} } as TrpcContext["req"],
    res: {} as TrpcContext["res"],
  };
}

describe("orbiqo visual identity tRPC contract", () => {
  it("lists the registered identity catalog", async () => {
    const catalog = await appRouter.createCaller(createPublicContext()).orbiqo.identities();
    expect(catalog.default_identity_id).toBe("pulse");
    expect(catalog.identities).toHaveLength(5);
    expect(catalog.identities.find(identity => identity.id === "signal")).toMatchObject({
      palette_id: 3,
      palette_name: "C4-SIGNAL-1",
      visual_style: "pulse",
      validation_status: "digital-validated",
      format_version: 5,
    });
  });

  it("passes identityId through generation and returns the encoded palette", async () => {
    const generated = await appRouter.createCaller(createPublicContext()).orbiqo.generate({
      payloadType: "url",
      text: "https://orbiqo.local/router-identity",
      geometry: "small",
      diameterMm: 30,
      alphabet: "color4",
      ecc: "balanced",
      compression: "auto",
      dpi: 600,
      centerMark: "OQ",
      identityId: "terra",
    });

    expect(generated.metadata).toMatchObject({
      identity_id: "terra",
      identity_name: "Terra",
      palette_id: 2,
      palette_name: "C4-TERRA-1",
      center_image_applied: false,
      center_image_host: null,
    });
  }, 20_000);

  it("uses the native decoder by default for canonical frontal PNGs", async () => {
    const caller = appRouter.createCaller(createPublicContext());
    const generated = await caller.orbiqo.generate({
      payloadType: "text",
      text: "canonical-native-default",
      geometry: "small",
      diameterMm: 30,
      alphabet: "color4",
      ecc: "balanced",
      compression: "none",
      dpi: 600,
      identityId: "pulse",
    });

    const decoded = await caller.orbiqo.decode({
      imageBase64: generated.png_base64,
      canonical: true,
      outputSize: 1024,
      erasureThreshold: 0.55,
    });

    expect(decoded.decoder_backend).toBe("native-cpp");
    expect(decoded.decoder_fallback_reason).toBeNull();
    expect(decoded.text).toBe("canonical-native-default");
  }, 30_000);

  it("runs native protocol generation and decode without the Python bridge", async () => {
    const caller = appRouter.createCaller(createPublicContext());
    const generated = await caller.orbiqo.generate({
      payloadType: "text",
      text: "direct-native-core",
      sizingMode: "manual",
      geometry: "small",
      diameterMm: 30,
      alphabet: "color4",
      ecc: "balanced",
      compression: "none",
      dpi: 600,
      protocolBackend: "native-cpp",
    });

    expect(generated.metadata.raster_renderer).toBe("cpp-native-full");
    const decoded = await caller.orbiqo.decode({
      imageBase64: generated.png_base64,
      canonical: true,
      decoderBackend: "native-cpp",
    });

    expect(decoded.decoder_backend).toBe("native-cpp");
    expect(Buffer.from(decoded.payload_base64, "base64").toString("utf8")).toBe("direct-native-core");
  }, 30_000);

  it("rejects an unknown raster backend before invoking the bridge", async () => {
    await expect(
      appRouter.createCaller(createPublicContext()).orbiqo.generate({
        payloadType: "text",
        text: "native renderer validation",
        geometry: "small",
        diameterMm: 30,
        alphabet: "color4",
        ecc: "balanced",
        rasterBackend: "unknown" as never,
      }),
    ).rejects.toMatchObject({ code: "BAD_REQUEST" });
  });

  it("rejects a non-HTTPS center image URL before invoking the bridge", async () => {
    await expect(
      appRouter.createCaller(createPublicContext()).orbiqo.generate({
        payloadType: "text",
        text: "center URL validation",
        geometry: "small",
        diameterMm: 30,
        alphabet: "color4",
        ecc: "balanced",
        centerImageUrl: "http://example.com/mark.png",
      }),
    ).rejects.toMatchObject({ code: "BAD_REQUEST" });
  });

  it("rejects a center image URL above the configured contract limit", async () => {
    const tooLongUrl = `https://example.com/${"a".repeat(2_050)}`;
    await expect(
      appRouter.createCaller(createPublicContext()).orbiqo.generate({
        payloadType: "text",
        text: "center URL validation",
        geometry: "small",
        diameterMm: 30,
        alphabet: "color4",
        ecc: "balanced",
        centerImageUrl: tooLongUrl,
      }),
    ).rejects.toMatchObject({ code: "BAD_REQUEST" });
  });

  it("rejects an HTTPS center image URL that resolves to loopback", async () => {
    await expect(
      appRouter.createCaller(createPublicContext()).orbiqo.generate({
        payloadType: "text",
        text: "center URL validation",
        geometry: "small",
        diameterMm: 30,
        alphabet: "color4",
        ecc: "balanced",
        centerImageUrl: "https://127.0.0.1/mark.png",
      }),
    ).rejects.toMatchObject({ code: "BAD_REQUEST" });
  });

  it.each([
    [26, 0, "micro-2", 16],
    [27, 5, "micro-4", 18],
    [106, 5, "micro-4", 18],
    [107, 1, "small", 30],
    [335, 2, "medium", 40],
    [547, 3, "large", 50],
    [735, 4, "xl", 70],
  ] as const)("recommends the smallest geometry for %i bytes", async (length, version, name, diameter) => {
    const payloadBase64 = Buffer.alloc(length, 0x5a).toString("base64");
    const recommendation = await appRouter.createCaller(createPublicContext()).orbiqo.recommendSizing({
      payloadType: "binary",
      payloadBase64,
      alphabet: "color4",
      ecc: "balanced",
      compression: "none",
    });

    expect(recommendation).toMatchObject({
      geometry_version: version,
      geometry_name: name,
      recommended_diameter_mm: diameter,
      payload_bytes: length,
      compression: "NONE",
    });
  });

  it("recommends Micro 1 for up to 16 bytes only when Fast ECC is selected", async () => {
    const recommendation = await appRouter.createCaller(createPublicContext()).orbiqo.recommendSizing({
      payloadType: "binary",
      payloadBase64: Buffer.alloc(16, 0x5a).toString("base64"),
      alphabet: "color4",
      ecc: "fast",
      compression: "none",
    });

    expect(recommendation).toMatchObject({
      geometry_version: 6,
      geometry_name: "micro-1",
      recommended_diameter_mm: 16,
      maximum_uncompressed_payload_bytes: 16,
    });
  });

  it("generates and decodes a manual Micro 1 symbol", async () => {
    const caller = appRouter.createCaller(createPublicContext());
    const payload = Buffer.from("micro-one");
    const generated = await caller.orbiqo.generate({
      payloadType: "binary",
      payloadBase64: payload.toString("base64"),
      sizingMode: "manual",
      geometry: "micro-1",
      diameterMm: 16,
      alphabet: "color4",
      ecc: "fast",
      compression: "none",
      dpi: 600,
      centerMark: "OQ",
      identityId: "pulse",
    });

    expect(generated.metadata).toMatchObject({
      geometry_version: 6,
      geometry_name: "micro-1",
      columns: 266,
      ecc_level: "FAST",
      maximum_uncompressed_payload_bytes: 16,
    });
    const decoded = await caller.orbiqo.decode({
      imageBase64: generated.png_base64,
      canonical: false,
      outputSize: 1024,
      erasureThreshold: 0.55,
    });
    expect(Buffer.from(decoded.payload_base64, "base64")).toEqual(payload);
    expect(decoded.geometry_version).toBe(6);
  }, 30_000);

  it("uses the recommended diameter in automatic generation", async () => {
    const caller = appRouter.createCaller(createPublicContext());
    const payload = Buffer.alloc(335, 0x5a);
    const generated = await caller.orbiqo.generate({
      payloadType: "binary",
      payloadBase64: payload.toString("base64"),
      sizingMode: "auto",
      geometry: "auto",
      alphabet: "color4",
      ecc: "balanced",
      compression: "none",
      dpi: 300,
      centerMark: "OQ",
      identityId: "pulse",
    });

    expect(generated.metadata).toMatchObject({
      sizing_mode: "auto",
      requested_geometry: "auto",
      geometry_version: 2,
      geometry_name: "medium",
      diameter_mm: 40,
      recommended_diameter_mm: 40,
    });

    const decoded = await caller.orbiqo.decode({
      imageBase64: generated.png_base64,
      canonical: false,
      outputSize: 1024,
      erasureThreshold: 0.55,
    });
    expect(Buffer.from(decoded.payload_base64, "base64")).toEqual(payload);
    expect(decoded.geometry_version).toBe(2);
  }, 30_000);

  it("bases the recommendation on the compressed frame", async () => {
    const recommendation = await appRouter.createCaller(createPublicContext()).orbiqo.recommendSizing({
      payloadType: "text",
      text: "A".repeat(700),
      alphabet: "color4",
      ecc: "balanced",
      compression: "auto",
    });

    expect(recommendation).toMatchObject({
      geometry_version: 0,
      geometry_name: "micro-2",
      recommended_diameter_mm: 16,
      payload_bytes: 700,
      compression: "DEFLATE",
    });
    expect(recommendation.frame_bytes).toBeLessThan(26);
  });

  it("preserves manual geometry and diameter overrides", async () => {
    const generated = await appRouter.createCaller(createPublicContext()).orbiqo.generate({
      payloadType: "text",
      text: "manual override",
      sizingMode: "manual",
      geometry: "large",
      diameterMm: 88,
      alphabet: "color4",
      ecc: "balanced",
      compression: "auto",
      dpi: 300,
      centerMark: "OQ",
      identityId: "pulse",
    });

    expect(generated.metadata).toMatchObject({
      sizing_mode: "manual",
      requested_geometry: "large",
      geometry_version: 3,
      diameter_mm: 88,
      recommended_diameter_mm: 50,
    });
  }, 20_000);

  it("rejects payloads above the XL capacity", async () => {
    await expect(
      appRouter.createCaller(createPublicContext()).orbiqo.recommendSizing({
        payloadType: "binary",
        payloadBase64: Buffer.alloc(923, 0x5a).toString("base64"),
        alphabet: "color4",
        ecc: "balanced",
        compression: "none",
      }),
    ).rejects.toMatchObject({ code: "BAD_REQUEST" });
  });

  it("generates Orbiqo, QR, Aztec and JAB from the exact same payload", async () => {
    const text = "https://orbiqo.dev/compare-four";
    const comparison = await appRouter.createCaller(createPublicContext()).orbiqo.compareSymbols({
      payloadType: "url",
      text,
      identityId: "pulse",
      centerMark: "OQ",
    });

    expect(Buffer.from(comparison.payload_base64, "base64").toString("utf8")).toBe(text);
    expect(comparison.payload_bytes).toBe(Buffer.byteLength(text));
    expect(comparison.items.map(item => item.id)).toEqual(["orbiqo", "qr", "aztec", "jab"]);
    expect(comparison).toMatchObject({ canvas_px: 1024, occupied_px: 900 });
    expect(comparison.ecc_comparability).toContain("not equivalent");

    for (const item of comparison.items) {
      const png = Buffer.from(item.png_base64, "base64");
      expect(png.subarray(0, 8).toString("hex")).toBe("89504e470d0a1a0a");
      expect(png.readUInt32BE(16)).toBe(1024);
      expect(png.readUInt32BE(20)).toBe(1024);
      expect(item.toolchain.length).toBeGreaterThan(4);
      expect(item.reported_ecc.length).toBeGreaterThan(0);
    }
  }, 45_000);
});
