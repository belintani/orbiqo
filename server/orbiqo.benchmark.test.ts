import { describe, expect, it } from "vitest";
import {
  loadBenchmarkArtifacts,
  loadBenchmarkSummary,
  loadNormalizedBenchmarkArtifacts,
  loadNormalizedBenchmarkSummary,
  loadOptimizationDelta,
  loadEccProfileComparison,
  loadEccProfileComparisonArtifacts,
  loadNativeRendererComparison,
} from "./benchmarkResults";

describe("Orbiqo benchmark artifacts", () => {
  it("validates the published summary and all four toolchains", async () => {
    const summary = await loadBenchmarkSummary();
    expect(summary.adapters.map(item => item.format).sort()).toEqual(["aztec", "jab", "orbiqo", "qr"]);
    expect(summary.jab_status.included).toBe(true);
    expect(summary.capacity).toHaveLength(4);
    expect(summary.environment.scope).toContain("digital");
    expect(summary.orbiqo_perspective).toMatchObject({ successes: 14, trials: 16 });
  });

  it("publishes raw rows and a methodology that disclaims print claims", async () => {
    const artifacts = await loadBenchmarkArtifacts();
    expect(artifacts.rawCsv.split("\n").length).toBeGreaterThan(150);
    expect(artifacts.rawCsv).toContain("generation_time,orbiqo");
    expect(artifacts.methodology).toContain("digital-only");
    expect(artifacts.methodology).toContain("No result");
  });

  it("validates equal-area normalized capacity and adapter profiles", async () => {
    const summary = await loadNormalizedBenchmarkSummary();
    expect(summary.normalization).toMatchObject({ canvas_size: 1024, occupied_size: 900, minimum_feature_pitch_px: 7 });
    expect(summary.normalization.timing_payload_bytes).toBe(64);
    expect(summary.capacity.map(row => [row.format, row.maximum_payload_bytes])).toEqual([
      ["orbiqo", 922], ["qr", 713], ["aztec", 853], ["jab", 2093],
    ]);
    expect(summary.normalization.orbiqo_capacity_renderer).toContain("SVG/Cairo");
    expect(summary.normalization.orbiqo_product_renderer).toContain("725 DPI");
    expect(summary.adapters.find(row => row.format === "qr")?.reported_ecc).toBe("Q");
    expect(summary.environment.scope).toContain("digital-only normalized");
  });

  it("publishes normalized raw runs, capacity attempts, and methodology", async () => {
    const artifacts = await loadNormalizedBenchmarkArtifacts();
    expect(artifacts.rawCsv).toContain("normalized_clean");
    expect(artifacts.capacityCsv).toContain("nominal_pitch_px");
    expect(artifacts.methodology).toContain("900×900");
    expect(artifacts.methodology).toContain("no printing claims");
  });

  it("publishes explicit before/after optimization deltas", async () => {
    const delta = await loadOptimizationDelta();
    expect(delta.metrics.map(metric => metric.key)).toEqual(["capacity", "generation", "decode", "robustness"]);
    expect(delta.metrics.find(metric => metric.key === "capacity")).toMatchObject({ before: 571, after: 922 });
    expect(delta.metrics.find(metric => metric.key === "generation")).toMatchObject({ direction: "lower_is_better" });
    expect(delta.metrics.find(metric => metric.key === "generation")?.change_percent).toBeLessThan(-30);
    expect(delta.metrics.find(metric => metric.key === "decode")).toMatchObject({ direction: "lower_is_better" });
    expect(delta.metrics.find(metric => metric.key === "decode")?.change_percent).toBeCloseTo(-3.221035644418689, 6);
    expect(delta.orbiqo_degradation).toEqual({ before: 24, after: 29, trials: 32 });
  });

  it("publishes a separate practical comparison of the four Orbiqo protection profiles", async () => {
    const comparison = await loadEccProfileComparison();
    expect(comparison.method).toMatchObject({ payload_bytes: 64, timing_runs: 10 });
    expect(comparison.profiles.map(profile => profile.ecc)).toEqual(["fast", "balanced", "robust", "extreme"]);
    expect(comparison.profiles.find(profile => profile.ecc === "robust")?.occlusion.minimum_successes).toBe(3);
    expect(comparison.profiles.find(profile => profile.ecc === "extreme")?.occlusion.minimum_successes).toBe(0);
    expect(comparison.limitations.join(" ")).toContain("digital");

    const artifacts = await loadEccProfileComparisonArtifacts();
    expect(artifacts.rawCsv).toContain("encode_time,fast");
    expect(artifacts.methodology).toContain("before any external format comparison");
  });

  it("publishes an opt-in C++ raster comparison without replacing the Python reference", async () => {
    const comparison = await loadNativeRendererComparison();
    expect(comparison.method).toMatchObject({ runs: 10, dpi: 600, ecc: "balanced" });
    expect(comparison.method.scope).toContain("Python remains the reference");
    expect(comparison.cases.map(item => item.geometry)).toEqual(["micro-4", "small", "medium"]);
    expect(comparison.cases.every(item => item.reference_roundtrip && item.native_roundtrip)).toBe(true);
    expect(comparison.cases.find(item => item.geometry === "small")?.native_relative_change_percent).toBeLessThan(-50);
  });
});
