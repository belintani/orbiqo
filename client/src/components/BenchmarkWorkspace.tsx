import { Button } from "@/components/ui/button";
import { trpc } from "@/lib/trpc";
import { externalTimingCopy } from "@/lib/benchmarkPresentation";
import type { OrbiqoEccProfileBenchmark, OrbiqoNormalizedBenchmarkSummary } from "@shared/orbiqo";
import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  Database,
  Download,
  ExternalLink,
  FileSearch,
  FileText,
  FlaskConical,
  Gauge,
  LoaderCircle,
  ShieldAlert,
} from "lucide-react";

const formatOrder = ["orbiqo", "qr", "aztec", "jab"];
const formatLabels: Record<string, string> = { orbiqo: "Orbiqo", qr: "QR", aztec: "Aztec", jab: "JAB" };
const eccProfileOrder = ["fast", "balanced", "robust", "extreme"] as const;
const eccProfileLabels: Record<(typeof eccProfileOrder)[number], string> = { fast: "Fast", balanced: "Balanced", robust: "Robust", extreme: "Extreme" };
const profileLabels: Record<string, string> = {
  clean: "Clean", blur_1_5: "Blur 1.5", blur_3_0: "Blur 3.0", noise_8: "Noise 8", jpeg_40: "JPEG 40",
  downsample_0_35: "Downsample", occlusion_0_06: "Occlusion", combined: "Combined",
};

