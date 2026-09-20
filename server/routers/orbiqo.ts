import { TRPCError } from "@trpc/server";
import { z } from "zod";
import { publicProcedure, router } from "../_core/trpc";
import {
  nativeCapacities,
  nativeDecode,
  nativeCompareSymbols,
  nativeGenerate,
  nativeHealth,
  nativeIdentities,
  nativeRecommendSizing,
  OrbiqoNativeError,
} from "../orbiqoNative";
import {
  loadBenchmarkArtifacts,
  loadBenchmarkSummary,
  loadNormalizedBenchmarkArtifacts,
  loadNormalizedBenchmarkSummary,
  loadOptimizationDelta,
  loadFormat5OcclusionValidation,
  loadEccProfileComparison,
  loadEccProfileComparisonArtifacts,
  loadNativeFullComparison,
  loadNativeRendererComparison,
} from "../benchmarkResults";

const geometry = z.union([z.enum(["auto", "micro-1", "micro-2", "micro-4", "small", "medium", "large", "xl"]), z.number().int().min(0).max(6)]);
const ecc = z.enum(["fast", "balanced", "robust", "extreme"]);
const alphabet = z.enum(["color4", "mono2"]);
const identity = z.enum(["reference", "pulse", "nocturne", "terra", "signal"]);
const rasterBackend = z.literal("native-cpp");
const protocolBackend = z.literal("native-cpp");
const decoderBackend = z.literal("native-cpp");

function bridgeFailure(error: unknown): never {
  if (error instanceof OrbiqoNativeError) {
    const badInputCodes = new Set([
      "INVALID_INPUT",
      "INPUT_TOO_LARGE",
      "CAPACITY_EXCEEDED",
      "CENTER_IMAGE_INVALID_URL",
      "CENTER_IMAGE_FORBIDDEN_HOST",
      "CENTER_IMAGE_REDIRECT_LIMIT",
      "CENTER_IMAGE_FETCH_FAILED",
      "CENTER_IMAGE_TOO_LARGE",
    ]);
    throw new TRPCError({
      code: badInputCodes.has(error.nativeCode) ? "BAD_REQUEST" : "INTERNAL_SERVER_ERROR",
      message: error.message,
      cause: error,
    });
  }
  throw new TRPCError({ code: "INTERNAL_SERVER_ERROR", message: "Unexpected Orbiqo native failure", cause: error });
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
  nativeFullComparison: publicProcedure.query(async () => loadNativeFullComparison()),
  nativeRendererComparison: publicProcedure.query(async () => loadNativeRendererComparison()),
  health: publicProcedure.query(() => nativeHealth()),
  identities: publicProcedure.query(() => nativeIdentities()),
  capacities: publicProcedure
    .input(z.object({ alphabet: alphabet.default("color4"), ecc: ecc.default("balanced") }))
    .query(async ({ input }) => nativeCapacities(input)),
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
        return await nativeRecommendSizing(input);
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
        return await nativeCompareSymbols(input);
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
          rasterBackend: rasterBackend.default("native-cpp"),
          protocolBackend: protocolBackend.optional(),
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
        return await nativeGenerate(input);
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
          decoderBackend: decoderBackend.optional(),
      }),
    )
    .mutation(async ({ input }) => {
      try {
        return await nativeDecode(input);
      } catch (error) {
        bridgeFailure(error);
      }
    }),
});
