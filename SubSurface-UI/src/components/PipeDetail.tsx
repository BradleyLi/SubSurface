import type { Pipe } from "../types/pipe";
import { formatCurrency, formatPercent, topShapFeature } from "../api/pipes";

interface PipeDetailProps {
  pipe: Pipe | null;
  onClose: () => void;
}

function riskClass(level: string): string {
  return `risk-badge risk-${level.toLowerCase()}`;
}

export default function PipeDetail({ pipe, onClose }: PipeDetailProps) {
  if (!pipe) return null;

  return (
    <div className="pipe-detail">
      <div className="pipe-detail-header">
        <div>
          <span className="detail-label">Selected Segment</span>
          <h4>{pipe.pipe_id}</h4>
        </div>
        <button type="button" className="btn-close" onClick={onClose} aria-label="Close">
          ×
        </button>
      </div>

      <div className="detail-grid">
        <div>
          <span className="detail-stat-label">Risk</span>
          <span className={riskClass(pipe.risk_level)}>{pipe.risk_level}</span>
        </div>
        <div>
          <span className="detail-stat-label">Break Prob</span>
          <strong>{formatPercent(pipe.predicted_break_probability)}</strong>
        </div>
        <div>
          <span className="detail-stat-label">Percentile</span>
          <strong>{pipe.risk_percentile.toFixed(1)}</strong>
        </div>
        <div>
          <span className="detail-stat-label">Type</span>
          <strong>{pipe.pipe_type}</strong>
        </div>
        <div>
          <span className="detail-stat-label">Ward</span>
          <strong>{pipe.ward}</strong>
        </div>
        <div>
          <span className="detail-stat-label">Material</span>
          <strong>{pipe.material}</strong>
        </div>
        <div>
          <span className="detail-stat-label">Age</span>
          <strong>{pipe.age} yrs</strong>
        </div>
        <div>
          <span className="detail-stat-label">Diameter</span>
          <strong>{pipe.diameter_mm} mm</strong>
        </div>
      </div>

      {pipe.street && (
        <p className="detail-street">{pipe.street}</p>
      )}

      <div className="detail-costs">
        <div>
          <span>Emergency</span>
          <strong>{formatCurrency(pipe.emergency_cost)}</strong>
        </div>
        <div>
          <span>Replacement</span>
          <strong>{formatCurrency(pipe.replacement_cost)}</strong>
        </div>
        <div>
          <span>Est. Savings</span>
          <strong className="savings">{formatCurrency(pipe.expected_savings)}</strong>
        </div>
      </div>

      <p className="detail-driver">
        Top risk driver: <strong>{topShapFeature(pipe)}</strong>
      </p>
    </div>
  );
}
