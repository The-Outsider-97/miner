"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { Footer } from "./Footer";
import { ArtifactSubmission } from "./ArtifactSubmission";
import { Header } from "./Header";
import { Loading } from "./Loading";
import { SidePanel } from "./SidePanel";
import { Table, type TableColumn } from "./Table";
import type { BenchmarkRun, DashboardSnapshot, RuntimeMeasurement, SectionDefinition } from "./types";

const DASHBOARD_REFRESH_MS = 10_000;

const sections: readonly SectionDefinition[] = [
  { id: "overview", label: "Overview" },
  { id: "artifact", label: "Artifact" },
  { id: "slai", label: "SLAI" },
  { id: "benchmark", label: "Benchmark" },
  { id: "performance", label: "Performance" },
  { id: "system", label: "System" },
];

const available = (value: unknown) => value !== null && value !== undefined;
const number = (value: number | null | undefined, digits = 3) =>
  available(value) ? new Intl.NumberFormat("en-US", { maximumFractionDigits: digits }).format(value!) : "Not available";
const integer = (value: number | null | undefined) => number(value, 0);
const percent = (value: number | null | undefined) => available(value) ? `${(value! * 100).toFixed(1)}%` : "Not available";
const cost = (value: number | null | undefined) => available(value) ? `$${value!.toFixed(value! < 0.01 ? 6 : 4)}` : "Not available";
const ms = (value: number | null | undefined) => !available(value) ? "Not available" : value! >= 1000 ? `${(value! / 1000).toFixed(2)} s` : `${value!.toFixed(0)} ms`;
const hash = (value: string | null | undefined, size = 12) => !value ? "Not available" : value.length > size ? `${value.slice(0, size)}…` : value;
const label = (value: string | null | undefined) => !value ? "Unavailable" : value.replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase());
const date = (value: string | null | undefined) => {
  if (!value) return "Not available";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" }).format(parsed);
};

function Status({ value, text }: { value: string; text?: string }) {
  return <span className="status-label"><span className="status-dot" data-state={value} aria-hidden="true" />{text ?? label(value)}</span>;
}

function Heading({ eyebrow, title, copy }: { eyebrow: string; title: string; copy: string }) {
  return <div className="section-heading"><p className="eyebrow"><span aria-hidden="true">●</span>{eyebrow}</p><h2>{title}</h2><p className="section-heading__copy">{copy}</p></div>;
}

function Metric({ label: metricLabel, value, detail }: { label: string; value: string; detail?: string }) {
  return <div className="metric"><p>{metricLabel}</p><strong>{value}</strong>{detail ? <span>{detail}</span> : null}</div>;
}

function Detail({ label: detailLabel, children }: { label: string; children: ReactNode }) {
  return <div className="detail-row"><dt>{detailLabel}</dt><dd>{children}</dd></div>;
}

function Empty({ children }: { children: ReactNode }) { return <div className="empty-state">{children}</div>; }

