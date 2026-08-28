import { trpc } from "@/lib/trpc";
import { Braces, CheckCircle2, CircleAlert, Gauge, LoaderCircle, TimerReset } from "lucide-react";

function signedPercent(value: number) {
  return `${value < 0 ? "−" : "+"}${Math.abs(value).toFixed(1)}%`;
}

function milliseconds(value: number) {
  return `${value.toFixed(1)} ms`;
}

export function NativeRendererWorkspace() {
  const comparison = trpc.orbiqo.nativeRendererComparison.useQuery(undefined, { staleTime: Infinity });

  if (comparison.isLoading) {
    return <section className="native-renderer-workspace native-renderer-workspace--state"><LoaderCircle className="animate-spin" size={18} /> Loading measured renderer comparison…</section>;
  }
  if (comparison.isError || !comparison.data) {
    return <section className="native-renderer-workspace native-renderer-workspace--state"><CircleAlert size={18} /> The native renderer comparison is unavailable: {comparison.error?.message ?? "no benchmark artifact"}</section>;
  }

  const data = comparison.data;
  const fastestGain = Math.min(...data.cases.map(item => item.native_relative_change_percent));

  return (
    <section className="native-renderer-workspace" aria-labelledby="native-renderer-title">
      <header className="native-renderer-heading">
        <div>
          <p className="eyebrow"><Braces size={14} /> RENDERERS / SAME ENCODED SYMBOL</p>
          <h2 id="native-renderer-title">Python is the <em>reference.</em><br />C++ is the raster experiment.</h2>
        </div>
        <p>The comparison starts after a symbol is encoded. It measures PNG-ready raster production for the same geometry, registered identity fills and empty center—not framing, protection coding, SVG or decode.</p>
      </header>

      <div className="native-renderer-hero-grid">
        <article className="native-engine-card native-engine-card--reference">
          <span>DEFAULT / REFERENCE</span>
          <h3>Python renderer</h3>
          <p>Source of truth for every configuration, including center text, remote images and SVG.</p>
          <footer><CheckCircle2 size={14} /> Always available</footer>
        </article>
        <div className="native-renderer-flow" aria-label="Native rendering flow">
          <span>Encoded symbol</span><i>→</i><span>Versioned draw list</span><i>→</i><strong>C++ / libpng</strong><i>→</i><span>PNG</span>
        </div>
        <article className="native-engine-card native-engine-card--native">
          <span>OPT-IN / EXPERIMENTAL</span>
          <h3>C++ raster core</h3>
          <p>Renders the core only with an empty reserved center; Python visibly resumes when center content is used.</p>
          <footer><Gauge size={14} /> No silent replacement</footer>
        </article>
      </div>

      <div className="native-summary-grid" aria-label="Native renderer benchmark summary">
        <article><TimerReset size={18} /><span>Largest measured gain</span><strong>{signedPercent(fastestGain)}</strong><small>Native C++ versus Python raster median</small></article>
        <article><CheckCircle2 size={18} /><span>Decode validation</span><strong>7 / 7</strong><small>Current Draft 0.6 geometries returned exact bytes</small></article>
        <article><Braces size={18} /><span>Method</span><strong>{data.method.runs} runs</strong><small>{data.method.payload_bytes} B · {data.method.dpi} DPI · {data.method.ecc}</small></article>
      </div>

      <div className="native-results-table" role="region" aria-label="Python and C++ raster timing by geometry" tabIndex={0}>
        <div className="native-results-table__header"><span>Geometry</span><span>Python reference</span><span>C++ experiment</span><span>Difference</span><span>Exact decode</span></div>
        {data.cases.map(item => (
          <div className="native-results-table__row" key={item.geometry}>
            <span><strong>{item.geometry}</strong><small>{item.diameter_mm} mm</small></span>
            <span>{milliseconds(item.reference_renderer_median_ms)}</span>
            <span>{milliseconds(item.native_renderer_median_ms)}</span>
            <span className={item.native_relative_change_percent < 0 ? "is-faster" : ""}>{signedPercent(item.native_relative_change_percent)}</span>
            <span className={item.reference_roundtrip && item.native_roundtrip ? "native-check is-valid" : "native-check"}><CheckCircle2 size={14} /> Exact</span>
          </div>
        ))}
      </div>

      <aside className="native-renderer-limit">
        <CircleAlert size={18} />
        <p><strong>How to read this page.</strong> {data.method.scope}. It is an implementation benchmark on this machine, not a general device-speed claim. The C++ option stays experimental until center-content parity and degradation checks are measured.</p>
      </aside>
    </section>
  );
}
