interface KpiBarProps {
  segmentsShown: number;
  critical: number;
  high: number;
  avgRisk: number;
  networkTotal: number;
  networkCritical: number;
  source: string;
}

export default function KpiBar({
  segmentsShown,
  critical,
  high,
  avgRisk,
  networkTotal,
  networkCritical,
  source,
}: KpiBarProps) {
  return (
    <div className="kpi-bar">
      <div className="kpi-item">
        <span className="kpi-value">{segmentsShown.toLocaleString()}</span>
        <span className="kpi-label">On Map</span>
      </div>
      <div className="kpi-item kpi-critical">
        <span className="kpi-value">{critical.toLocaleString()}</span>
        <span className="kpi-label">Critical</span>
      </div>
      <div className="kpi-item kpi-high">
        <span className="kpi-value">{high.toLocaleString()}</span>
        <span className="kpi-label">High</span>
      </div>
      <div className="kpi-item">
        <span className="kpi-value">{avgRisk.toFixed(1)}</span>
        <span className="kpi-label">Avg Risk</span>
      </div>
      <div className="kpi-item kpi-muted">
        <span className="kpi-value">{networkCritical.toLocaleString()}</span>
        <span className="kpi-label">Network Critical / {networkTotal.toLocaleString()}</span>
      </div>
      <div className="kpi-source">{source.replace(/_/g, " ")}</div>
    </div>
  );
}
