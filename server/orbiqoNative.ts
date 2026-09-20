import { promises as dns } from "node:dns";
import { spawn } from "node:child_process";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { OrbiqoDecodedSymbol, OrbiqoGeneratedSymbol, OrbiqoGeometry, OrbiqoSymbolComparison } from "../shared/orbiqo";

const moduleDirectory = path.dirname(fileURLToPath(import.meta.url));
const nativePath = process.env.ORBIQO_NATIVE_PATH ?? path.join(moduleDirectory, "python", "native", "orbiqo_native");
const externalPath = process.env.ORBIQO_EXTERNAL_COMPARE_PATH ?? path.resolve(moduleDirectory, "..", "benchmark", "native", "orbiqo_external_compare");
const jabRoot = process.env.ORBIQO_JAB_ROOT ?? path.resolve(moduleDirectory, "..", "benchmark", "jabcode-runtime");
const maxInputBytes = 12 * 1024 * 1024;
const maxOutputBytes = 30 * 1024 * 1024;
const nativeTimeoutMs = 30_000;

export class OrbiqoNativeError extends Error {
  constructor(public readonly nativeCode: string, message: string) {
    super(message);
    this.name = "OrbiqoNativeError";
  }
}

type NativeFields = Record<string, string>;

function parseFields(raw: string): NativeFields {
  const fields: NativeFields = {};
  for (const line of raw.trim().split(/\r?\n/)) {
    if (!line || line === "ORBIQO_NATIVE_RESULT_V1" || line === "END") continue;
    const separator = line.indexOf(" ");
    if (separator <= 0) continue;
    fields[line.slice(0, separator)] = line.slice(separator + 1);
  }
  if (!fields.svg_base64 && !fields.payload_hex && !fields.normalized_png_base64 && !fields.png_base64) {
    throw new OrbiqoNativeError("INVALID_RESPONSE", "Native executable returned no recognizable result");
  }
  return fields;
}

function callNative(lines: string[], timeoutMs = nativeTimeoutMs): Promise<NativeFields> {
  const input = `${lines.join("\n")}\n`;
  if (Buffer.byteLength(input) > maxInputBytes * 2) {
    return Promise.reject(new OrbiqoNativeError("INPUT_TOO_LARGE", "Native operation exceeds the local input limit"));
  }
  return new Promise((resolve, reject) => {
    const child = spawn(nativePath, [], {
      cwd: path.resolve(moduleDirectory, ".."),
      env: process.env,
      stdio: ["pipe", "pipe", "pipe"],
    });
    const stdout: Buffer[] = [];
    const stderr: Buffer[] = [];
    let outputBytes = 0;
    let settled = false;
    const finish = (error?: Error, value?: NativeFields) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (error) reject(error);
      else resolve(value as NativeFields);
    };
    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      finish(new OrbiqoNativeError("TIMEOUT", "Native operation exceeded its time limit"));
    }, timeoutMs);
    child.stdout.on("data", (chunk: Buffer) => {
      outputBytes += chunk.length;
      if (outputBytes > maxOutputBytes) {
        child.kill("SIGKILL");
        finish(new OrbiqoNativeError("OUTPUT_TOO_LARGE", "Native operation exceeded its output limit"));
        return;
      }
      stdout.push(chunk);
    });
    child.stderr.on("data", (chunk: Buffer) => stderr.push(chunk));
    child.on("error", error => finish(new OrbiqoNativeError("PROCESS_FAILURE", error.message)));
    child.on("close", code => {
      if (settled) return;
      if (code !== 0) {
        const detail = Buffer.concat(stderr).toString("utf8").trim();
        const nativeCode = detail.includes("payload does not fit") ? "CAPACITY_EXCEEDED" : "NATIVE_OPERATION_FAILED";
        finish(new OrbiqoNativeError(nativeCode, detail || `Native executable exited with code ${code ?? "unknown"}`));
        return;
      }
      try {
        finish(undefined, parseFields(Buffer.concat(stdout).toString("utf8")));
      } catch (error) {
        finish(error instanceof Error ? error : new OrbiqoNativeError("INVALID_RESPONSE", "Invalid native response"));
      }
    });
    child.stdin.end(input);
  });
}

