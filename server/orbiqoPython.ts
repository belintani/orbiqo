import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const moduleDirectory = path.dirname(fileURLToPath(import.meta.url));
export function resolveBridgePath(projectRoot = process.cwd(), configuredPath?: string): string {
  return configuredPath ?? path.join(projectRoot, "server", "python", "orbiqo_bridge.py");
}

const bridgePath = resolveBridgePath(process.cwd(), process.env.ORBIQO_BRIDGE_PATH);
const referenceRoot = process.env.ORBIQO_RADIALCODE_ROOT ?? path.resolve(moduleDirectory, "python", "vendor", "radialcode");
const maxInputBytes = 12 * 1024 * 1024;
const maxOutputBytes = 30 * 1024 * 1024;

export type BridgeFailure = { code: string; message: string };
type BridgeEnvelope<T> = { ok: true; result: T } | { ok: false; error: BridgeFailure };

export class OrbiqoBridgeError extends Error {
  constructor(
    public readonly bridgeCode: string,
    message: string,
  ) {
    super(message);
    this.name = "OrbiqoBridgeError";
  }
}

export async function callOrbiqoPython<T>(
  request: Record<string, unknown>,
  options: { timeoutMs?: number } = {},
): Promise<T> {
  const input = JSON.stringify(request);
  if (Buffer.byteLength(input) > maxInputBytes) {
    throw new OrbiqoBridgeError("INPUT_TOO_LARGE", "Request exceeds the local bridge limit");
  }

  return await new Promise<T>((resolve, reject) => {
    const pythonPath = [path.join(referenceRoot, "src"), process.env.PYTHONPATH].filter(Boolean).join(path.delimiter);
    const child = spawn("python3", [bridgePath], {
      cwd: path.resolve(moduleDirectory, ".."),
      env: { ...process.env, ORBIQO_RADIALCODE_ROOT: referenceRoot, PYTHONPATH: pythonPath },
      stdio: ["pipe", "pipe", "pipe"],
    });
    const stdout: Buffer[] = [];
    const stderr: Buffer[] = [];
    let outputBytes = 0;
    let settled = false;

    const finish = (error?: Error, value?: T) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (error) reject(error);
      else resolve(value as T);
    };

    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      finish(new OrbiqoBridgeError("TIMEOUT", "Reference operation exceeded its time limit"));
    }, options.timeoutMs ?? 25_000);

    child.stdout.on("data", (chunk: Buffer) => {
      outputBytes += chunk.length;
      if (outputBytes > maxOutputBytes) {
        child.kill("SIGKILL");
        finish(new OrbiqoBridgeError("OUTPUT_TOO_LARGE", "Reference operation exceeded its output limit"));
        return;
      }
      stdout.push(chunk);
    });
    child.stderr.on("data", (chunk: Buffer) => stderr.push(chunk));
    child.on("error", error => finish(new OrbiqoBridgeError("PROCESS_FAILURE", error.message)));
    child.on("close", () => {
      if (settled) return;
      const raw = Buffer.concat(stdout).toString("utf8").trim();
      let envelope: BridgeEnvelope<T>;
      try {
        envelope = JSON.parse(raw) as BridgeEnvelope<T>;
      } catch {
        const detail = Buffer.concat(stderr).toString("utf8").trim();
        finish(new OrbiqoBridgeError("INVALID_RESPONSE", detail || "Python bridge returned invalid JSON"));
        return;
      }
      if (!envelope.ok) {
        finish(new OrbiqoBridgeError(envelope.error.code, envelope.error.message));
        return;
      }
      finish(undefined, envelope.result);
    });

    child.stdin.end(input);
  });
}
