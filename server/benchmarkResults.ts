import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { z } from "zod";
import type { OrbiqoBenchmarkSummary, OrbiqoEccProfileBenchmark, OrbiqoNativeFullComparison, OrbiqoNativeRendererComparison, OrbiqoNormalizedBenchmarkSummary, OrbiqoOptimizationDelta } from "../shared/orbiqo";

const moduleDirectory = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(moduleDirectory, "..");
const summaryPath = path.join(projectRoot, "benchmark", "results", "comparison_summary.json");
const rawPath = path.join(projectRoot, "benchmark", "results", "comparison_raw.csv");
const methodologyPath = path.join(projectRoot, "docs", "BENCHMARK_METHODOLOGY.md");
const normalizedSummaryPath = path.join(projectRoot, "benchmark", "results", "normalized_summary.json");
const normalizedRawPath = path.join(projectRoot, "benchmark", "results", "normalized_raw.csv");
const normalizedCapacityPath = path.join(projectRoot, "benchmark", "results", "normalized_capacity_trials.csv");
const normalizedMethodologyPath = path.join(projectRoot, "docs", "NORMALIZED_BENCHMARK_METHODOLOGY.md");
const optimizationDeltaPath = path.join(projectRoot, "benchmark", "results", "optimization_delta.json");
const format5OcclusionPath = path.join(projectRoot, "benchmark", "results", "format5_occlusion_validation.json");
const eccProfileComparisonPath = path.join(projectRoot, "benchmark", "results", "ecc_profile_comparison.json");
const eccProfileComparisonRawPath = path.join(projectRoot, "benchmark", "results", "ecc_profile_comparison_raw.csv");
const eccProfileMethodologyPath = path.join(projectRoot, "docs", "ECC_PROFILE_BENCHMARK.md");
const nativeRendererComparisonPath = path.join(projectRoot, "benchmark", "results", "native_renderer_comparison.json");
const nativeFullComparisonPath = path.join(projectRoot, "benchmark", "results", "native_full_comparison.json");

const summarySchema = z.object({
  schema_version: z.number().int().positive(),
  environment: z.object({
    generated_utc: z.string(),
    python: z.string(),
    platform: z.string(),
    machine: z.string(),
    radialcode: z.string(),
    zxing_cpp: z.string(),
    pillow: z.string(),
    numpy: z.string(),
    jab_commit: z.string(),
    payload_sha256: z.string().length(64),
    payload_base64: z.string(),
    timing_runs: z.number().int().positive(),
    degradation_trials: z.number().int().positive(),
    canvas_size: z.number().int().positive(),
    scope: z.string(),
  }),
  adapters: z.array(z.object({ format: z.string(), toolchain: z.string() })),
  jab_status: z.object({ included: z.boolean(), reason: z.string() }),
  capacity: z.array(
    z.object({
      format: z.string(), profile: z.string(), maximum_payload_bytes: z.number().int().nonnegative(), ec_level: z.string(), source: z.string(),
      raster_modules: z.array(z.number()).optional(), raster_modules_with_quiet_zone: z.array(z.number()).optional(),
    }),
  ),
  timing: z.array(
    z.object({
      format: z.string(), metric: z.enum(["generation_time", "decode_time"]), runs: z.number().int().positive(),
      median_ms: z.number().nonnegative(), mean_ms: z.number().nonnegative(), p95_ms: z.number().nonnegative(), success_rate: z.number().min(0).max(1),
    }),
  ),
  degradation: z.array(
    z.object({ format: z.string(), profile: z.string(), successes: z.number().int().nonnegative(), trials: z.number().int().positive(), success_rate: z.number().min(0).max(1) }),
  ),
  orbiqo_perspective: z.object({
    available: z.boolean(), successes: z.number().int().nonnegative(), trials: z.number().int().nonnegative(),
    known_failures: z.array(z.object({ pose: z.string(), profile: z.string(), error: z.string() })),
  }),
  limitations: z.array(z.string()),
});