function number(fields: NativeFields, key: string, fallback = 0): number {
  const value = Number(fields[key]);
  return Number.isFinite(value) ? value : fallback;
}

function callExternal(format: "qr" | "aztec" | "jab", payload: Buffer, timeoutMs = nativeTimeoutMs): Promise<NativeFields> {
  return new Promise((resolve, reject) => {
    const args = [format, payload.toString("hex"), ...(format === "jab" ? [jabRoot] : [])];
    const child = spawn(externalPath, args, {
      cwd: path.resolve(moduleDirectory, ".."),
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"],
    });
    const stdout: Buffer[] = [];
    const stderr: Buffer[] = [];
    let settled = false;
    const finish = (error?: Error, value?: NativeFields) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (error) reject(error);
      else resolve(value as NativeFields);
    };
    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      finish(new OrbiqoNativeError("TIMEOUT", "External native comparison exceeded its time limit"));
    }, timeoutMs);
    child.stdout.on("data", (chunk: Buffer) => stdout.push(chunk));
    child.stderr.on("data", (chunk: Buffer) => stderr.push(chunk));
    child.on("error", error => finish(new OrbiqoNativeError("PROCESS_FAILURE", error.message)));
    child.on("close", code => {
      if (settled) return;
      if (code !== 0) {
        const detail = Buffer.concat(stderr).toString("utf8").trim();
        finish(new OrbiqoNativeError("EXTERNAL_COMPARISON_FAILED", detail || `External native comparison exited with code ${code ?? "unknown"}`));
        return;
      }
      try {
        finish(undefined, parseFields(Buffer.concat(stdout).toString("utf8")));
      } catch (error) {
        finish(error instanceof Error ? error : new OrbiqoNativeError("INVALID_RESPONSE", "Invalid external native response"));
      }
    });
  });
}

function geometryName(version: number): string {
  return ({ 0: "micro-2", 1: "small", 2: "medium", 3: "large", 4: "xl", 5: "micro-4", 6: "micro-1" } as Record<number, string>)[version] ?? "unknown";
}

const paletteNames = ["C4-CORE-1", "C4-NOCTURNE-1", "C4-TERRA-1", "C4-SIGNAL-1"] as const;
const paletteColors = [
  ["#111111", "#00a6d6", "#d81b60", "#f0c808"],
  ["#111111", "#4cc9f0", "#f72585", "#a7c957"],
  ["#111111", "#2a9d8f", "#e76f51", "#ffd60a"],
  ["#111111", "#219ebc", "#ff4d6d", "#80ed99"],
] as const;
const identities = {
  reference: { palette: 0, angular: 0.88, radial: 0.72 },
  pulse: { palette: 0, angular: 0.82, radial: 0.8 },
  nocturne: { palette: 1, angular: 0.82, radial: 0.8 },
  terra: { palette: 2, angular: 0.82, radial: 0.8 },
  signal: { palette: 3, angular: 0.82, radial: 0.8 },
} as const;

type GenerateInput = {
  payloadType: "text" | "url" | "binary";
  text?: string;
  payloadBase64?: string;
  sizingMode?: "auto" | "manual";
  geometry?: OrbiqoGeometry | number;
  diameterMm?: number;
  alphabet?: "color4" | "mono2";
  ecc?: "fast" | "balanced" | "robust" | "extreme";
  compression?: "auto" | "none" | "deflate";
  dpi?: number;
  centerMark?: string;
  centerImageUrl?: string;
  identityId?: keyof typeof identities;
};

