import { Button } from "@/components/ui/button";
import { trpc } from "@/lib/trpc";
import type { OrbiqoDecodedSymbol } from "@shared/orbiqo";
import {
  AlertTriangle,
  Camera,
  CheckCircle2,
  FileImage,
  Focus,
  Gauge,
  LoaderCircle,
  MonitorUp,
  RotateCcw,
  ScanLine,
  ShieldCheck,
  Square,
  Upload,
  Video,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

type ReaderPhase =
  | "idle"
  | "requesting-permission"
  | "stream-ready"
  | "capturing"
  | "detecting"
  | "decoded"
  | "decode-failed"
  | "permission-denied";

type ReaderWorkspaceProps = {
  samplePngBase64?: string;
  sampleGeometryVersion?: number;
};

const maxUploadBytes = 8 * 1024 * 1024;

function arrayBufferToBase64(buffer: ArrayBuffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let index = 0; index < bytes.length; index += 0x8000) {
    binary += String.fromCharCode(...Array.from(bytes.subarray(index, index + 0x8000)));
  }
  return btoa(binary);
}

function phaseCopy(phase: ReaderPhase) {
  const copy: Record<ReaderPhase, { label: string; detail: string }> = {
    idle: { label: "Ready for an image", detail: "Nothing leaves this local workspace." },
    "requesting-permission": { label: "Waiting for permission", detail: "Your browser controls camera and screen access." },
    "stream-ready": { label: "Stream ready", detail: "Align one Orbiqo symbol inside the guide." },
    capturing: { label: "Capturing frame", detail: "The current frame is being resized locally." },
    detecting: { label: "Detecting symbol", detail: "Guard, pose anchors, homography, and palette decoding are running." },
    decoded: { label: "Integrity verified", detail: "The payload passed header, ECC, and frame checks." },
    "decode-failed": { label: "No valid payload", detail: "The image was handled safely, but no valid Orbiqo symbol decoded." },
    "permission-denied": { label: "Permission not granted", detail: "Choose upload, or allow access and try again." },
  };
  return copy[phase];
}