const normalizedSummarySchema = z.object({
  schema_version: z.number().int().positive(),
  normalization: z.object({
    canvas_size: z.number().int().positive(), occupied_size: z.number().int().positive(), minimum_feature_pitch_px: z.number().positive(),
    timing_payload_bytes: z.number().int().positive(), timing_payload_sha256: z.string().length(64), success_criterion: z.string(),
    orbiqo_capacity_renderer: z.string().optional(), orbiqo_product_renderer: z.string().optional(),
  }),
  environment: z.object({
    generated_utc: z.string(), python: z.string(), platform: z.string(), machine: z.string(), radialcode: z.string(), zxing_cpp: z.string(),
    pillow: z.string(), numpy: z.string(), jab_commit: z.string(), payload_sha256: z.string().length(64), payload_base64: z.string(),
    timing_runs: z.number().int().positive(), degradation_trials: z.number().int().positive(), canvas_size: z.number().int().positive(),
    occupied_size: z.number().int().positive(), minimum_feature_pitch_px: z.number().positive(), scope: z.string(),
  }),
  adapters: z.array(z.object({
    format: z.string(), toolchain: z.string(), profile: z.string(), reported_ecc: z.string(), logical_width: z.number(), logical_height: z.number(), nominal_pitch_px: z.number().positive(),
  })),
  jab_status: z.object({ included: z.boolean(), reason: z.string() }),
  capacity: z.array(z.object({
    format: z.string(), maximum_payload_bytes: z.number().int().nonnegative(), nominal_pitch_px: z.number().positive(), logical_width: z.number().positive(),
    logical_height: z.number().positive(), profile: z.string(), reported_ecc: z.string(), bytes_per_100k_occupied_px: z.number().nonnegative(), constraint: z.string(),
  })),
  timing: z.array(z.object({
    format: z.string(), metric: z.enum(["generation_time", "decode_time"]), runs: z.number().int().positive(), median_ms: z.number().nonnegative(),
    mean_ms: z.number().nonnegative(), p95_ms: z.number().nonnegative(), success_rate: z.number().min(0).max(1),
  })),
  degradation: z.array(z.object({
    format: z.string(), profile: z.string(), successes: z.number().int().nonnegative(), trials: z.number().int().positive(), success_rate: z.number().min(0).max(1),
  })),
  limitations: z.array(z.string()),
});

const optimizationDeltaSchema = z.object({
  schema_version: z.number().int().positive(), generated_utc: z.string(), baseline_path: z.string(), current_summary_path: z.string(), methodology: z.string(),
  metrics: z.array(z.object({
    key: z.enum(["capacity", "generation", "decode", "robustness"]), label: z.string(), before: z.number(), after: z.number(), unit: z.enum(["B", "ms", "%"]),
    change: z.number(), change_percent: z.number(), direction: z.enum(["higher_is_better", "lower_is_better"]),
  })),
  orbiqo_degradation: z.object({ before: z.number(), after: z.number(), trials: z.number().int().positive() }),
});

const format5OcclusionSchema = z.object({
  profile: z.object({ occlusion_fraction: z.number(), seed: z.number() }).passthrough(),
  rows: z.array(z.object({
    ecc: z.enum(["balanced", "robust", "extreme"]),
    payload: z.string(),
    bytes: z.number().int().positive(),
    successes: z.number().int().nonnegative(),
    trials: z.number().int().positive(),
    outcomes: z.array(z.boolean()),
  })),
});

const eccProfileComparisonSchema = z.object({
  schema_version: z.number().int().positive(),
  environment: z.object({ generated_utc: z.string(), python: z.string(), platform: z.string(), radialcode: z.string() }),
  method: z.object({
    scope: z.string(), payload_bytes: z.number().int().positive(), payload_sha256: z.string().length(64), payload_base64: z.string(),
    geometry_selection: z.string(), encode_measurement: z.string(), decode_measurement: z.string(), timing_runs: z.number().int().positive(),
    occlusion: z.object({ fraction: z.number().positive(), payload_patterns: z.array(z.string()).min(1), trials_per_pattern: z.number().int().positive(), seeds: z.array(z.number().int()).min(1), success_criterion: z.string() }),
  }),
  profiles: z.array(z.object({
    ecc: z.enum(["fast", "balanced", "robust", "extreme"]), geometry: z.string(), geometry_version: z.number().int().positive(), data_rings: z.number().int().positive(),
    diameter_mm: z.number().positive(), nominal_pitch_px: z.number().positive(), code: z.string(),
    encode: z.object({ runs: z.number().int().positive(), median_ms: z.number().nonnegative(), mean_ms: z.number().nonnegative(), p95_ms: z.number().nonnegative() }),
    decode: z.object({ runs: z.number().int().positive(), median_ms: z.number().nonnegative(), mean_ms: z.number().nonnegative(), p95_ms: z.number().nonnegative() }),
    occlusion: z.object({
      minimum_successes: z.number().int().nonnegative(), trials_per_pattern: z.number().int().positive(),
      rows: z.array(z.object({ payload: z.string(), bytes: z.number().int().positive(), successes: z.number().int().nonnegative(), trials: z.number().int().positive(), outcomes: z.array(z.boolean()) })),
    }),
  })).min(4),
  limitations: z.array(z.string()).min(1),
});