function payloadBytes(input: GenerateInput): Buffer {
  if (input.payloadType === "binary") {
    if (!input.payloadBase64) throw new OrbiqoNativeError("INVALID_INPUT", "Binary payload is required");
    return Buffer.from(input.payloadBase64, "base64");
  }
  if (input.text === undefined) throw new OrbiqoNativeError("INVALID_INPUT", "Text payload is required");
  return Buffer.from(input.text, "utf8");
}

function isPrivateAddress(address: string): boolean {
  if (net.isIPv4(address)) {
    const parts = address.split(".").map(Number);
    return parts[0] === 10 || parts[0] === 127 || (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31) || (parts[0] === 192 && parts[1] === 168) || parts[0] === 0;
  }
  if (net.isIPv6(address)) return address === "::1" || address.startsWith("fc") || address.startsWith("fd") || address.startsWith("fe8") || address.startsWith("fe9") || address.startsWith("fea") || address.startsWith("feb");
  return true;
}

async function assertPublicHttps(url: URL): Promise<void> {
  if (url.protocol !== "https:") throw new OrbiqoNativeError("CENTER_IMAGE_INVALID_URL", "Center image URL must use HTTPS");
  const hostname = url.hostname.toLowerCase();
  if (["localhost", "localhost.localdomain"].includes(hostname) || hostname.endsWith(".local")) throw new OrbiqoNativeError("CENTER_IMAGE_FORBIDDEN_HOST", "Center image host is not allowed");
  const addresses = await dns.lookup(hostname, { all: true });
  if (addresses.some(item => isPrivateAddress(item.address))) throw new OrbiqoNativeError("CENTER_IMAGE_FORBIDDEN_HOST", "Center image host resolves to a private address");
}

async function fetchCenterImage(urlValue: string | undefined): Promise<{ bytes: Buffer | null; host: string | null }> {
  if (!urlValue) return { bytes: null, host: null };
  let url = new URL(urlValue);
  for (let redirect = 0; redirect <= 3; redirect += 1) {
    await assertPublicHttps(url);
    const response = await fetch(url, { redirect: "manual", signal: AbortSignal.timeout(10_000) });
    if (response.status >= 300 && response.status < 400) {
      const location = response.headers.get("location");
      if (!location || redirect === 3) throw new OrbiqoNativeError("CENTER_IMAGE_REDIRECT_LIMIT", "Center image redirect limit reached");
      url = new URL(location, url);
      continue;
    }
    if (!response.ok) throw new OrbiqoNativeError("CENTER_IMAGE_FETCH_FAILED", `Center image request failed with HTTP ${response.status}`);
    const length = Number(response.headers.get("content-length") ?? 0);
    if (length > 2 * 1024 * 1024) throw new OrbiqoNativeError("CENTER_IMAGE_TOO_LARGE", "Center image exceeds the size limit");
    const bytes = Buffer.from(await response.arrayBuffer());
    if (bytes.length > 2 * 1024 * 1024) throw new OrbiqoNativeError("CENTER_IMAGE_TOO_LARGE", "Center image exceeds the size limit");
    return { bytes, host: url.hostname };
  }
  throw new OrbiqoNativeError("CENTER_IMAGE_REDIRECT_LIMIT", "Center image redirect limit reached");
}

function geometryValue(value: string | number | undefined): string {
  if (typeof value === "number") return String(value);
  return ({ "micro-1": "6", "micro-2": "0", "micro-4": "5", small: "1", medium: "2", large: "3", xl: "4" } as Record<string, string>)[value ?? "auto"] ?? "auto";
}