function downloadText(contents: string, filename: string, type: string) {
  const url = URL.createObjectURL(new Blob([contents], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function median(summary: OrbiqoNormalizedBenchmarkSummary, format: string, metric: "generation_time" | "decode_time") {
  return summary.timing.find(row => row.format === format && row.metric === metric)?.median_ms ?? 0;
}

function profileMedian(profile: OrbiqoEccProfileBenchmark["profiles"][number], metric: "encode" | "decode") {
  return profile[metric].median_ms;
}

export function BenchmarkWorkspace() {
  const summaryQuery = trpc.orbiqo.normalizedBenchmarkSummary.useQuery(undefined, { staleTime: 60_000 });
  const legacyQuery = trpc.orbiqo.benchmarkSummary.useQuery(undefined, { staleTime: 60_000 });
  const eccProfileQuery = trpc.orbiqo.eccProfileComparison.useQuery(undefined, { staleTime: 60_000 });
  const artifactQuery = trpc.orbiqo.normalizedBenchmarkArtifacts.useQuery(undefined, { enabled: false });
  const eccProfileArtifactQuery = trpc.orbiqo.eccProfileComparisonArtifacts.useQuery(undefined, { enabled: false });

  async function downloadArtifact(kind: "csv" | "capacity" | "methodology") {
    const result = await artifactQuery.refetch();
    if (!result.data) return;
    if (kind === "csv") downloadText(result.data.rawCsv, "orbiqo-normalized-runs.csv", "text/csv;charset=utf-8");
    else if (kind === "capacity") downloadText(result.data.capacityCsv, "orbiqo-normalized-capacity-trials.csv", "text/csv;charset=utf-8");
    else downloadText(result.data.methodology, "orbiqo-normalized-methodology.md", "text/markdown;charset=utf-8");
  }

  async function downloadProfileArtifact(kind: "csv" | "methodology") {
    const result = await eccProfileArtifactQuery.refetch();
    if (!result.data) return;
    if (kind === "csv") downloadText(result.data.rawCsv, "orbiqo-ecc-profile-runs.csv", "text/csv;charset=utf-8");
    else downloadText(result.data.methodology, "orbiqo-ecc-profile-method.md", "text/markdown;charset=utf-8");
  }

  if (summaryQuery.isPending || legacyQuery.isPending || eccProfileQuery.isPending) {
    return <section className="benchmark-loading"><LoaderCircle className="animate-spin" /><span>Validating normalized artifacts…</span></section>;
  }
  if (!summaryQuery.data || !legacyQuery.data || !eccProfileQuery.data) {
    return <section className="benchmark-loading benchmark-loading--error"><AlertTriangle /><span>Benchmark artifacts could not be loaded.</span></section>;
  }
  const summary = summaryQuery.data;
  const profileComparison = eccProfileQuery.data;
  const internalProfiles = eccProfileOrder.map(ecc => profileComparison.profiles.find(profile => profile.ecc === ecc)).filter((profile): profile is OrbiqoEccProfileBenchmark["profiles"][number] => Boolean(profile));
  const balancedProfile = internalProfiles.find(profile => profile.ecc === "balanced");
  const profileTimingMaximum = Math.max(...internalProfiles.flatMap(profile => [profileMedian(profile, "encode"), profileMedian(profile, "decode")]));
  const perspective = legacyQuery.data.orbiqo_perspective;
  const timingRows = formatOrder.map(format => ({ format, generation: median(summary, format, "generation_time"), decode: median(summary, format, "decode_time") }));
  const timingMaximum = Math.max(...timingRows.flatMap(row => [row.generation, row.decode]));
  const degradationProfiles = Array.from(new Set(summary.degradation.map(row => row.profile)));
  const totalDegradation = summary.degradation.reduce((total, row) => total + row.successes, 0);
  const degradationTrials = summary.degradation.reduce((total, row) => total + row.trials, 0);
  const generatedAt = new Date(summary.environment.generated_utc);
  const orbiqoCapacity = summary.capacity.find(row => row.format === "orbiqo");

  return (
    <section className="benchmark-workspace">
      <div className="radial-ui-motif radial-ui-motif--benchmark" aria-hidden="true"><i /><i /><i /></div>
      <div className="benchmark-head">
        <div>
          <p className="eyebrow"><FlaskConical size={14} /> ORBIQO PROFILE STUDY / DRAFT 0.6</p>
          <h2>Choose the protection <em>you actually need.</em></h2>
          <p>Before comparing formats, this study measures Fast, Balanced, Robust and Extreme with the same 64-byte payload. It records encoding, full image decoding, Auto fit geometry and a separate 6% digital-occlusion corpus.</p>
        </div>
        <div className="benchmark-head-actions">
          <span><Database size={14} /> 64 B · 10 timing runs · 3 patterns × 4 placements</span>
          <div>
            <Button variant="outline" onClick={() => void downloadProfileArtifact("methodology")}><FileText size={15} />Profile method</Button>
            <Button onClick={() => void downloadProfileArtifact("csv")}><Download size={15} />Profile runs</Button>
          </div>
        </div>
      </div>

      <div className="benchmark-verdict">
        <CheckCircle2 />
        <span><small>INTERNAL PROFILE CONCLUSION</small><strong>For this 64-byte digital corpus, Robust is the measured resilience choice: 3/4 at every payload pattern under 6% occlusion. Fast and Extreme reach 0/4; Balanced varies by pattern. The external comparison below remains separate context.</strong></span>
      </div>

      <section className="profile-study" aria-labelledby="profile-study-title">
        <header className="profile-study-head">
          <div><p>01 / INTERNAL COMPARISON</p><h3 id="profile-study-title">Same payload, different protection.</h3></div>
          <span>Auto fit may select a different geometry; that outcome is reported rather than hidden.</span>
        </header>
        <div className="profile-study-grid">
          {internalProfiles.map(profile => {
            const isRobust = profile.ecc === "robust";
            const maxTiming = Math.max(profileMedian(profile, "encode"), profileMedian(profile, "decode"));
            return (
              <article className={`profile-study-card ${isRobust ? "is-robust" : ""}`} key={profile.ecc}>
                <header><span>{eccProfileLabels[profile.ecc]}</span><small>Auto → {profile.geometry} · {profile.data_rings} rings</small></header>
                <div className="profile-study-timing">
                  {(["encode", "decode"] as const).map(metric => {
                    const value = profileMedian(profile, metric);
                    return <div key={metric}><span>{metric === "encode" ? "ENCODE" : "DECODE"}</span><i style={{ width: `${Math.max(3, (value / profileTimingMaximum) * 100)}%` }} /><strong>{value.toFixed(value < 10 ? 2 : 1)} ms</strong></div>;
                  })}
                </div>
                <div className="profile-study-occlusion"><span>6% DIGITAL OCCLUSION</span><strong>{profile.occlusion.minimum_successes}/{profile.occlusion.trials_per_pattern}</strong><small>minimum across 3 payload patterns</small></div>
                <p>{profile.ecc === "robust" ? "Measured resilience profile in this corpus; it trades redundancy for lower payload margin." : profile.ecc === "extreme" ? "More parity moved this payload to Small geometry and did not improve this measured corpus." : profile.ecc === "fast" ? "Lowest measured encode time here, with no successful occlusion recovery in this corpus." : "Default balance profile; its measured occlusion result varies by payload pattern."}</p>
              </article>
            );
          })}
        </div>
        <p className="profile-study-note">Encode measures framing, protection coding and placement. Decode measures the full vision pipeline from the same normalized digital raster. Neither result is a print or device guarantee.</p>
      </section>

      <div className="benchmark-section-break"><span>02 / EXTERNAL CONTEXT</span><div><h3>Balanced beside QR, Aztec and JAB.</h3><p>The external equal-area benchmark uses Orbiqo Balanced as its declared default. It is useful for context, but it does not make protection families or color handling equivalent.</p></div></div>

      <div className="benchmark-kpis">
        <div><Database /><span>Compared toolchains</span><strong>{summary.adapters.length}</strong><small>One occupied digital area</small></div>
        <div><Gauge /><span>Exact degradation</span><strong>{Math.round((totalDegradation / degradationTrials) * 100)}%</strong><small>{totalDegradation} / {degradationTrials} payloads</small></div>
        <div><BarChart3 /><span>Orbiqo capacity</span><strong>{orbiqoCapacity?.maximum_payload_bytes ?? "—"} B</strong><small>{orbiqoCapacity?.nominal_pitch_px.toFixed(2)} px boundary pitch</small></div>
        <div><FileSearch /><span>Capacity floor</span><strong>{summary.normalization.minimum_feature_pitch_px} px</strong><small>{generatedAt.toLocaleDateString(undefined, { month: "short", day: "2-digit" })} artifact</small></div>
      </div>

      <div className="benchmark-grid">
        <article className="benchmark-card benchmark-card--wide">
          <div className="benchmark-card-title"><div><p>{externalTimingCopy.eyebrow}</p><h3>{externalTimingCopy.title}</h3></div><span>64 BYTES · BALANCED FOR ORBIQO · LOG SCALE</span></div>
          <div className="benchmark-timing-context">
            <span>ORBIQO BALANCED ENCODER CORE</span>
            <strong>{balancedProfile ? `${profileMedian(balancedProfile, "encode").toFixed(2)} ms` : "—"}</strong>
            <small>Framing, protection coding and placement only; PNG rendering is excluded.</small>
          </div>
          <div className="timing-chart">
            {timingRows.map(row => (
              <div className="timing-group" key={row.format}>
                <strong>{formatLabels[row.format]}</strong>
                <div className="timing-bar-row"><span>{externalTimingCopy.rasterLabel}</span><i style={{ width: `${Math.max(2, (Math.log10(row.generation + 1) / Math.log10(timingMaximum + 1)) * 100)}%` }} /><b>{row.generation.toFixed(row.generation < 10 ? 2 : 1)} ms</b></div>
                <div className="timing-bar-row timing-bar-row--decode"><span>{externalTimingCopy.decoderLabel}</span><i style={{ width: `${Math.max(2, (Math.log10(row.decode + 1) / Math.log10(timingMaximum + 1)) * 100)}%` }} /><b>{row.decode.toFixed(row.decode < 10 ? 2 : 1)} ms</b></div>
              </div>
            ))}
          </div>
          <p className="benchmark-note">{externalTimingCopy.scope} ZXing is native C++; Orbiqo remains a Python reference; JAB includes process startup.</p>
        </article>

        <article className="benchmark-card">
          <div className="benchmark-card-title"><div><p>Equal-area capacity</p><h3>Exact-decode boundary</h3></div><span>BYTES · ≥7 PX</span></div>
          <div className="capacity-chart">
            {summary.capacity.map(row => {
              const maximum = Math.max(...summary.capacity.map(item => item.maximum_payload_bytes));
              return <div key={row.format}><span><strong>{formatLabels[row.format]}</strong><small>{row.reported_ecc}</small></span><i><b style={{ height: `${Math.max(4, (row.maximum_payload_bytes / maximum) * 100)}%` }} /></i><em>{row.maximum_payload_bytes}</em></div>;
            })}
          </div>
          <p className="benchmark-note">Orbiqo Draft 0.6 keeps Micro 1/2/4 and adds an external BCH copy outside the inner header cluster. Capacity uses the normative SVG/Cairo raster. JAB level 3 is weaker than Orbiqo Balanced or QR Q; this is not an ECC-equivalent winner ranking.</p>
        </article>

        <article className="benchmark-card benchmark-card--wide">
          <div className="benchmark-card-title"><div><p>Normalized channel stress</p><h3>Synthetic degradation matrix</h3></div><span>900×900 OCCUPIED · EXACT BYTES</span></div>
          <div className="degradation-table-wrap"><table className="degradation-table"><thead><tr><th>Format</th>{degradationProfiles.map(profile => <th key={profile}>{profileLabels[profile] ?? profile}</th>)}</tr></thead><tbody>
            {formatOrder.map(format => <tr key={format}><th>{formatLabels[format]}</th>{degradationProfiles.map(profile => {
              const row = summary.degradation.find(item => item.format === format && item.profile === profile);
              const rate = row?.success_rate ?? 0;
              return <td key={profile}><span className={rate === 1 ? "cell-pass" : rate > 0 ? "cell-warn" : "cell-fail"}>{row ? `${row.successes}/${row.trials}` : "—"}</span></td>;
            })}</tr>)}
          </tbody></table></div>
        </article>

        <article className="benchmark-card benchmark-card--warning">
          <div className="benchmark-card-title"><div><p>Separate vision limit</p><h3>Strong foreshortening</h3></div><ShieldAlert /></div>
          <div className="known-limit-score"><strong>{perspective.successes}</strong><span>of {perspective.trials}<small>pose/profile pairs decode</small></span></div>
          <p>This matrix is not mixed into equal-area capacity. The two extreme guard-notch failures remain strict regressions.</p>
        </article>

        <article className="benchmark-card">
          <div className="benchmark-card-title"><div><p>Profiles</p><h3>Toolchain &amp; ECC ledger</h3></div><CheckCircle2 /></div>
          <div className="toolchain-list">{summary.adapters.map(adapter => <div key={adapter.format}><span>{formatLabels[adapter.format]}</span><strong>{adapter.reported_ecc} · {adapter.toolchain}</strong></div>)}</div>
          <a href="https://github.com/zxing-cpp/zxing-cpp" target="_blank" rel="noreferrer">ZXing-C++ source <ExternalLink size={12} /></a>
        </article>
      </div>

      <article className="limitations-panel">
        <div><AlertTriangle /><span><small>LIMITATIONS</small><strong>What equal area still does not equalize</strong></span></div>
        <ol>{summary.limitations.map(limit => <li key={limit}>{limit}</li>)}</ol>
        <footer><span>PAYLOAD SHA-256</span><code>{summary.normalization.timing_payload_sha256}</code></footer>
      </article>
    </section>
  );
}
