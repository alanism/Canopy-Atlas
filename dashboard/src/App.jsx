import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

const SUMMARY_ENDPOINT = "/v0/dashboard-summary?window=1h";
const METHODOLOGY_ENDPOINT = "/v0/methodology";
const FALLBACK_TITLE = "CANOPY ATLAS / EVIDENCE CONSOLE";
const TEST_PRICE = "$0.05 test price";

const emptyPayload = {
  meta: {
    dashboard_title: FALLBACK_TITLE,
    x402_signal_status: "unavailable",
    x402_signal_detected: false,
    data_quality_status: "unknown",
    labeled_volume_pct: 0,
    long_tail_volume_pct: 0,
    runtime_warning: "No cached benchmark payload is available yet.",
    freshness_tier: "benchmark",
    suitable_for_runtime_routing: false
  },
  data: {
    panels: {
      observed_effective_cost_leaderboard: [],
      volume_weighted_route_share: [],
      observed_settlement_health_x_cost: [],
      under_review_routes: []
    }
  }
};

export function DashboardApp() {
  const [payload, setPayload] = useState(emptyPayload);
  const [state, setState] = useState("loading");
  const [toast, setToast] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetch(SUMMARY_ENDPOINT)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`dashboard summary unavailable: ${response.status}`);
        }
        return response.json();
      })
      .then((json) => {
        if (!cancelled) {
          setPayload(json);
          setState("available");
        }
      })
      .catch(() => {
        if (!cancelled) {
          setPayload(emptyPayload);
          setState("failed");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const meta = payload.meta || emptyPayload.meta;
  const panels = payload.data?.panels || emptyPayload.data.panels;
  const leaderboard = panels.observed_effective_cost_leaderboard || [];
  const routeShare = panels.volume_weighted_route_share || [];
  const healthRows = panels.observed_settlement_health_x_cost || [];
  const underReview = panels.under_review_routes || [];
  const routingDisabled = meta.suitable_for_runtime_routing === false;
  const hasSettlementHealth = healthRows.some((row) => row.observed_settlement_rate !== undefined && row.observed_settlement_rate !== null);

  function archiveSnapshot() {
    try {
      const archive = {
        archived_at: new Date().toISOString(),
        source: SUMMARY_ENDPOINT,
        payload
      };
      window.localStorage.setItem("canopy_atlas_latest_snapshot", JSON.stringify(archive));
      setToast("Snapshot archived.");
    } catch {
      setToast("Snapshot failed. Retry is safe.");
    }
  }

  return (
    <main className="console-shell" data-state={state}>
      <CommandBar state={state} routingDisabled={routingDisabled} onArchive={archiveSnapshot} />
      {toast ? <div className="toast" role="status">{toast}</div> : null}

      <section className="console-grid" aria-label="Canopy Atlas evidence console">
        <aside className="left-rail" aria-label="Current snapshot">
          <CurrentSnapshot meta={meta} state={state} routingDisabled={routingDisabled} />
        </aside>

        <section className="evidence-field" aria-label="Route evidence">
          <PanelHeader
            eyebrow="ROUTE EVIDENCE"
            title="ROUTE HEALTH × COST"
            subtitle="Cost, share, and settlement health for observed routes."
          />
          <p className="section-explainer">Lower cost is useful only when settlement health and quality hold.</p>
          {state === "loading" ? <StateNotice title="Loading evidence packet" body="Reading the summary endpoint." /> : null}
          {state === "failed" ? (
            <StateNotice
              title="API unreachable"
              body="Start the API with CANOPY_BOOTSTRAP_EMPTY_CACHE=1 python3 -m api.server, or set CANOPY_DASHBOARD_API_BASE_URL for the dashboard proxy."
              tone="exception"
            />
          ) : null}
          <StateNotice title="Preview bootstrap window." body="Freshness expanding." />
          <HealthCost rows={hasSettlementHealth ? healthRows : leaderboard} hasSettlementHealth={hasSettlementHealth} />
          <ObservedRoutes rows={leaderboard} />
          <RouteShare rows={routeShare} />
        </section>

        <aside className="right-rail" aria-label="Evidence feeds and under review">
          <EvidenceFeeds meta={meta} />
          <UnderReview rows={underReview} />
        </aside>
      </section>

      <section className="methodology-console" id="methodology" aria-label="Methodology">
        <PanelHeader
          eyebrow="METHODOLOGY"
          title="METHODOLOGY"
          subtitle="What the snapshot checks before presenting route evidence."
        />
        <p>
          Benchmark-grade evidence only.
          <br />
          Runtime routing disabled.
        </p>
        <div className="methodology-grid" aria-label="Checks">
          <MethodQuestion index="01" text="Observed routes" />
          <MethodQuestion index="02" text="Freshness" />
          <MethodQuestion index="03" text="Validation" />
          <MethodQuestion index="04" text="Exceptions" />
        </div>
        <FeedRow label="CURRENT MODE" value={formatMode(meta.data_quality_status)} />
      </section>

      <section className="agent-strip" aria-label="Archive snapshot">
        <PanelHeader
          eyebrow="ARCHIVE SNAPSHOT"
          title="ARCHIVE SNAPSHOT"
          subtitle="Capture the current dashboard state for audit or review."
        />
        <button type="button" className="archive-button archive-large" title="Capture current evidence view." onClick={archiveSnapshot}>
          ARCHIVE SNAPSHOT
        </button>
      </section>
    </main>
  );
}

function CommandBar({ state, routingDisabled, onArchive }) {
  return (
    <header className="command-bar">
      <div className="brand-block">
        <span>CANOPY ATLAS</span>
        <strong>EVIDENCE CONSOLE</strong>
        <p>Observed route evidence from the latest benchmark window.</p>
      </div>
      <div className="status-chips" aria-label="Console status">
        <StatusChip label="BENCHMARK-GRADE" />
        <StatusChip label={routingDisabled ? "ROUTING_DISABLED" : "ROUTING_UNKNOWN"} tone={routingDisabled ? "live" : "exception"} />
        <StatusChip label="CACHE_1H" />
        <StatusChip label="X402_ACCESS" />
        <StatusChip label={state === "available" ? "AVAILABLE" : state.toUpperCase()} tone={state === "failed" ? "exception" : "live"} />
      </div>
      <nav className="command-actions" aria-label="Evidence actions">
        <a href={SUMMARY_ENDPOINT}>API</a>
        <a href={METHODOLOGY_ENDPOINT}>METHODOLOGY</a>
        <button type="button" className="archive-button" title="Capture current evidence view." onClick={onArchive}>ARCHIVE SNAPSHOT</button>
        <a href={SUMMARY_ENDPOINT}>VIEW JSON</a>
      </nav>
    </header>
  );
}

function CurrentSnapshot({ meta, state, routingDisabled }) {
  return (
    <Panel className="snapshot-panel">
      <PanelHeader
        eyebrow="CURRENT SNAPSHOT"
        title="CURRENT SNAPSHOT"
        subtitle="When this evidence was built, validated, and made available."
      />
      <IdentityRow label="SNAPSHOT TIME" value={formatDate(meta.cache_generation_timestamp)} />
      <IdentityRow label="QUALITY" value={formatValue(meta.data_quality_status)} />
      <IdentityRow label="ROUTING" value={routingDisabled ? "disabled" : "unknown"} />
      <IdentityRow label="ACCESS" value="x402" />
      <IdentityRow label="PRICE" value={TEST_PRICE} />
      <IdentityRow label="ALLOWED" value="archive snapshot" />
      <IdentityRow label="BLOCKED" value="runtime routing" />
      <IdentityRow label="STATE" value={state === "available" ? "available" : state} />
    </Panel>
  );
}

function EvidenceFeeds({ meta }) {
  return (
    <Panel className="feed-panel">
      <PanelHeader
        eyebrow="EVIDENCE FEEDS"
        title="EVIDENCE FEEDS"
        subtitle="Source freshness and validation state for this snapshot."
      />
      <FeedRow label="SUMMARY ENDPOINT" value="available" />
      <FeedRow label="CACHE REFRESH" value={formatDate(meta.cache_generation_timestamp)} />
      <FeedRow label="METRICS BUILD" value={formatDate(meta.metrics_timestamp)} />
      <FeedRow label="VALIDATION" value={formatValue(meta.data_quality_status)} />
      <FeedRow label="RUNTIME POLICY" value="disabled" />
    </Panel>
  );
}

function UnderReview({ rows = [] }) {
  return (
    <Panel className="under-review-panel">
      <PanelHeader
        eyebrow="UNDER REVIEW"
        title="UNDER REVIEW"
        subtitle="Observed activity that is not yet fully labeled or validated."
      />
      {rows.length ? rows.map((row, index) => <UnderReviewRoute key={row.route_id || index} row={row} />) : <p className="empty-copy">No under-review routes.</p>}
      <footer className="panel-footer">
        Visible != verified.
        <br />
        Coverage and labeling incomplete.
      </footer>
    </Panel>
  );
}

function HealthCost({ rows = [], hasSettlementHealth }) {
  if (!rows.length) {
    return <StateNotice title="Empty evidence field" body="No observed route rows are available in the current payload." />;
  }
  return (
    <div className="chart-panel">
      <ResponsiveContainer width="100%" height={310}>
        <ScatterChart margin={{ top: 12, right: 18, bottom: 24, left: 8 }}>
          <CartesianGrid stroke="var(--chart-grid)" />
          <XAxis dataKey="observed_cost_pct" name="observed cost" tickFormatter={percentLabel} stroke="var(--surface-ink-soft)" />
          <YAxis dataKey="observed_settlement_rate" name="settlement health" tickFormatter={percentLabel} stroke="var(--surface-ink-soft)" domain={[0.9, 1]} />
          <Tooltip formatter={(value) => percentLabel(value)} labelFormatter={formatValue} contentStyle={{ background: "var(--surface-raised)", border: "1px solid var(--hairline-strong)", color: "var(--surface-ink)" }} />
          <Scatter data={rows} fill="var(--signal-live)" />
        </ScatterChart>
      </ResponsiveContainer>
      {!hasSettlementHealth ? <p className="chart-note">Settlement health unavailable in current summary payload.</p> : null}
    </div>
  );
}

function ObservedRoutes({ rows = [] }) {
  return (
    <Panel className="leaderboard-panel">
      <PanelHeader
        eyebrow="OBSERVED ROUTES"
        title="OBSERVED ROUTES"
        subtitle="Routes ranked by observed effective cost."
      />
      {rows.length ? rows.map((row, index) => <RouteEvidenceCard key={row.route_id || index} row={row} />) : <p className="empty-copy">No cached route rows yet.</p>}
    </Panel>
  );
}

function RouteShare({ rows = [] }) {
  return (
    <Panel className="share-panel">
      <PanelHeader
        eyebrow="ROUTE SHARE"
        title="ROUTE SHARE"
        subtitle="Volume-weighted share of observed route activity."
      />
      {rows.length ? <RouteShareBars rows={rows} /> : <p className="empty-copy">No route-share data yet.</p>}
    </Panel>
  );
}

function RouteEvidenceCard({ row }) {
  return (
    <article className="route-card">
      <span className="route-id">{formatValue(row.route_id)}</span>
      <dl>
        <Metric label="OBSERVED COST" value={percentLabel(row.observed_cost_pct)} />
        <Metric label="ROUTE SHARE" value={percentLabel(row.route_share_pct)} />
        <Metric label="SETTLEMENT HEALTH" value={percentLabel(row.observed_settlement_rate)} />
        <Metric label="QUALITY" value={formatValue(row.data_quality_status)} />
      </dl>
    </article>
  );
}

function RouteShareBars({ rows = [] }) {
  return (
    <>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
          <CartesianGrid stroke="var(--chart-grid)" horizontal={false} />
          <XAxis type="number" tickFormatter={percentLabel} stroke="var(--surface-ink-soft)" />
          <YAxis type="category" dataKey="route_id" width={0} hide />
          <Tooltip formatter={(value) => percentLabel(value)} labelFormatter={formatValue} contentStyle={{ background: "var(--surface-raised)", border: "1px solid var(--hairline-strong)", color: "var(--surface-ink)" }} />
          <Bar dataKey="route_share_pct" fill="var(--signal-live)" radius={[0, 2, 2, 0]} />
        </BarChart>
      </ResponsiveContainer>
      <div className="share-list">
        {rows.map((row, index) => <RouteMini key={row.route_id || index} row={row} />)}
      </div>
    </>
  );
}

function RouteMini({ row }) {
  return (
    <div className="route-mini">
      <span className="route-id">{formatValue(row.route_id)}</span>
      <span>{percentLabel(row.route_share_pct)}</span>
      <span>{percentLabel(row.observed_cost_pct)}</span>
      <span>{formatValue(row.data_quality_status)}</span>
    </div>
  );
}

function UnderReviewRoute({ row }) {
  return (
    <div className="under-review-route">
      <FeedRow label="ROUTE" value={formatValue(row.route_id)} />
      <FeedRow label="SHARE" value={percentLabel(row.route_share_pct)} />
      <FeedRow label="OBSERVED COST" value={percentLabel(row.observed_cost_pct)} />
      <FeedRow label="QUALITY" value={formatValue(row.data_quality_status)} />
    </div>
  );
}

function Panel({ className = "", children }) {
  return <section className={`console-panel ${className}`}>{children}</section>;
}

function PanelHeader({ eyebrow, title, subtitle }) {
  return (
    <header className="panel-header">
      {eyebrow ? <span className="mono-label">{eyebrow}</span> : null}
      <h2>{title}</h2>
      {subtitle ? <p>{subtitle}</p> : null}
    </header>
  );
}

function IdentityRow({ label, value }) {
  return (
    <div className="identity-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function FeedRow({ label, value }) {
  return (
    <div className="feed-row">
      <span>{label}</span>
      <strong>{formatValue(value)}</strong>
    </div>
  );
}

function Metric({ label, value }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function MethodQuestion({ index, text }) {
  return (
    <div className="method-question">
      <span>{index}</span>
      <strong>{text}</strong>
    </div>
  );
}

function StatusChip({ label, tone = "live" }) {
  return <span className={`status-chip ${tone}`}>{formatValue(label)}</span>;
}

function StateNotice({ title, body, tone = "live" }) {
  return (
    <div className={`state-notice ${tone}`}>
      <strong>{title}</strong>
      <span>{body}</span>
    </div>
  );
}

function percentLabel(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "\u2014";
  }
  return `${(Number(value) * 100).toFixed(2)}%`;
}

function formatDate(value) {
  if (!value) {
    return "\u2014";
  }
  return String(value);
}

function formatValue(value) {
  if (value === null || value === undefined || value === "" || Number.isNaN(value)) {
    return "\u2014";
  }
  return String(value);
}

function formatMode(value) {
  return formatValue(value).replaceAll("_", " ");
}