export async function nativeGenerate(input: GenerateInput): Promise<OrbiqoGeneratedSymbol> {
  const payload = payloadBytes(input);
  const identity = identities[input.identityId ?? "pulse"] ?? identities.pulse;
  const center = await fetchCenterImage(input.centerImageUrl);
  const geometry = geometryValue(input.geometry);
  const diameter = input.diameterMm ?? 0;
  const text = center.bytes ? "" : (input.centerMark ?? "");
  const started = performance.now();
  const fields = await callNative([
    "OP generate",
    `PAYLOAD_HEX ${payload.toString("hex")}`,
    `GEOMETRY ${geometry}`,
    "FORMAT 5",
    `ALPHABET ${input.alphabet ?? "color4"}`,
    `PAYLOAD_TYPE ${input.payloadType}`,
    `ECC ${input.ecc ?? "balanced"}`,
    `COMPRESSION ${input.compression ?? "auto"}`,
    `PALETTE ${identity.palette}`,
    `DPI ${input.dpi ?? 600}`,
    `DIAMETER_MM ${diameter}`,
    `RADIAL_FILL ${identity.radial}`,
    `ANGULAR_FILL ${identity.angular}`,
    "BACKGROUND #ffffff",
    ...(text ? [`CENTER_TEXT_B64 ${Buffer.from(text, "utf8").toString("base64")}`] : []),
    ...(center.bytes ? [`CENTER_IMAGE_HEX ${center.bytes.toString("hex")}`] : []),
    "END",
  ]);
  const geometryVersion = number(fields, "geometry_version");
  const effectiveDiameter = number(fields, "diameter_mm");
  const paletteId = number(fields, "palette_id", identity.palette);
  const result: OrbiqoGeneratedSymbol = {
    svg: Buffer.from(fields.svg_base64, "base64").toString("utf8"),
    png_base64: fields.png_base64,
    center_image_preview_base64: null,
    metadata: {
      format_version: number(fields, "format_version", 5),
      geometry_version: geometryVersion,
      geometry_name: fields.geometry_name ?? geometryName(geometryVersion),
      layout_name: fields.layout_name === "legacy-radial" ? "legacy-radial" : "constant-columns",
      columns: number(fields, "columns"),
      data_inner: number(fields, "data_inner"),
      diameter_mm: effectiveDiameter,
      recommended_diameter_mm: number(fields, "recommended_diameter_mm", effectiveDiameter),
      sizing_mode: input.sizingMode ?? "manual",
      requested_geometry: (input.geometry ?? "auto") as OrbiqoGeometry,
      selection_reason: geometry === "auto" ? "smallest geometry that fits the encoded frame at the selected ECC" : "explicit geometry selected",
      physical_pitch_mm: 0,
      print_pitch_warning: false,
      alphabet: (input.alphabet ?? "color4").toUpperCase(),
      ecc_level: (input.ecc ?? "balanced").toUpperCase(),
      payload_type: input.payloadType,
      payload_bytes: number(fields, "payload_bytes", payload.length),
      frame_bytes: number(fields, "frame_bytes"),
      payload_cells: number(fields, "payload_cells"),
      channel_bits: number(fields, "channel_bits"),
      channel_bytes: number(fields, "channel_bytes"),
      mask_id: number(fields, "mask_id"),
      palette_id: paletteId,
      palette_name: paletteNames[paletteId] ?? paletteNames[0],
      palette_colors: [...(paletteColors[paletteId] ?? paletteColors[0])],
      maximum_uncompressed_payload_bytes: number(fields, "maximum_uncompressed_payload_bytes"),
      generation_time_ms: performance.now() - started,
      raster_backend_requested: "native-cpp",
      raster_renderer: "cpp-native-full",
      native_fallback_reason: null,
      attribution: "Built with RadialCode — an open radial 2D code project.",
      visual_style: input.identityId === "reference" ? "reference" : "pulse",
      identity_id: input.identityId ?? "pulse",
      identity_name: input.identityId === "reference" ? "Reference" : (input.identityId ?? "pulse").replace(/^./, value => value.toUpperCase()),
      center_image_applied: Boolean(center.bytes),
      center_image_host: center.host,
    },
  };
  return result;
}

