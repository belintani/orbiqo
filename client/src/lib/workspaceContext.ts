export const workspaceContext = {
  read: {
    eyebrow: "READ / LOCAL INSPECTION",
    lead: "Bring a symbol",
    emphasis: "into focus.",
    body: "Choose an image, camera, screen capture or the symbol you just generated. Decoding stays explicit and local to this workspace.",
  },
  compare: {
    eyebrow: "COMPARE / SAME PAYLOAD",
    lead: "Inspect the payload.",
    emphasis: "See the tradeoffs.",
    body: "Generate the same message in four real toolchains and examine each artifact beside its declared profile.",
  },
  benchmarks: {
    eyebrow: "BENCHMARKS / MEASURED CONTEXT",
    lead: "Choose protection first.",
    emphasis: "Compare formats second.",
    body: "Start with Orbiqo’s measured protection profiles, then use the external comparison as context—not as a universal winner ranking.",
  },
  renderer: {
    eyebrow: "RENDERERS / IMPLEMENTATION STUDY",
    lead: "Keep the reference.",
    emphasis: "Measure the acceleration.",
    body: "Inspect the experimental C++ raster core beside Python without confusing a renderer optimization with a protocol or decoding claim.",
  },
} as const;
