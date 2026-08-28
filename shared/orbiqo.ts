export type OrbiqoPayloadType = "text" | "url" | "binary";
export type OrbiqoGeometry = "auto" | "micro-1" | "micro-2" | "micro-4" | "small" | "medium" | "large" | "xl" | 0 | 1 | 2 | 3 | 4 | 5 | 6;
export type OrbiqoEcc = "fast" | "balanced" | "robust" | "extreme";
export type OrbiqoSizingMode = "auto" | "manual";
export type OrbiqoIdentityId = "reference" | "pulse" | "nocturne" | "terra" | "signal";
export type OrbiqoRasterBackend = "reference" | "native-experimental";

export type OrbiqoNativeRendererComparison = {
  schema_version: number;
  generated_utc: string;
  method: {
    runs: number;
    dpi: number;
    payload_bytes: number;
    ecc: string;
    identity: string;
    scope: string;
  };
  cases: Array<{
    geometry: string;
    diameter_mm: number;
    native_output_bytes: number;
    reference_output_bytes: number;
    reference_renderer_median_ms: number;
    native_renderer_median_ms: number;
    native_relative_change_percent: number;
    reference_roundtrip: boolean;
    native_roundtrip: boolean;
  }>;
};

export type OrbiqoVisualIdentity = {
  id: OrbiqoIdentityId;
  name: string;
  description: string;
  tone: string;
  palette_id: number;
  palette_name: string;
  colors: string[];
  visual_style: "reference" | "pulse";
  angular_fill: number;
  radial_fill: number;
  recommended_for: string;
  validation_status: "digital-validated";
  format_version: number;
};

export type OrbiqoVisualIdentityCatalog = {
  default_identity_id: OrbiqoIdentityId;
  custom_colors_supported: false;
  identities: OrbiqoVisualIdentity[];
};

export type OrbiqoHealth = {
  product: string;
  reference_package: string;
  reference_version: string;
  reference_root: string;
  supported_format_versions: number[];
  default_format_version: number;
  default_layout: "constant-columns";
  visual_identity_count: number;
};

export type OrbiqoCapacityRow = {
  version: number;
  name: string;
  rings: number;
  recommended_diameter_mm: number;
  format_version: number;
  layout_name: "constant-columns";
  columns: number;
  data_inner: number;
  payload_cells: number;
  channel_bits: number;
  channel_bytes: number;
  maximum_uncompressed_payload_bytes: number;
};

export type OrbiqoCapacities = {
  alphabet: string;
  ecc: string;
  rows: OrbiqoCapacityRow[];
};

export type OrbiqoSizingRecommendation = {
  format_version: number;
  geometry_version: number;
  geometry_name: string;
  recommended_diameter_mm: number;
  payload_bytes: number;
  frame_bytes: number;
  compression: string;
  maximum_uncompressed_payload_bytes: number;
  remaining_nominal_payload_bytes: number;
  selection_reason: string;
};

export type OrbiqoComparisonItem = {
  id: "orbiqo" | "qr" | "aztec" | "jab";
  name: string;
  png_base64: string;
  toolchain: string;
  profile: string;
  reported_ecc: string;
  detail: string;
  native_width: number;
  native_height: number;
  geometry: string | null;
  diameter_mm: number | null;
};

export type OrbiqoSymbolComparison = {
  payload_type: string;
  payload_bytes: number;
  payload_base64: string;
  canvas_px: number;
  occupied_px: number;
  normalization: string;
  ecc_comparability: string;
  items: OrbiqoComparisonItem[];
};

export type OrbiqoGeneratedSymbol = {
  svg: string;
  png_base64: string;
  center_image_preview_base64?: string | null;
  metadata: {
    format_version: number;
    geometry_version: number;
    geometry_name: string;
    layout_name: "constant-columns" | "legacy-radial";
    columns: number;
    data_inner: number;
    diameter_mm: number;
    recommended_diameter_mm: number;
    sizing_mode: OrbiqoSizingMode;
    requested_geometry: OrbiqoGeometry;
    selection_reason: string;
    physical_pitch_mm: number;
    print_pitch_warning: boolean;
    alphabet: string;
    ecc_level: string;
    payload_type: string;
    payload_bytes: number;
    frame_bytes: number;
    mask_id: number;
    palette_id: number;
    palette_name: string;
    palette_colors: string[];
    maximum_uncompressed_payload_bytes: number;
    generation_time_ms: number;
    raster_backend_requested: OrbiqoRasterBackend;
    raster_renderer: "python-reference" | "cpp-native-experimental" | "python-reference-fallback";
    native_fallback_reason: string | null;
    attribution: string;
    visual_style: "reference" | "pulse";
    identity_id: OrbiqoIdentityId;
    identity_name: string;
    center_image_applied: boolean;
    center_image_host: string | null;
  };
};