function imageFormat(bytes: Buffer): string {
  if (bytes.subarray(0, 8).toString("hex") === "89504e470d0a1a0a") return "PNG";
  if (bytes.subarray(0, 2).toString("hex") === "ffd8") return "JPEG";
  if (bytes.subarray(0, 4).toString("ascii") === "RIFF" && bytes.subarray(8, 12).toString("ascii") === "WEBP") return "WEBP";
  return "IMAGE";
}

function pngDimensions(pngBase64: string): { width: number; height: number } {
  const bytes = Buffer.from(pngBase64, "base64");
  if (bytes.length < 24 || bytes.subarray(0, 8).toString("hex") !== "89504e470d0a1a0a") return { width: 0, height: 0 };
  return { width: bytes.readUInt32BE(16), height: bytes.readUInt32BE(20) };
}

export async function nativeDecode(input: { imageBase64: string; canonical?: boolean; erasureThreshold?: number }): Promise<OrbiqoDecodedSymbol> {
  const image = Buffer.from(input.imageBase64, "base64");
  const fields = await callNative([
    "OP decode",
    `IMAGE_HEX ${image.toString("hex")}`,
    `CANONICAL ${input.canonical ? 1 : 0}`,
    `ERASURE_THRESHOLD ${input.erasureThreshold ?? 0.55}`,
    "END",
  ]);
  const payload = Buffer.from(fields.payload_hex ?? "", "hex");
  const payloadType = ({ 0: "BINARY", 1: "UTF8", 2: "URL" } as Record<number, string>)[number(fields, "payload_type")] ?? "BINARY";
  const result: OrbiqoDecodedSymbol = {
    payload_base64: payload.toString("base64"),
    decoder_backend: "native-cpp",
    decoder_fallback_reason: null,
    payload_type: payloadType,
    payload_bytes: payload.length,
    format_version: number(fields, "format_version"),
    geometry_version: number(fields, "geometry_version"),
    alphabet: number(fields, "alphabet") === 1 ? "COLOR4" : "MONO2",
    palette_id: number(fields, "palette_id"),
    palette_name: paletteNames[number(fields, "palette_id")] ?? paletteNames[0],
    ecc_level: ["FAST", "BALANCED", "ROBUST", "EXTREME"][number(fields, "ecc_level")] ?? "BALANCED",
    mask_id: number(fields, "mask_id"),
    image: { width: number(fields, "image_width"), height: number(fields, "image_height"), format: imageFormat(image) },
    diagnostics: {
      header_corrected_bits: [number(fields, "header_corrected_bits")],
      corrected_rs_symbols: number(fields, "corrected_rs_symbols"),
      erasure_cells: number(fields, "erasure_cells"),
      erasure_bytes: 0,
      average_confidence: Number(fields.average_confidence ?? 1),
      minimum_confidence: Number(fields.minimum_confidence ?? 1),
      processing_time_ms: 0,
      color_reference_means: [],
    },
    ...(input.canonical ? {} : { rectification: { axis_ratio: Number(fields.axis_ratio ?? 1), anchor_widths: [], reprojection_error_px: 0, homography: [[1, 0, 0], [0, 1, 0], [0, 0, 1]] } }),
  };
  if (payloadType === "UTF8" || payloadType === "URL") result.text = payload.toString("utf8");
  return result;
}

export async function nativeNormalizePng(pngBase64: string): Promise<string> {
  const fields = await callNative([
    "OP normalize",
    `IMAGE_HEX ${Buffer.from(pngBase64, "base64").toString("hex")}`,
    "END",
  ]);
  if (!fields.normalized_png_base64) throw new OrbiqoNativeError("INVALID_RESPONSE", "Native normalizer returned no PNG");
  return fields.normalized_png_base64;
}

