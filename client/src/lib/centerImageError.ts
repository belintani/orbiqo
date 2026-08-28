export function describeCenterImageError(message: string): string {
  const normalized = message.toLowerCase();
  if (normalized.includes("png, jpeg, or webp") || normalized.includes("invalid format")) {
    return "The URL did not return a supported PNG, JPEG, or WebP image.";
  }
  if (normalized.includes("could not be fetched") || normalized.includes("could not be resolved") || normalized.includes("fetch failed")) {
    return "The image could not be reached. Check that the public HTTPS URL is available.";
  }
  if (normalized.includes("public address") || normalized.includes("forbidden host")) {
    return "The image host is blocked because it is not publicly reachable.";
  }
  if (normalized.includes("exceeds two mib") || normalized.includes("exceeds four million") || normalized.includes("dimensions exceed")) {
    return "The image exceeds the supported download or pixel limits.";
  }
  return message;
}
