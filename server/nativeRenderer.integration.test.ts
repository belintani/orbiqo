import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import { callOrbiqoPython } from "./orbiqoPython";

const nativeDirectory = resolve(process.cwd(), "server/python/native");
const nativeExecutable = resolve(nativeDirectory, "orbiqo_renderer");

describe("native C++ raster renderer", () => {
  beforeAll(() => {
    execFileSync("make", ["-C", nativeDirectory, "all"], { stdio: "pipe" });
    expect(existsSync(nativeExecutable)).toBe(true);
  }, 30_000);

  it("renders an encoded symbol that the reference decoder reads exactly", async () => {
    const generated = await callOrbiqoPython<{
      png_base64: string;
      metadata: { raster_backend_requested: string; raster_renderer: string; native_fallback_reason: string | null };
    }>({
      op: "generate",
      payload_type: "url",
      text: "https://orbiqo.local/native-raster",
      sizing_mode: "manual",
      geometry: "small",
      diameter_mm: 30,
      alphabet: "color4",
      ecc: "balanced",
      compression: "auto",
      center_mark: "",
      dpi: 300,
      identity_id: "pulse",
      raster_backend: "native-experimental",
    });

    expect(generated.metadata.raster_backend_requested).toBe("native-experimental");
    expect(generated.metadata.raster_renderer).toBe("cpp-native-experimental");
    expect(generated.metadata.native_fallback_reason).toBeNull();

    const decoded = await callOrbiqoPython<{ text: string }>({
      op: "decode",
      image_base64: generated.png_base64,
      canonical: false,
      output_size: 1024,
      erasure_threshold: 0.55,
    });
    expect(decoded.text).toBe("https://orbiqo.local/native-raster");
  }, 30_000);

  it("keeps center text on the reference renderer until native parity exists", async () => {
    const generated = await callOrbiqoPython<{
      metadata: { raster_renderer: string; native_fallback_reason: string | null };
    }>({
      op: "generate",
      payload_type: "text",
      text: "fallback",
      sizing_mode: "manual",
      geometry: "small",
      diameter_mm: 30,
      ecc: "balanced",
      center_mark: "OQ",
      dpi: 300,
      identity_id: "pulse",
      raster_backend: "native-experimental",
    });

    expect(generated.metadata.raster_renderer).toBe("python-reference-fallback");
    expect(generated.metadata.native_fallback_reason).toContain("empty center");
  }, 30_000);
});