export async function nativeCompareSymbols(input: {
  payloadType: "text" | "url" | "binary";
  text?: string;
  payloadBase64?: string;
  identityId?: keyof typeof identities;
  centerMark?: string;
}): Promise<OrbiqoSymbolComparison> {
  const payload = payloadBytes(input);
  if (payload.length === 0) throw new OrbiqoNativeError("INVALID_INPUT", "Comparison payload must not be empty");
  const generated = await nativeGenerate({
    ...input,
    sizingMode: "auto",
    geometry: "auto",
    diameterMm: 30,
    alphabet: "color4",
    ecc: "balanced",
    compression: "none",
    dpi: 600,
  });
  const normalizedOrbiqo = await nativeNormalizePng(generated.png_base64);
  const nativeDimensions = pngDimensions(generated.png_base64);
  const items: OrbiqoSymbolComparison["items"] = [{
    id: "orbiqo",
    name: "Orbiqo",
    png_base64: normalizedOrbiqo,
    toolchain: "Orbiqo native C++17 codec",
    profile: `${generated.metadata.geometry_name} / COLOR4 / balanced`,
    reported_ecc: "RS(255,191), code rate 74.9%",
    detail: `Protocol Draft 0.6 format ${generated.metadata.format_version}; ${generated.metadata.columns} constant columns`,
    native_width: nativeDimensions.width,
    native_height: nativeDimensions.height,
    geometry: generated.metadata.geometry_name,
    diameter_mm: generated.metadata.diameter_mm,
  }];
  const displayNames = { qr: "QR Code", aztec: "Aztec", jab: "JAB Code" } as const;
  for (const format of ["qr", "aztec", "jab"] as const) {
    const fields = await callExternal(format, payload, format === "jab" ? 45_000 : nativeTimeoutMs);
    items.push({
      id: format,
      name: displayNames[format],
      png_base64: fields.png_base64 ?? "",
      toolchain: fields.toolchain ?? "native external adapter",
      profile: format === "jab" ? "single symbol / official CLI default" : "ZXing-C++ default writer",
      reported_ecc: format === "jab" ? "official CLI default" : "ZXing-C++ default",
      detail: "Generated and decoded by the native C++ comparison runner.",
      native_width: number(fields, "width"),
      native_height: number(fields, "height"),
      geometry: null,
      diameter_mm: null,
    });
  }
  return {
    payload_type: input.payloadType,
    payload_bytes: payload.length,
    payload_base64: payload.toString("base64"),
    canvas_px: 1024,
    occupied_px: 900,
    normalization: "Each full symbol, including its required quiet zone, is fitted into the same 900×900 px occupied area on a 1024×1024 px canvas.",
    ecc_comparability: "Profiles are toolchain-specific and not equivalent: Orbiqo Balanced RS; QR and Aztec use ZXing-C++ defaults; JAB uses the official CLI default.",
    items,
  };
}

export function nativeHealth() {
  return {
    product: "Orbiqo Lab",
    reference_package: "Orbiqo native C++17 codec",
    reference_version: "draft-0.6-native",
    reference_root: nativePath,
    supported_format_versions: [1, 2, 3, 4, 5],
    default_format_version: 5,
    default_layout: "constant-columns" as const,
    visual_identity_count: 5,
  };
}

export function nativeIdentities() {
  const descriptions = {
    reference: ["Reference", "Technical baseline with wider radial breathing room.", "Neutral / technical", "Inspection and engineering comparison"],
    pulse: ["Pulse", "The original Orbiqo signature: bright, energetic and balanced.", "Signature / vivid", "General use and product surfaces"],
    nocturne: ["Nocturne", "Deep blue, electric pink and lime with a cooler digital character.", "Digital / nocturnal", "Technology and entertainment identities"],
    terra: ["Terra", "Teal, mineral orange and warm yellow with an editorial character.", "Warm / editorial", "Hospitality, culture and physical products"],
    signal: ["Signal", "Blue, coral and mint tuned for a crisp contemporary presence.", "Clear / contemporary", "Services, wayfinding and communications"],
  } as const;
  const rows = (Object.keys(identities) as Array<keyof typeof identities>).map(id => {
    const selected = identities[id];
    const info = descriptions[id];
    return {
      id,
      name: info[0],
      description: info[1],
      tone: info[2],
      palette_id: selected.palette,
      palette_name: paletteNames[selected.palette],
      colors: [...paletteColors[selected.palette]],
      visual_style: id === "reference" ? "reference" as const : "pulse" as const,
      angular_fill: selected.angular,
      radial_fill: selected.radial,
      recommended_for: info[3],
      validation_status: "digital-validated" as const,
      format_version: 5,
    };
  });
  return { default_identity_id: "pulse" as const, custom_colors_supported: false as const, identities: rows };
}

