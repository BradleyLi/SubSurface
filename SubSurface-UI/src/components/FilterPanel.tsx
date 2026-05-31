import type { FilterState, RiskLevel } from "../types/pipe";
import { RISK_COLORS } from "../constants/colors";

interface FilterPanelProps {
  filters: FilterState;
  materials: string[];
  wards: string[];
  pipeTypes: string[];
  riskLevels: RiskLevel[];
  onChange: (patch: Partial<FilterState>) => void;
  onReset: () => void;
  onCriticalOnly: () => void;
}

function toggleValue<T>(list: T[], value: T): T[] {
  return list.includes(value)
    ? list.filter((v) => v !== value)
    : [...list, value];
}

export default function FilterPanel({
  filters,
  materials,
  wards,
  pipeTypes,
  riskLevels,
  onChange,
  onReset,
  onCriticalOnly,
}: FilterPanelProps) {
  return (
    <div className="filter-panel">
      <div className="filter-header">
        <h3>Map Filters</h3>
        <div className="filter-actions">
          <button type="button" className="btn-ghost" onClick={onCriticalOnly}>
            Critical only
          </button>
          <button type="button" className="btn-ghost" onClick={onReset}>
            Reset
          </button>
        </div>
      </div>

      <label className="field-label">Risk Level</label>
      <div className="chip-group">
        {riskLevels.map((level) => (
          <button
            key={level}
            type="button"
            className={`chip ${filters.riskLevels.includes(level) ? "active" : ""}`}
            style={
              filters.riskLevels.includes(level)
                ? { borderColor: RISK_COLORS[level], color: RISK_COLORS[level] }
                : undefined
            }
            onClick={() =>
              onChange({
                riskLevels: toggleValue(filters.riskLevels, level),
              })
            }
          >
            {level}
          </button>
        ))}
      </div>

      <label className="field-label">Min Risk Score — {filters.minRiskScore}</label>
      <input
        type="range"
        min={0}
        max={100}
        value={filters.minRiskScore}
        onChange={(e) =>
          onChange({ minRiskScore: Number(e.target.value) })
        }
        className="range-input"
      />

      <label className="field-label">Material</label>
      <div className="chip-group chip-group-scroll">
        {materials.map((mat) => (
          <button
            key={mat}
            type="button"
            className={`chip ${filters.materials.includes(mat) ? "active" : ""}`}
            onClick={() =>
              onChange({ materials: toggleValue(filters.materials, mat) })
            }
          >
            {mat}
          </button>
        ))}
      </div>

      <label className="field-label">Ward</label>
      <div className="chip-group chip-group-scroll">
        {wards.map((ward) => (
          <button
            key={ward}
            type="button"
            className={`chip ${filters.wards.includes(ward) ? "active" : ""}`}
            onClick={() =>
              onChange({ wards: toggleValue(filters.wards, ward) })
            }
          >
            {ward}
          </button>
        ))}
      </div>

      {pipeTypes.length > 1 && (
        <>
          <label className="field-label">Pipe Type</label>
          <div className="chip-group">
            {pipeTypes.map((type) => (
              <button
                key={type}
                type="button"
                className={`chip ${filters.pipeTypes.includes(type) ? "active" : ""}`}
                onClick={() =>
                  onChange({ pipeTypes: toggleValue(filters.pipeTypes, type) })
                }
              >
                {type}
              </button>
            ))}
          </div>

          <label className="field-label">Color By</label>
          <div className="radio-group">
            <label>
              <input
                type="radio"
                name="colorMode"
                checked={filters.colorMode === "risk"}
                onChange={() => onChange({ colorMode: "risk" })}
              />
              Risk Level
            </label>
            <label>
              <input
                type="radio"
                name="colorMode"
                checked={filters.colorMode === "type"}
                onChange={() => onChange({ colorMode: "type" })}
              />
              Pipe Type
            </label>
          </div>
        </>
      )}
    </div>
  );
}
