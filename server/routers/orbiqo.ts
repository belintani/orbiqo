import { TRPCError } from "@trpc/server";
import { z } from "zod";
import { publicProcedure, router } from "../_core/trpc";
import { callOrbiqoPython, OrbiqoBridgeError } from "../orbiqoPython";
import {
  loadBenchmarkArtifacts,
  loadBenchmarkSummary,
  loadNormalizedBenchmarkArtifacts,
  loadNormalizedBenchmarkSummary,
  loadOptimizationDelta,
  loadFormat5OcclusionValidation,
  loadEccProfileComparison,
  loadEccProfileComparisonArtifacts,
  loadNativeRendererComparison,
} from "../benchmarkResults";
import type {
  OrbiqoCapacities,
  OrbiqoDecodedSymbol,
  OrbiqoGeneratedSymbol,
  OrbiqoHealth,
  OrbiqoSizingRecommendation,
  OrbiqoSymbolComparison,
  OrbiqoVisualIdentityCatalog,
} from "../../shared/orbiqo";

const geometry = z.union([z.enum(["auto", "micro-1", "micro-2", "micro-4", "small", "medium", "large", "xl"]), z.number().int().min(0).max(6)]);
const ecc = z.enum(["fast", "balanced", "robust", "extreme"]);
const alphabet = z.enum(["color4", "mono2"]);
const identity = z.enum(["reference", "pulse", "nocturne", "terra", "signal"]);
const rasterBackend = z.enum(["reference", "native-experimental"]);

function bridgeFailure(error: unknown): never {
  if (error instanceof OrbiqoBridgeError) {
    const badInputCodes = new Set([
      "INVALID_INPUT",
      "INVALID_BASE64",
      "INVALID_IMAGE",
      "IMAGE_TOO_SMALL",
      "IMAGE_TOO_LARGE",
      "INPUT_TOO_LARGE",
      "CAPACITY_EXCEEDED",
      "DECODE_FAILED",
      "CENTER_IMAGE_INVALID_URL",
      "CENTER_IMAGE_URL_TOO_LONG",
      "CENTER_IMAGE_FORBIDDEN_HOST",
      "CENTER_IMAGE_UNREACHABLE",
      "CENTER_IMAGE_REDIRECT_LIMIT",
      "CENTER_IMAGE_FETCH_FAILED",
      "CENTER_IMAGE_TOO_LARGE",
      "CENTER_IMAGE_INVALID_FORMAT",
    ]);
    throw new TRPCError({
      code: badInputCodes.has(error.bridgeCode) ? "BAD_REQUEST" : "INTERNAL_SERVER_ERROR",
      message: error.message,
      cause: error,
    });
  }
  throw new TRPCError({ code: "INTERNAL_SERVER_ERROR", message: "Unexpected Orbiqo reference failure", cause: error });
}

