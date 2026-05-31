import type { Pipe } from "../types/pipe";
import { formatCurrency, formatPercent, topShapFeature } from "../api/pipes";
import { CRITICAL_TABLE_LIMIT } from "../constants/colors";

interface CriticalTableProps {
  rows: Pipe[];
  selectedPipeId: string | null;
  onSelect: (pipe: Pipe) => void;
  totalCritical: number;
}

function riskClass(level: string): string {
  return `risk-badge risk-${level.toLowerCase()}`;
}

export default function CriticalTable({
  rows,
  selectedPipeId,
  onSelect,
  totalCritical,
}: CriticalTableProps) {
  return (
    <div className="critical-table-wrap">
      <div className="table-header">
        <h3>Critical Priority Queue</h3>
        <span className="table-meta">
          Top {Math.min(rows.length, CRITICAL_TABLE_LIMIT)} of {totalCritical.toLocaleString()}
        </span>
      </div>

      <div className="table-scroll">
        <table className="critical-table">
          <thead>
            <tr>
              <th>Pipe</th>
              <th>Risk</th>
              <th>Prob</th>
              <th>Ward</th>
              <th>Material</th>
              <th>Age</th>
              <th>Driver</th>
              <th>Emergency</th>
              <th>Savings</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={9} className="empty-row">
                  No critical pipes match current filters.
                </td>
              </tr>
            ) : (
              rows.map((pipe) => (
                <tr
                  key={pipe.pipe_id}
                  className={selectedPipeId === pipe.pipe_id ? "selected" : ""}
                  onClick={() => onSelect(pipe)}
                >
                  <td className="mono">{pipe.pipe_id.replace("WM-", "")}</td>
                  <td>
                    <span className={riskClass(pipe.risk_level)}>
                      {pipe.risk_level}
                    </span>
                  </td>
                  <td className="mono">{formatPercent(pipe.predicted_break_probability)}</td>
                  <td>{pipe.ward}</td>
                  <td>{pipe.material}</td>
                  <td className="mono">{pipe.age}y</td>
                  <td className="driver">{topShapFeature(pipe)}</td>
                  <td className="mono">{formatCurrency(pipe.emergency_cost)}</td>
                  <td className="mono savings">{formatCurrency(pipe.expected_savings)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