let capacityCache: Promise<Array<Record<string, number | string>>> | undefined;
let capacityCacheKey: string | undefined;

export async function nativeCapacities(input: { alphabet: "color4" | "mono2"; ecc: "fast" | "balanced" | "robust" | "extreme" }) {
  const cacheKey = `${input.alphabet}:${input.ecc}`;
  if (!capacityCache || capacityCacheKey !== cacheKey) {
    capacityCacheKey = cacheKey;
    capacityCache = Promise.all([6, 0, 5, 1, 2, 3, 4].map(version => nativeGenerate({
      payloadType: "text",
      text: "",
      sizingMode: "manual",
      geometry: version,
      alphabet: input.alphabet,
      ecc: input.ecc,
      compression: "none",
      dpi: 72,
      identityId: "reference",
    }))).then(generated => generated.map(symbol => ({
      version: symbol.metadata.geometry_version,
      name: symbol.metadata.geometry_name,
      rings: ({ 0: 2, 1: 12, 2: 18, 3: 24, 4: 30, 5: 4, 6: 1 } as Record<number, number>)[symbol.metadata.geometry_version],
      recommended_diameter_mm: symbol.metadata.recommended_diameter_mm,
      format_version: symbol.metadata.format_version,
      layout_name: "constant-columns" as const,
      columns: symbol.metadata.columns,
      data_inner: symbol.metadata.data_inner,
      payload_cells: symbol.metadata.payload_cells ?? 0,
      channel_bits: symbol.metadata.channel_bits ?? 0,
      channel_bytes: symbol.metadata.channel_bytes ?? 0,
      maximum_uncompressed_payload_bytes: symbol.metadata.maximum_uncompressed_payload_bytes,
    })));
  }
  return { alphabet: input.alphabet.toUpperCase(), ecc: input.ecc.toUpperCase(), rows: await capacityCache };
}

export async function nativeRecommendSizing(input: {
  payloadType: "text" | "url" | "binary";
  text?: string;
  payloadBase64?: string;
  alphabet: "color4" | "mono2";
  ecc: "fast" | "balanced" | "robust" | "extreme";
  compression: "auto" | "none" | "deflate";
}) {
  const generated = await nativeGenerate({ ...input, sizingMode: "auto", geometry: "auto", dpi: 72, identityId: "reference" });
  return {
    format_version: generated.metadata.format_version,
    geometry_version: generated.metadata.geometry_version,
    geometry_name: generated.metadata.geometry_name,
    recommended_diameter_mm: generated.metadata.recommended_diameter_mm,
    payload_bytes: generated.metadata.payload_bytes,
    frame_bytes: generated.metadata.frame_bytes,
    compression: input.compression === "auto"
      ? (generated.metadata.frame_bytes < generated.metadata.payload_bytes + 8 ? "DEFLATE" : "NONE")
      : input.compression.toUpperCase(),
    maximum_uncompressed_payload_bytes: generated.metadata.maximum_uncompressed_payload_bytes,
    remaining_nominal_payload_bytes: generated.metadata.maximum_uncompressed_payload_bytes - generated.metadata.payload_bytes,
    selection_reason: "smallest geometry that fits the encoded frame at the selected ECC",
  };
}