export const orbiqoRouter = router({
  benchmarkSummary: publicProcedure.query(async () => loadBenchmarkSummary()),
  benchmarkArtifacts: publicProcedure.query(async () => loadBenchmarkArtifacts()),
  normalizedBenchmarkSummary: publicProcedure.query(async () => loadNormalizedBenchmarkSummary()),
  normalizedBenchmarkArtifacts: publicProcedure.query(async () => loadNormalizedBenchmarkArtifacts()),
  optimizationDelta: publicProcedure.query(async () => loadOptimizationDelta()),
  format5OcclusionValidation: publicProcedure.query(async () => loadFormat5OcclusionValidation()),
  eccProfileComparison: publicProcedure.query(async () => loadEccProfileComparison()),
  eccProfileComparisonArtifacts: publicProcedure.query(async () => loadEccProfileComparisonArtifacts()),
  nativeRendererComparison: publicProcedure.query(async () => loadNativeRendererComparison()),
  health: publicProcedure.query(async () => {
    try {
      return await callOrbiqoPython<OrbiqoHealth>({ op: "health" }, { timeoutMs: 5_000 });
    } catch (error) {
      bridgeFailure(error);
    }
  }),
  identities: publicProcedure.query(async () => {
    try {
      return await callOrbiqoPython<OrbiqoVisualIdentityCatalog>({ op: "identities" }, { timeoutMs: 5_000 });
    } catch (error) {
      bridgeFailure(error);
    }
  }),
  capacities: publicProcedure
    .input(z.object({ alphabet: alphabet.default("color4"), ecc: ecc.default("balanced") }))
    .query(async ({ input }) => {
      try {
        return await callOrbiqoPython<OrbiqoCapacities>({ op: "capacity", ...input }, { timeoutMs: 5_000 });
      } catch (error) {
        bridgeFailure(error);
      }
    }),
  recommendSizing: publicProcedure
    .input(
      z
        .object({
          payloadType: z.enum(["text", "url", "binary"]),
          text: z.string().max(65_536).optional(),
          payloadBase64: z.string().max(90_000).optional(),
          alphabet: alphabet.default("color4"),
          ecc: ecc.default("balanced"),
          compression: z.enum(["auto", "none", "deflate"]).default("auto"),
        })
        .superRefine((value, context) => {
          if (value.payloadType === "binary" && !value.payloadBase64) {
            context.addIssue({ code: z.ZodIssueCode.custom, path: ["payloadBase64"], message: "Binary payload is required" });
          }
          if (value.payloadType !== "binary" && value.text === undefined) {
            context.addIssue({ code: z.ZodIssueCode.custom, path: ["text"], message: "Text payload is required" });
          }
        }),
    )
    .query(async ({ input }) => {
      try {
        return await callOrbiqoPython<OrbiqoSizingRecommendation>(
          {
            op: "recommend_sizing",
            payload_type: input.payloadType,
            text: input.text,
            payload_base64: input.payloadBase64,
            alphabet: input.alphabet,
            ecc: input.ecc,
            compression: input.compression,
          },
          { timeoutMs: 5_000 },
        );
      } catch (error) {
        bridgeFailure(error);
      }
    }),
  compareSymbols: publicProcedure
    .input(
      z
        .object({
          payloadType: z.enum(["text", "url", "binary"]),
          text: z.string().max(2_048).optional(),
          payloadBase64: z.string().max(8_192).optional(),
          identityId: identity.default("pulse"),
          centerMark: z.string().max(8).optional(),
        })
        .superRefine((value, context) => {
          if (value.payloadType === "binary" && !value.payloadBase64) {
            context.addIssue({ code: z.ZodIssueCode.custom, path: ["payloadBase64"], message: "Binary payload is required" });
          }
          if (value.payloadType !== "binary" && value.text === undefined) {
            context.addIssue({ code: z.ZodIssueCode.custom, path: ["text"], message: "Text payload is required" });
          }
        }),
    )
    .mutation(async ({ input }) => {
      try {
        return await callOrbiqoPython<OrbiqoSymbolComparison>(
          {
            op: "compare_symbols",
            payload_type: input.payloadType,
            text: input.text,
            payload_base64: input.payloadBase64,
            identity_id: input.identityId,
            center_mark: input.centerMark,
          },
          { timeoutMs: 45_000 },
        );
      } catch (error) {
        bridgeFailure(error);
      }
    }),
  generate: publicProcedure
    .input(
      z
        .object({
          payloadType: z.enum(["text", "url", "binary"]),
          text: z.string().max(65_536).optional(),
          payloadBase64: z.string().max(90_000).optional(),
          sizingMode: z.enum(["auto", "manual"]).default("manual"),
          geometry: geometry.default("auto"),
          diameterMm: z.number().min(10).max(300).optional(),
          alphabet: alphabet.default("color4"),
          ecc: ecc.default("balanced"),
          compression: z.enum(["auto", "none", "deflate"]).default("auto"),
          dpi: z.number().int().min(72).max(600).default(600),
          centerMark: z.string().max(8).optional(),
          centerImageUrl: z.string().max(2_048).url().refine(value => value.startsWith("https://"), "Center image URL must use HTTPS").optional(),
          identityId: identity.default("pulse"),
          rasterBackend: rasterBackend.default("reference"),
        })
        .superRefine((value, context) => {
          if (value.payloadType === "binary" && !value.payloadBase64) {
            context.addIssue({ code: z.ZodIssueCode.custom, path: ["payloadBase64"], message: "Binary payload is required" });
          }
          if (value.payloadType !== "binary" && value.text === undefined) {
            context.addIssue({ code: z.ZodIssueCode.custom, path: ["text"], message: "Text payload is required" });
          }
          if (value.sizingMode === "manual" && value.geometry === "auto") {
            context.addIssue({ code: z.ZodIssueCode.custom, path: ["geometry"], message: "Manual sizing requires a fixed geometry" });
          }
          if (value.sizingMode === "manual" && value.diameterMm === undefined) {
            context.addIssue({ code: z.ZodIssueCode.custom, path: ["diameterMm"], message: "Manual sizing requires a diameter" });
          }
        }),
    )
    .mutation(async ({ input }) => {
      try {
        return await callOrbiqoPython<OrbiqoGeneratedSymbol>(
          {
            op: "generate",
            payload_type: input.payloadType,
            text: input.text,
            payload_base64: input.payloadBase64,
            sizing_mode: input.sizingMode,
            geometry: input.geometry,
            diameter_mm: input.diameterMm,
            alphabet: input.alphabet,
            ecc: input.ecc,
            compression: input.compression,
            dpi: input.dpi,
            center_mark: input.centerMark,
            center_image_url: input.centerImageUrl,
            identity_id: input.identityId,
            raster_backend: input.rasterBackend,
          },
          { timeoutMs: 25_000 },
        );
      } catch (error) {
        bridgeFailure(error);
      }
    }),
  decode: publicProcedure
    .input(
      z.object({
        imageBase64: z.string().min(16).max(11_200_000),
        canonical: z.boolean().default(false),
        geometryHint: z.number().int().min(0).max(6).optional(),
        outputSize: z.number().int().min(512).max(1536).default(1024),
        erasureThreshold: z.number().min(0).max(1).default(0.55),
      }),
    )
    .mutation(async ({ input }) => {
      try {
        return await callOrbiqoPython<OrbiqoDecodedSymbol>(
          {
            op: "decode",
            image_base64: input.imageBase64,
            canonical: input.canonical,
            geometry_hint: input.geometryHint,
            output_size: input.outputSize,
            erasure_threshold: input.erasureThreshold,
          },
          { timeoutMs: 30_000 },
        );
      } catch (error) {
        bridgeFailure(error);
      }
    }),
});
