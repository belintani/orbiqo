import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { resolveBridgePath } from "./orbiqoPython";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

describe("production Python runtime", () => {
  it("ships the interpreter, vendored reference and comparison dependencies required by the real bridge", () => {
    const dockerfile = readFileSync(path.join(projectRoot, "Dockerfile"), "utf8");

    expect(dockerfile).toContain("python3");
    expect(dockerfile).toContain("python3-venv");
    expect(dockerfile).toContain("/app/server/python/vendor/radialcode[vision]");
    expect(dockerfile).toContain("ORBIQO_BRIDGE_PATH=/app/server/python/orbiqo_bridge.py");
    expect(dockerfile).toContain("ORBIQO_RADIALCODE_ROOT=/app/server/python/vendor/radialcode");
    expect(dockerfile).toContain("ORBIQO_JAB_ROOT=/app/benchmark/jabcode-runtime");
    expect(dockerfile).toContain("PATH=/opt/orbiqo-venv/bin:$PATH");
    expect(dockerfile).toContain("make -C benchmark/jabcode-runtime/jabcodeReader");
    expect(dockerfile).toContain("mkdir -p benchmark/jabcode-runtime/jabcode/build");
    expect(dockerfile).toContain("-no-pie");
    expect(dockerfile).toContain("make -C server/python/native");
  });

  it("keeps the bridge outside dist because esbuild does not copy Python source files", () => {
    expect(resolveBridgePath("/app", undefined)).toBe("/app/server/python/orbiqo_bridge.py");
    expect(resolveBridgePath("/app", "/custom/bridge.py")).toBe("/custom/bridge.py");
  });
});
