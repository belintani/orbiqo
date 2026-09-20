import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

describe("production native runtime", () => {
  it("ships only the native codec, image and external comparison runtimes", () => {
    const dockerfile = readFileSync(path.join(projectRoot, "Dockerfile"), "utf8");

    expect(dockerfile).not.toContain("python3");
    expect(dockerfile).not.toContain("python3-venv");
    expect(dockerfile).not.toContain("ORBIQO_BRIDGE_PATH");
    expect(dockerfile).not.toContain("ORBIQO_RADIALCODE_ROOT");
    expect(dockerfile).toContain("libzxing-dev");
    expect(dockerfile).toContain("ORBIQO_NATIVE_PATH=/app/server/python/native/orbiqo_native");
    expect(dockerfile).toContain("ORBIQO_EXTERNAL_COMPARE_PATH=/app/benchmark/native/orbiqo_external_compare");
    expect(dockerfile).toContain("ORBIQO_JAB_ROOT=/app/benchmark/jabcode-runtime");
    expect(dockerfile).toContain("make -C benchmark/jabcode-runtime/jabcodeReader");
    expect(dockerfile).toContain("mkdir -p benchmark/jabcode-runtime/jabcode/build");
    expect(dockerfile).toContain("-no-pie");
    expect(dockerfile).toContain("make -C server/python/native");
    expect(dockerfile).toContain("make -C benchmark/native");
  });

  it("keeps the C++ executables at the paths consumed by the Node adapter", () => {
    const adapter = readFileSync(path.join(projectRoot, "server", "orbiqoNative.ts"), "utf8");
    expect(adapter).toContain('"python", "native"');
    expect(adapter).toContain('"benchmark", "native"');
  });

  it("does not wire the Python bridge into production procedures", () => {
    const router = readFileSync(path.join(projectRoot, "server", "routers", "orbiqo.ts"), "utf8");
    expect(router).not.toContain("orbiqoPython");
    expect(router).not.toContain("callOrbiqoPython");
  });
});
