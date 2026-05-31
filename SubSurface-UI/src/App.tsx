import { useState } from "react";
import type { Pipe } from "./types/pipe";
import { usePipes } from "./hooks/usePipes";
import Map3D from "./components/Map3D";
import FilterPanel from "./components/FilterPanel";
import CriticalTable from "./components/CriticalTable";
import PipeDetail from "./components/PipeDetail";
import KpiBar from "./components/KpiBar";

export default function App() {
  const {
    loading,
    error,
    source,
    filters,
    updateFilters,
    resetFilters,
    showCriticalOnly,
    filteredPipes,
    criticalTableRows,
    stats,
    materials,
    wards,
    pipeTypes,
    riskLevels,
  } = usePipes();

  const [selectedPipe, setSelectedPipe] = useState<Pipe | null>(null);

  const handleSelectPipe = (pipe: Pipe | null) => {
    setSelectedPipe(pipe);
  };

  return (
    <div className="app">
      <Map3D
        pipes={filteredPipes}
        colorMode={filters.colorMode}
        selectedPipe={selectedPipe}
        onSelectPipe={handleSelectPipe}
      />

      <aside className="sidebar">
        <header className="sidebar-header">
          <div>
            <h1>
              City<span>Nerve</span>
            </h1>
            <p>Toronto Watermain Risk · 3D Map</p>
          </div>
        </header>

        {loading && (
          <div className="status-banner loading">
            Loading pipe network from CityNerve API…
          </div>
        )}

        {error && (
          <div className="status-banner error">
            <strong>API unavailable.</strong> Start the SubSurface backend:{" "}
            <code>./scripts/run_citynerve.sh</code> or{" "}
            <code>uvicorn backend.main:app --port 8000</code>
            <br />
            <small>{error}</small>
          </div>
        )}

        {!loading && !error && (
          <>
            <KpiBar
              segmentsShown={stats.total}
              critical={stats.critical}
              high={stats.high}
              avgRisk={stats.avgRisk}
              networkTotal={stats.networkTotal}
              networkCritical={stats.networkCritical}
              source={source}
            />

            <FilterPanel
              filters={filters}
              materials={materials}
              wards={wards}
              pipeTypes={pipeTypes}
              riskLevels={riskLevels}
              onChange={updateFilters}
              onReset={resetFilters}
              onCriticalOnly={showCriticalOnly}
            />

            <PipeDetail
              pipe={selectedPipe}
              onClose={() => setSelectedPipe(null)}
            />

            <CriticalTable
              rows={criticalTableRows}
              selectedPipeId={selectedPipe?.pipe_id ?? null}
              onSelect={handleSelectPipe}
              totalCritical={stats.critical}
            />
          </>
        )}
      </aside>
    </div>
  );
}
