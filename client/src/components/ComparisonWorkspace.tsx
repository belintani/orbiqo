import { Button } from "@/components/ui/button";
import { trpc } from "@/lib/trpc";
import type { OrbiqoIdentityId, OrbiqoPayloadType } from "@shared/orbiqo";
import { Binary, Equal, LoaderCircle, RefreshCw, Scale, ShieldAlert } from "lucide-react";
import { useEffect, useRef } from "react";
import { toast } from "sonner";

type ComparisonWorkspaceProps = {
  payloadType: OrbiqoPayloadType;
  text?: string;
  payloadBase64?: string;
  identityId: OrbiqoIdentityId;
  centerMark?: string;
};

export function ComparisonWorkspace({ payloadType, text, payloadBase64, identityId, centerMark }: ComparisonWorkspaceProps) {
  const generatedOnce = useRef(false);
  const comparison = trpc.orbiqo.compareSymbols.useMutation({
    onError(error) {
      toast.error("Comparison failed", { description: error.message });
    },
  });
  const request = { payloadType, text, payloadBase64, identityId, centerMark };
  const hasPayload = payloadType === "binary" ? Boolean(payloadBase64) : Boolean(text);

  useEffect(() => {
    if (generatedOnce.current || !hasPayload) return;
    generatedOnce.current = true;
    comparison.mutate(request);
    // Generate once when this workspace opens; explicit refresh handles later payload edits.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <section className="comparison-workspace" aria-labelledby="comparison-title">
      <header className="comparison-heading">
        <div>
          <p className="eyebrow"><Equal size={14} /> SAME PAYLOAD / FOUR REAL TOOLCHAINS</p>
          <h2 id="comparison-title">See the formats <em>at the same time.</em></h2>
          <p>Each complete symbol is fitted into the same occupied area. The source payload is identical; only the encoding format changes.</p>
        </div>
        <div className="comparison-actions">
          <span><Binary size={14} /> {comparison.data?.payload_bytes ?? "—"} payload bytes</span>
          <Button
            variant="outline"
            onClick={() => comparison.mutate(request)}
            disabled={!hasPayload || comparison.isPending}
          >
            {comparison.isPending ? <LoaderCircle className="animate-spin" size={15} /> : <RefreshCw size={15} />}
            {comparison.data ? "Regenerate" : "Generate comparison"}
          </Button>
        </div>
      </header>

      {!hasPayload ? (
        <div className="comparison-empty">Return to Create and choose a payload first.</div>
      ) : comparison.isPending && !comparison.data ? (
        <div className="comparison-loading"><LoaderCircle className="animate-spin" /><span>Generating Orbiqo, QR, Aztec and JAB…</span></div>
      ) : comparison.data ? (
        <>
          <div className="comparison-grid">
            {comparison.data.items.map((item, index) => (
              <article className={`comparison-card comparison-card--${item.id}`} key={item.id}>
                <div className="comparison-card__header">
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <div><p>{item.id === "orbiqo" ? "RADIAL / FOUR-STATE" : item.id === "jab" ? "MATRIX / FOUR-STATE" : "MATRIX / MONO"}</p><h3>{item.name}</h3></div>
                  <small>{comparison.data.occupied_px} px</small>
                </div>
                <div className="comparison-symbol">
                  <img src={`data:image/png;base64,${item.png_base64}`} alt={`${item.name} encoding the shared payload`} />
                </div>
                <dl className="comparison-card__meta">
                  <div><dt>Profile</dt><dd>{item.profile}</dd></div>
                  <div><dt>ECC reported</dt><dd>{item.reported_ecc}</dd></div>
                  <div><dt>Native/logical</dt><dd>{item.native_width} × {item.native_height}</dd></div>
                  <div><dt>Toolchain</dt><dd>{item.toolchain}</dd></div>
                </dl>
                <p className="comparison-detail">{item.detail}</p>
              </article>
            ))}
          </div>

          <div className="comparison-method">
            <div><Scale size={17} /><span><strong>Normalized display</strong>{comparison.data.normalization}</span></div>
            <div><ShieldAlert size={17} /><span><strong>ECC caveat</strong>{comparison.data.ecc_comparability}</span></div>
          </div>
        </>
      ) : null}
    </section>
  );
}