const nativeRendererComparisonSchema = z.object({
  schema_version: z.number().int().positive(),
  generated_utc: z.string(),
  method: z.object({
    runs: z.number().int().positive(), dpi: z.number().int().positive(), payload_bytes: z.number().int().positive(),
    ecc: z.string(), identity: z.string(), scope: z.string(),
  }),
  cases: z.array(z.object({
    geometry: z.string(), diameter_mm: z.number().positive(), native_output_bytes: z.number().int().positive(), reference_output_bytes: z.number().int().positive(),
    reference_renderer_median_ms: z.number().nonnegative(), native_renderer_median_ms: z.number().nonnegative(), native_relative_change_percent: z.number(),
    reference_roundtrip: z.boolean(), native_roundtrip: z.boolean(),
  })).min(1),
});

const nativeFullComparisonSchema = z.object({
  schema_version: z.number().int().positive(),
  payload_bytes: z.number().int().positive(),
  rows: z.array(z.object({
    geometry: z.number().int().min(0).max(6),
    diameter_mm: z.number().positive(),
    runs: z.number().int().positive(),
    python_encode_render_median_ms: z.number().nonnegative(),
    cpp_encode_render_process_median_ms: z.number().nonnegative(),
    encode_render_delta_percent: z.number(),
    python_decode_median_ms: z.number().nonnegative(),
    cpp_decode_process_median_ms: z.number().nonnegative(),
    decode_delta_percent: z.number(),
    scope: z.string(),
  })).min(1),
});

export async function loadBenchmarkSummary(): Promise<OrbiqoBenchmarkSummary> {
  const parsed = JSON.parse(await readFile(summaryPath, "utf8"));
  return summarySchema.parse(parsed) as OrbiqoBenchmarkSummary;
}

export async function loadBenchmarkArtifacts() {
  const [rawCsv, methodology] = await Promise.all([readFile(rawPath, "utf8"), readFile(methodologyPath, "utf8")]);
  return { rawCsv, methodology };
}

export async function loadNormalizedBenchmarkSummary(): Promise<OrbiqoNormalizedBenchmarkSummary> {
  const parsed = JSON.parse(await readFile(normalizedSummaryPath, "utf8"));
  return normalizedSummarySchema.parse(parsed) as OrbiqoNormalizedBenchmarkSummary;
}

export async function loadNormalizedBenchmarkArtifacts() {
  const [rawCsv, capacityCsv, methodology] = await Promise.all([
    readFile(normalizedRawPath, "utf8"),
    readFile(normalizedCapacityPath, "utf8"),
    readFile(normalizedMethodologyPath, "utf8"),
  ]);
  return { rawCsv, capacityCsv, methodology };
}

export async function loadOptimizationDelta(): Promise<OrbiqoOptimizationDelta> {
  const parsed = JSON.parse(await readFile(optimizationDeltaPath, "utf8"));
  return optimizationDeltaSchema.parse(parsed) as OrbiqoOptimizationDelta;
}

export async function loadFormat5OcclusionValidation() {
  const parsed = JSON.parse(await readFile(format5OcclusionPath, "utf8"));
  return format5OcclusionSchema.parse(parsed);
}

export async function loadEccProfileComparison(): Promise<OrbiqoEccProfileBenchmark> {
  const parsed = JSON.parse(await readFile(eccProfileComparisonPath, "utf8"));
  return eccProfileComparisonSchema.parse(parsed) as OrbiqoEccProfileBenchmark;
}

export async function loadEccProfileComparisonArtifacts() {
  const [rawCsv, methodology] = await Promise.all([readFile(eccProfileComparisonRawPath, "utf8"), readFile(eccProfileMethodologyPath, "utf8")]);
  return { rawCsv, methodology };
}

export async function loadNativeRendererComparison(): Promise<OrbiqoNativeRendererComparison> {
  const parsed = JSON.parse(await readFile(nativeRendererComparisonPath, "utf8"));
  return nativeRendererComparisonSchema.parse(parsed) as OrbiqoNativeRendererComparison;
}

export async function loadNativeFullComparison(): Promise<OrbiqoNativeFullComparison> {
  const parsed = JSON.parse(await readFile(nativeFullComparisonPath, "utf8"));
  return nativeFullComparisonSchema.parse(parsed) as OrbiqoNativeFullComparison;
}