export function ReaderWorkspace({ samplePngBase64, sampleGeometryVersion }: ReaderWorkspaceProps) {
  const [phase, setPhase] = useState<ReaderPhase>("idle");
  const [sourceLabel, setSourceLabel] = useState("No source selected");
  const [previewUrl, setPreviewUrl] = useState<string>();
  const [result, setResult] = useState<OrbiqoDecodedSymbol>();
  const [failure, setFailure] = useState<string>();
  const [autoScan, setAutoScan] = useState(true);
  const [canonical, setCanonical] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | undefined>(undefined);
  const pendingRef = useRef(false);

  const decode = trpc.orbiqo.decode.useMutation({
    onMutate() {
      pendingRef.current = true;
      setFailure(undefined);
      setPhase("detecting");
    },
    onSuccess(decoded) {
      setResult(decoded);
      setPhase("decoded");
    },
    onError(error) {
      setResult(undefined);
      setFailure(error.message);
      setPhase("decode-failed");
    },
    onSettled() {
      pendingRef.current = false;
    },
  });

  function stopStream() {
    streamRef.current?.getTracks().forEach(track => track.stop());
    streamRef.current = undefined;
    if (videoRef.current) videoRef.current.srcObject = null;
    if (phase === "stream-ready") setPhase("idle");
  }

  useEffect(() => stopStream, []);

  async function startStream(kind: "camera" | "screen") {
    stopStream();
    setResult(undefined);
    setFailure(undefined);
    setPhase("requesting-permission");
    try {
      const stream =
        kind === "camera"
          ? await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false })
          : await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
      streamRef.current = stream;
      setSourceLabel(kind === "camera" ? "Live camera" : "Shared screen");
      setPreviewUrl(undefined);
      setCanonical(false);
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      stream.getVideoTracks()[0]?.addEventListener("ended", () => {
        streamRef.current = undefined;
        setPhase("idle");
        setSourceLabel("Stream ended");
      });
      setPhase("stream-ready");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Browser permission was not granted";
      setFailure(message);
      setPhase("permission-denied");
    }
  }

  function submitDecode(imageBase64: string, isCanonical: boolean, geometryHint?: number) {
    if (pendingRef.current) return;
    decode.mutate({
      imageBase64,
      canonical: isCanonical,
      geometryHint: isCanonical ? geometryHint : undefined,
      outputSize: 1024,
      erasureThreshold: 0.55,
    });
  }

  function captureFrame() {
    const video = videoRef.current;
    if (!video || video.readyState < 2 || !video.videoWidth || pendingRef.current) return;
    setPhase("capturing");
    const scale = Math.min(1, 1600 / Math.max(video.videoWidth, video.videoHeight));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(64, Math.round(video.videoWidth * scale));
    canvas.height = Math.max(64, Math.round(video.videoHeight * scale));
    const context = canvas.getContext("2d", { alpha: false });
    if (!context) {
      setFailure("Canvas capture is unavailable in this browser");
      setPhase("decode-failed");
      return;
    }
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    const dataUrl = canvas.toDataURL("image/jpeg", 0.88);
    setPreviewUrl(dataUrl);
    submitDecode(dataUrl.split(",")[1] ?? "", false);
  }

  useEffect(() => {
    if (!autoScan || phase !== "stream-ready" || !streamRef.current) return;
    const timer = window.setInterval(captureFrame, 1800);
    return () => window.clearInterval(timer);
    // captureFrame reads current refs and is intentionally scheduled only by stream state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoScan, phase]);

  async function handleUpload(file?: File) {
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setFailure("Choose a PNG, JPEG, or WebP image");
      setPhase("decode-failed");
      return;
    }
    if (file.size > maxUploadBytes) {
      setFailure("Image exceeds the 8 MiB upload limit");
      setPhase("decode-failed");
      return;
    }
    stopStream();
    const bytes = await file.arrayBuffer();
    const base64 = arrayBufferToBase64(bytes);
    setSourceLabel(file.name);
    setPreviewUrl(URL.createObjectURL(file));
    setCanonical(false);
    submitDecode(base64, false);
  }

  function decodeCurrentSample() {
    if (!samplePngBase64) return;
    stopStream();
    setSourceLabel("Current generated artifact");
    setPreviewUrl(`data:image/png;base64,${samplePngBase64}`);
    setCanonical(true);
    submitDecode(samplePngBase64, true, sampleGeometryVersion);
  }

  const copy = phaseCopy(phase);
  const confidence = result ? Math.round(result.diagnostics.average_confidence * 100) : undefined;
  const hasLiveStream = Boolean(streamRef.current);

  return (
    <section className="reader-workspace">
      <div className="reader-control">
        <div className="reader-heading">
          <span className="step-index">01</span>
          <div><p>Source</p><h2>Choose a digital capture</h2></div>
        </div>

        <div className="source-actions">
          <label className="source-card">
            <Upload size={19} /><span><strong>Upload image</strong><small>PNG, JPEG, WebP · 8 MiB</small></span>
            <input type="file" accept="image/png,image/jpeg,image/webp" onChange={event => void handleUpload(event.target.files?.[0])} />
          </label>
          <button className="source-card" type="button" onClick={() => void startStream("camera")}>
            <Camera size={19} /><span><strong>Use camera</strong><small>Permission requested explicitly</small></span>
          </button>
          <button className="source-card" type="button" onClick={() => void startStream("screen")}>
            <MonitorUp size={19} /><span><strong>Share screen</strong><small>Scan a symbol on another window</small></span>
          </button>
          <button className="source-card" type="button" disabled={!samplePngBase64} onClick={decodeCurrentSample}>
            <FileImage size={19} /><span><strong>Use generated</strong><small>Canonical round-trip check</small></span>
          </button>
        </div>

        <div className="reader-divider" />
        <div className="reader-heading reader-heading--compact">
          <span className="step-index">02</span>
          <div><p>Control</p><h2>Make decoding explicit</h2></div>
        </div>

        <div className="reader-options">
          <label><span><strong>Auto scan</strong><small>Every 1.8 seconds while a stream is open</small></span><input type="checkbox" checked={autoScan} onChange={event => setAutoScan(event.target.checked)} /></label>
        </div>

        <div className={`reader-status reader-status--${phase}`}>
          {phase === "decoded" ? <CheckCircle2 /> : phase === "decode-failed" || phase === "permission-denied" ? <AlertTriangle /> : phase === "detecting" || phase === "capturing" || phase === "requesting-permission" ? <LoaderCircle className="animate-spin" /> : <Focus />}
          <span><strong>{copy.label}</strong><small>{copy.detail}</small></span>
        </div>
        {failure ? <p className="reader-error">{failure}</p> : null}

        {hasLiveStream ? <div className="stream-buttons">
          <Button onClick={captureFrame} disabled={decode.isPending}><ScanLine size={17} />Capture &amp; decode</Button>
          <Button variant="outline" onClick={stopStream}><Square size={15} />Stop stream</Button>
        </div> : null}
      </div>

      <div className="reader-stage-panel">
        <div className="radial-ui-motif radial-ui-motif--reader" aria-hidden="true"><i /><i /><i /></div>
        <div className="reader-topline">
          <div><span className="step-index step-index--dark">03</span><span><small>LIVE INSPECTION</small><strong>{sourceLabel}</strong></span></div>
          <span className="privacy-chip"><ShieldCheck size={13} /> PULSE FIELD · LOCAL</span>
        </div>

        <div className="reader-viewport">
          <video ref={videoRef} muted playsInline className={streamRef.current ? "is-visible" : ""} />
          {previewUrl && !streamRef.current ? <img src={previewUrl} alt="Image selected for Orbiqo decoding" /> : null}
          {!previewUrl && !streamRef.current ? <div className="reader-empty"><Video /><span>No camera or image source</span></div> : null}
          <div className="scan-guide"><i /><i /><i /><i /><span>ALIGN OUTER GUARD</span></div>
        </div>

        {result ? (
          <div className="decode-result">
            <div className="result-title"><CheckCircle2 /><span><small>DECODED CONTENT</small><strong>{result.payload_type === "BINARY" ? `${result.payload_bytes} binary bytes` : result.text}</strong></span></div>
            <button onClick={() => navigator.clipboard.writeText(result.text ?? result.payload_base64)} type="button">Copy</button>
          </div>
        ) : (
          <div className="decode-result decode-result--empty"><ScanLine /><span><small>DECODED CONTENT</small><strong>Waiting for an integrity-verified payload</strong></span></div>
        )}

        <div className="reader-diagnostics">
          <div><Gauge /><span>Confidence</span><strong>{confidence === undefined ? "—" : `${confidence}%`}</strong></div>
          <div><RotateCcw /><span>RS corrected</span><strong>{result?.diagnostics.corrected_rs_symbols ?? "—"}</strong></div>
          <div><Focus /><span>Reprojection</span><strong>{result?.rectification ? `${result.rectification.reprojection_error_px.toFixed(2)} px` : canonical && result ? "canonical" : "—"}</strong></div>
          <div><LoaderCircle /><span>Decode time</span><strong>{result ? `${result.diagnostics.processing_time_ms.toFixed(0)} ms` : "—"}</strong></div>
        </div>
      </div>
    </section>
  );
}
