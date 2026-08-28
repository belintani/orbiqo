export const brandCopy = {
  heroLead: "Give a round touchpoint",
  heroEmphasis: "a face and an action.",
  productDescription:
    "Orbiqo gives badges, profiles and round products a clear digital role. Keep a person, mark or status in the reserved non-functional center; put the destination or message in the data rings around it.",
  adoptionPitch: {
    eyebrow: "WHY ORBIQO / WHEN THE SURFACE MATTERS",
    description: "Choose Orbiqo when a round object needs to be both recognized and scanned. It gives that surface one visible identity and one digital action—not a square label added at the end.",
    reasons: [
      { label: "THE OBJECT LEADS", title: "Use the shape you already have", body: "Brooches, badges, lids, discs and profile frames begin round. Orbiqo begins with that same silhouette." },
      { label: "KEEP THE SUBJECT", title: "A photo, mark or status stays visible", body: "The center is intentionally not payload, so the rings can carry the action without crossing the person or identity at its core." },
      { label: "MAKE THE ACTION RECOGNIZABLE", title: "One touchpoint, not a generic label", body: "Validated visual templates let a family of touchpoints look related while each one can lead to its own URL or message." },
    ],
  },
  runtimePrefix: "Orbiqo reference",
  artifactAttribution: "Orbiqo protocol · reference implementation: RadialCode",
  footerProtocol: "Orbiqo Protocol Draft 0.6 · Reference implementation: RadialCode · Reads Draft 0.2–0.5 records",
  circularPositioning: {
    eyebrow: "CIRCULAR FIT / COMPOSITIONAL ADVANTAGE",
    headlineLead: "A code that",
    headlineEmphasis: "belongs to the object.",
    description: "The circular claim is simple: when the object is round, the code can use the object’s own silhouette and keep its identity at the center. That is a compositional advantage—not a promise about scan speed or universal capacity.",
    footprint: "The largest square inscribed in a circular face covers 63.7% of that face. A square code can sit on a round object; a circular symbol begins with the object’s own silhouette.",
    footprintLimit: "Geometry of the footprint only. It does not imply 63.7% more payload.",
    benchmarkLimit: "Circular geometry does not automatically beat QR, Aztec or JAB in capacity, scan speed or perspective tolerance. Those remain separate, measured questions in the benchmark workspace.",
  },
} as const;