export type OrbiqoDecodedSymbol = {
  payload_base64: string;
  text?: string;
  payload_type: string;
  payload_bytes: number;
  format_version: number;
  geometry_version: number;
  alphabet: string;
  palette_id: number;
  palette_name: string;
  ecc_level: string;
  mask_id: number;
  image: { width: number; height: number; format: string };
  diagnostics: {
    header_corrected_bits: number[];
    corrected_rs_symbols: number;
    erasure_cells: number;
    erasure_bytes: number;
    average_confidence: number;
    minimum_confidence: number;
    processing_time_ms: number;
    color_reference_means: number[][];
  };
  rectification?: {
    axis_ratio: number;
    anchor_widths: number[];
    reprojection_error_px: number;
    homography: number[][];
  };
};

export type OrbiqoBenchmarkSummary = {
  schema_version: number;
  environment: {
    generated_utc: string;
    python: string;
    platform: string;
    machine: string;
    radialcode: string;
    zxing_cpp: string;
    pillow: string;
    numpy: string;
    jab_commit: string;
    payload_sha256: string;
    payload_base64: string;
    timing_runs: number;
    degradation_trials: number;
    canvas_size: number;
    scope: string;
  };
  adapters: Array<{ format: string; toolchain: string }>;
  jab_status: { included: boolean; reason: string };
  capacity: Array<{
    format: string;
    profile: string;
    maximum_payload_bytes: number;
    ec_level: string;
    source: string;
    raster_modules?: number[];
    raster_modules_with_quiet_zone?: number[];
  }>;
  timing: Array<{
    format: string;
    metric: "generation_time" | "decode_time";
    runs: number;
    median_ms: number;
    mean_ms: number;
    p95_ms: number;
    success_rate: number;
  }>;
  degradation: Array<{
    format: string;
    profile: string;
    successes: number;
    trials: number;
    success_rate: number;
  }>;
  orbiqo_perspective: {
    available: boolean;
    successes: number;
    trials: number;
    known_failures: Array<{ pose: string; profile: string; error: string }>;
  };
  limitations: string[];
};

export type OrbiqoNormalizedBenchmarkSummary = {
  schema_version: number;
  normalization: {
    canvas_size: number;
    occupied_size: number;
    minimum_feature_pitch_px: number;
    timing_payload_bytes: number;
    timing_payload_sha256: string;
    success_criterion: string;
    orbiqo_capacity_renderer?: string;
    orbiqo_product_renderer?: string;
  };
  environment: {
    generated_utc: string;
    python: string;
    platform: string;
    machine: string;
    radialcode: string;
    zxing_cpp: string;
    pillow: string;
    numpy: string;
    jab_commit: string;
    payload_sha256: string;
    payload_base64: string;
    timing_runs: number;
    degradation_trials: number;
    canvas_size: number;
    occupied_size: number;
    minimum_feature_pitch_px: number;
    scope: string;
  };
  adapters: Array<{
    format: string;
    toolchain: string;
    profile: string;
    reported_ecc: string;
    logical_width: number;
    logical_height: number;
    nominal_pitch_px: number;
  }>;
  jab_status: { included: boolean; reason: string };
  capacity: Array<{
    format: string;
    maximum_payload_bytes: number;
    nominal_pitch_px: number;
    logical_width: number;
    logical_height: number;
    profile: string;
    reported_ecc: string;
    bytes_per_100k_occupied_px: number;
    constraint: string;
  }>;
  timing: Array<{
    format: string;
    metric: "generation_time" | "decode_time";
    runs: number;
    median_ms: number;
    mean_ms: number;
    p95_ms: number;
    success_rate: number;
  }>;
  degradation: Array<{
    format: string;
    profile: string;
    successes: number;
    trials: number;
    success_rate: number;
  }>;
  limitations: string[];
};

export type OrbiqoOptimizationDelta = {
  schema_version: number;
  generated_utc: string;
  baseline_path: string;
  current_summary_path: string;
  methodology: string;
  metrics: Array<{
    key: "capacity" | "generation" | "decode" | "robustness";
    label: string;
    before: number;
    after: number;
    unit: "B" | "ms" | "%";
    change: number;
    change_percent: number;
    direction: "higher_is_better" | "lower_is_better";
  }>;
  orbiqo_degradation: { before: number; after: number; trials: number };
};

export type OrbiqoEccProfileBenchmark = {
  schema_version: number;
  environment: { generated_utc: string; python: string; platform: string; radialcode: string };
  method: {
    scope: string;
    payload_bytes: number;
    payload_sha256: string;
    payload_base64: string;
    geometry_selection: string;
    encode_measurement: string;
    decode_measurement: string;
    timing_runs: number;
    occlusion: { fraction: number; payload_patterns: string[]; trials_per_pattern: number; seeds: number[]; success_criterion: string };
  };
  profiles: Array<{
    ecc: OrbiqoEcc;
    geometry: string;
    geometry_version: number;
    data_rings: number;
    diameter_mm: number;
    nominal_pitch_px: number;
    code: string;
    encode: { runs: number; median_ms: number; mean_ms: number; p95_ms: number };
    decode: { runs: number; median_ms: number; mean_ms: number; p95_ms: number };
    occlusion: {
      minimum_successes: number;
      trials_per_pattern: number;
      rows: Array<{ payload: string; bytes: number; successes: number; trials: number; outcomes: boolean[] }>;
    };
  }>;
  limitations: string[];
};
