import { describe, expect, it } from "vitest";
import { callOrbiqoPython, OrbiqoBridgeError } from "./orbiqoPython";

describe("Orbiqo adversarial bridge boundary", () => {
  it("rejects payloads above the 64 KiB reference limit", async () => {
    const oversized = Buffer.alloc(65 * 1024, 0x41).toString("base64");
    await expect(
      callOrbiqoPython({
        op: "generate",
        payload_type: "binary",
        payload_base64: oversized,
        geometry: "auto",
        alphabet: "color4",
        ecc: "balanced",
      }),
    ).rejects.toMatchObject<Partial<OrbiqoBridgeError>>({ bridgeCode: "INPUT_TOO_LARGE" });
  });

  it("rejects malformed base64 without entering image decoding", async () => {
    await expect(callOrbiqoPython({ op: "decode", image_base64: "%%%%not-base64%%%%" })).rejects.toMatchObject<
      Partial<OrbiqoBridgeError>
    >({ bridgeCode: "INVALID_BASE64" });
  });

  it("rejects non-image byte streams through a stable public failure code", async () => {
    const bytes = Buffer.alloc(4096, 0x5a).toString("base64");
    await expect(callOrbiqoPython({ op: "decode", image_base64: bytes })).rejects.toMatchObject<
      Partial<OrbiqoBridgeError>
    >({ bridgeCode: "INVALID_IMAGE" });
  });

  it("rejects requests above the Node bridge input limit before spawning Python", async () => {
    const tooLarge = "A".repeat(13 * 1024 * 1024);
    await expect(callOrbiqoPython({ op: "decode", image_base64: tooLarge })).rejects.toMatchObject<
      Partial<OrbiqoBridgeError>
    >({ bridgeCode: "INPUT_TOO_LARGE" });
  });
});