export default function DashboardApp() {
  const [data, setData] = useState<DashboardSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const [activeSection, setActiveSection] = useState("overview");
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let requestInFlight = false;

    const loadDashboard = async (showLoading: boolean) => {
      if (requestInFlight) return;
      requestInFlight = true;

      if (showLoading) setLoading(true);
      setError(null);

      try {
        const response = await fetch("/api/dashboard", {
          cache: "no-store",
          signal: controller.signal,
        });

        if (!response.ok) {
          const body = await response.json().catch(() => null) as { error?: string } | null;
          throw new Error(body?.error ?? `Dashboard request failed (${response.status}).`);
        }

        const snapshot = await response.json() as DashboardSnapshot;
        setData(snapshot);
      } catch (reason: unknown) {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setData(null);
        setError(reason instanceof Error ? reason.message : "Dashboard data could not be loaded.");
      } finally {
        requestInFlight = false;
        if (showLoading && !controller.signal.aborted) setLoading(false);
      }
    };

    void loadDashboard(true);
    const interval = window.setInterval(
      () => void loadDashboard(false),
      DASHBOARD_REFRESH_MS,
    );

    return () => {
      window.clearInterval(interval);
      controller.abort();
    };
  }, [refresh]);

  useEffect(() => {
    const observer = new IntersectionObserver((entries) => {
      const current = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (current?.target.id) setActiveSection(current.target.id);
    }, { rootMargin: "-20% 0px -62%", threshold: [0.1, 0.35, 0.6] });
    sections.forEach(({ id }) => { const node = document.getElementById(id); if (node) observer.observe(node); });
    return () => observer.disconnect();
  }, [data, loading, error]);

  useEffect(() => {
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") setPanelOpen(false); };
    document.addEventListener("keydown", escape);
    document.body.classList.toggle("is-overlay-open", panelOpen);
    return () => { document.removeEventListener("keydown", escape); document.body.classList.remove("is-overlay-open"); };
  }, [panelOpen]);

  const top = useCallback(() => window.scrollTo({ top: 0, behavior: "smooth" }), []);
  const isMining = data?.mining.active === true && data.mining.status === "mining";

  const runColumns = useMemo<readonly TableColumn<BenchmarkRun>[]>(() => [
    { key: "strategy", header: "Strategy", render: (run) => <strong>{run.strategy ?? "—"}</strong> },
    { key: "kind", header: "Kind", render: (run) => <span className="mono-muted">{run.run_kind ?? "—"}</span> },
    { key: "score", header: "Score", align: "right", render: (run) => number(run.total_score) },
    { key: "cost", header: "Cost", align: "right", render: (run) => cost(run.total_cost_usd) },
    { key: "p95", header: "p95", align: "right", render: (run) => ms(run.p95_runtime_ms) },
    { key: "errors", header: "Errors", align: "right", render: (run) => percent(run.error_rate) },
    { key: "time", header: "Run time", render: (run) => date(run.created_at) },
  ], []);

  const agentColumns = useMemo<readonly TableColumn<RuntimeMeasurement>[]>(() => [
    { key: "agent", header: "Agent", render: (item) => item.agent ?? "Unknown" },
    { key: "operation", header: "Operation", render: (item) => item.operation ?? "Unknown" },
    { key: "latency", header: "Latency", align: "right", render: (item) => ms(item.elapsed_ms) },
  ], []);

  return <div className="site-shell">
    <Header panelOpen={panelOpen} onTogglePanel={() => setPanelOpen((value) => !value)} onTop={top} isMining={isMining} />
    <SidePanel open={panelOpen} sections={sections} activeSection={activeSection} data={data} onClose={() => setPanelOpen(false)} />

    <div className="dashboard-column">
      <main className="dashboard-main">
        {loading ? <Loading /> : null}
        {!loading && error ? <section className="error-state" aria-live="polite"><p className="eyebrow"><span aria-hidden="true">●</span>Backend connection</p><h1>Miner data is unavailable.</h1><p>{error}</p><button className="primary-button" type="button" onClick={() => setRefresh((value) => value + 1)}>Retry</button></section> : null}

        {!loading && !error && data ? <>
          <section id="overview" className="dashboard-section dashboard-section--intro"><div className="section-content">
            <p className="eyebrow"><span aria-hidden="true">●</span>SN67 / Harnyx</p><h1>Miner observability, without the noise.</h1>
            <p className="intro-copy">Real artifact, benchmark, cost, latency, and dependency state from the Miner backend. This interface is read-only.</p>
            <div className="overview-strip">
              <Metric label="Active artifact" value={data.artifact?.profile ?? "None"} detail={data.artifact?.hash ? hash(data.artifact.hash) : "No artifact manifest available"} />
              <Metric label="Latest score" value={number(data.benchmark.latest?.total_score)} detail={data.benchmark.latest?.run_kind ?? "No benchmark results available yet"} />
              <Metric label="Champion comparison" value={data.benchmark.latest?.champion_selected === true ? "Selected" : data.benchmark.latest?.champion_selected === false ? "Not selected" : "Not available"} detail={available(data.benchmark.latest?.wins) ? `${data.benchmark.latest?.wins ?? 0}W / ${data.benchmark.latest?.losses ?? 0}L / ${data.benchmark.latest?.ties ?? 0}T` : undefined} />
              <Metric label="Backend" value={label(data.backend.status)} detail={`BenchmarkStore: ${label(data.backend.benchmark_store)}`} />
            </div>
            {data.backend.benchmark_store !== "available" ? <div className="inline-notice"><span className="status-dot" data-state={data.backend.benchmark_store} aria-hidden="true" /><p>{data.backend.message ?? "No benchmark results available yet."}</p></div> : null}
          </div></section>

          <section id="artifact" className="dashboard-section dashboard-section--surface"><div className="section-content">
            <Heading eyebrow="Artifact" title="What is currently being evaluated" copy="Identity and strategy state come from the latest Miner artifact manifest or, when absent, the latest persisted benchmark run." />
            {data.artifact ? <div className="two-column-grid">
              <dl className="detail-list"><Detail label="Profile"><strong>{data.artifact.profile ?? "Not available"}</strong></Detail><Detail label="Version">{data.artifact.version ?? "Not available"}</Detail><Detail label="SHA-256"><code className="hash-value">{data.artifact.hash ?? "Not available"}</code></Detail><Detail label="Size">{available(data.artifact.size_bytes) ? `${integer(data.artifact.size_bytes)} bytes` : "Not available"}</Detail><Detail label="Harnyx validation">{data.artifact.validated === null ? "Not recorded" : <Status value={data.artifact.validated ? "ready" : "unavailable"} text={data.artifact.validated ? "Validated" : "Not validated"} />}</Detail><Detail label="Built">{date(data.artifact.built_at)}</Detail></dl>
              <div className="component-state"><h3>Selective strategy</h3><p>Only components recorded by the artifact builder are shown.</p><div className="component-list">{data.artifact.enabled_components.length ? data.artifact.enabled_components.map((item) => <span className="component-chip" data-state="ready" key={item}>{item.replaceAll("_", " ")}</span>) : <span className="muted-copy">No enabled strategy components recorded.</span>}</div>{data.artifact.disabled_components.length ? <div className="component-disabled"><p>Disabled / ablated</p><div className="component-list">{data.artifact.disabled_components.map((item) => <span className="component-chip" data-state="empty" key={item}>{item.replaceAll("_", " ")}</span>)}</div></div> : null}</div>
            </div> : <Empty>No artifact metadata is available yet. Build an artifact before expecting profile or validation information.</Empty>}
            <ArtifactSubmission
              currentArtifact={data.artifact}
            />
          </div></section>

          <section id="slai" className="dashboard-section"><div className="section-content">
            <Heading eyebrow="SLAI integration" title="Measured capability, not symbolic imports" copy="Pinned dependencies are always visible; agents appear only when actual runtime-use evidence was persisted by Miner." />
            <div className="integration-grid">
              <div className="integration-card"><div className="integration-card__head"><h3>SLAI v2.3</h3><Status value={data.slai.status} /></div><dl className="detail-list detail-list--compact"><Detail label="Commit"><code>{hash(data.slai.commit)}</code></Detail><Detail label="Pin state"><Status value={data.slai.pinned ? "ready" : "unavailable"} text={data.slai.pinned ? "Pinned" : "Mismatch / unavailable"} /></Detail><Detail label="Runtime evidence">{data.slai.runtime_evidence === "recorded" ? "Recorded" : "Not recorded"}</Detail></dl></div>
              <div className="integration-card"><div className="integration-card__head"><h3>Harnyx</h3><Status value={data.harnyx.status} /></div><dl className="detail-list detail-list--compact"><Detail label="SDK">{data.harnyx.sdk_version || "Not available"}</Detail><Detail label="Commit"><code>{hash(data.harnyx.commit)}</code></Detail><Detail label="Pin state"><Status value={data.harnyx.pinned ? "ready" : "unavailable"} text={data.harnyx.pinned ? "Pinned" : "Mismatch / unavailable"} /></Detail></dl></div>
            </div>
            <div className="subsection"><div className="subsection__heading"><h3>Selected SLAI agents</h3><p>Only persisted runtime use is shown.</p></div>{data.slai.selected_agents.length ? <div className="component-list">{data.slai.selected_agents.map((agent) => <span className="component-chip" data-state="ready" key={agent}>{agent}</span>)}</div> : <Empty>No selected SLAI agents have been persisted for the latest run.</Empty>}</div>
            <div className="subsection"><div className="subsection__heading"><h3>Recorded SLAI agent latency</h3><p>Candidate agents are not presented as used agents.</p></div><Table columns={agentColumns} rows={data.slai.runtime_measurements} getRowKey={(row, index) => `${row.agent ?? "agent"}-${row.operation ?? "operation"}-${index}`} emptyMessage="No persisted SLAI agent invocation measurements are available yet." caption="Recorded SLAI agent invocation latency" /></div>
          </div></section>

          <section id="benchmark" className="dashboard-section dashboard-section--surface"><div className="section-content">
            <Heading eyebrow="Benchmark" title="Persisted Harnyx evidence" copy="Scores come from BenchmarkStore records generated from official Harnyx local-eval or local-benchmark reports." />
            {data.benchmark.latest ? <><div className="metric-grid"><Metric label="Total score" value={number(data.benchmark.latest.total_score)} /><Metric label="Comparison" value={number(data.benchmark.latest.comparison_score)} /><Metric label="Fast" value={number(data.benchmark.latest.fast_score)} /><Metric label="Normal" value={number(data.benchmark.latest.normal_score)} /><Metric label="Wins" value={integer(data.benchmark.latest.wins)} /><Metric label="Losses" value={integer(data.benchmark.latest.losses)} /><Metric label="Ties" value={integer(data.benchmark.latest.ties)} /><Metric label="Timestamp" value={date(data.benchmark.latest.created_at)} /></div><div className="subsection"><div className="subsection__heading"><h3>Recent runs</h3><p>Newest persisted experiments first.</p></div><Table columns={runColumns} rows={data.benchmark.recent} getRowKey={(run, index) => run.run_id ?? `${run.strategy ?? "run"}-${index}`} emptyMessage="No benchmark results available yet." caption="Recent Harnyx benchmark runs" /></div></> : <Empty>No benchmark results available yet. Run official Harnyx evaluation and persist the report through Miner.</Empty>}
          </div></section>

          <section id="performance" className="dashboard-section"><div className="section-content">
            <Heading eyebrow="Runtime / cost" title="Reward-relevant overhead" copy="Cost, usage, latency, timeouts, and failures are shown only when present in the latest persisted benchmark evidence." />
            {data.performance ? <><div className="metric-grid metric-grid--performance"><Metric label="Total cost" value={cost(data.performance.total_cost_usd)} /><Metric label="Tokens" value={integer(data.performance.token_usage)} /><Metric label="Tool calls" value={integer(data.performance.tool_calls)} /><Metric label="Median latency" value={ms(data.performance.median_runtime_ms)} /><Metric label="p95 latency" value={ms(data.performance.p95_runtime_ms)} /><Metric label="Timeout rate" value={percent(data.performance.timeout_rate)} /><Metric label="Error rate" value={percent(data.performance.error_rate)} /><Metric label="Citation failures" value={percent(data.performance.citation_failure_rate)} /><Metric label="Structured-output failures" value={percent(data.performance.structured_output_failure_rate)} /></div>{data.performance.provider_models.length ? <div className="provider-line"><span>Recorded provider usage</span><div className="component-list">{data.performance.provider_models.map((provider) => <code key={provider}>{provider}</code>)}</div></div> : null}</> : <Empty>No runtime or cost measurements are available until a benchmark run is persisted.</Empty>}
          </div></section>

          <section id="system" className="dashboard-section dashboard-section--surface"><div className="section-content">
            <Heading eyebrow="System / versions" title="Reproducibility context" copy="Pinned commits and benchmark data versions trace the dashboard state back to the Miner experiment that produced it." />
            <div className="two-column-grid"><dl className="detail-list"><Detail label="Miner commit"><code className="hash-value">{data.versions.miner_commit ?? "Not available"}</code></Detail><Detail label="SLAI commit"><code className="hash-value">{data.versions.slai_commit ?? "Not available"}</code></Detail><Detail label="Harnyx commit"><code className="hash-value">{data.versions.harnyx_commit ?? "Not available"}</code></Detail></dl><dl className="detail-list"><Detail label="Suite">{data.versions.suite_slug ?? "Not available"}</Detail><Detail label="Dataset version">{data.versions.dataset_version ?? "Not available"}</Detail><Detail label="Scoring version">{data.versions.scoring_version ?? "Not available"}</Detail><Detail label="Batch"><code className="hash-value">{data.versions.batch_id ?? data.versions.source_batch_id ?? "Not available"}</code></Detail></dl></div>
            <p className="snapshot-time">Dashboard snapshot generated {date(data.generated_at)}.</p>
          </div></section>
        </> : null}
      </main>
      <Footer isMining={isMining} />
    </div>
  </div>;
}
