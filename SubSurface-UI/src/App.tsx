import { useEffect, useState } from "react";
import type { Pipe } from "./types/pipe";
import { usePipes } from "./hooks/usePipes";
import { useVoiceMatch } from "./hooks/useVoiceMatch";
import Map3D from "./components/Map3D";
import FilterPanel from "./components/FilterPanel";
import CriticalTable from "./components/CriticalTable";
import PipeDetail from "./components/PipeDetail";
import SummaryAgent from "./components/SummaryAgent";
import MultiRoleAnalysis from "./components/MultiRoleAnalysis";
import CallerReportAlert from "./components/CallerReportAlert";
import KpiBar from "./components/KpiBar";

export default function App() {
  const {
    loading,
    error,
    source,
    pipes,
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

  const { voiceMatch, showActiveReport } = useVoiceMatch(pipes, true);
  const activeVoiceMatch = showActiveReport ? voiceMatch : null;
  const [selectedPipe, setSelectedPipe] = useState<Pipe | null>(null);
  const [useMatchedVoicePipe, setUseMatchedVoicePipe] = useState(true);

  const handleSelectPipe = (pipe: Pipe | null) => {
    setSelectedPipe(pipe);
  };

  // Auto-select matched voice pipe when a live caller report arrives
  useEffect(() => {
    if (!showActiveReport) return;
    const match = voiceMatch?.match;
    if (!match || !useMatchedVoicePipe) return;

    const matched = pipes.find((p) => p.pipe_id === match.pipe_id);
    if (matched) {
      setSelectedPipe(matched);
    }
  }, [
    showActiveReport,
    voiceMatch?.match?.pipe_id,
    useMatchedVoicePipe,
    pipes,
    voiceMatch?.match,
  ]);

  return (
    <div className="app">
      <Map3D
        pipes={filteredPipes}
        colorMode={filters.colorMode}
        selectedPipe={selectedPipe}
        onSelectPipe={handleSelectPipe}
        voiceMatch={activeVoiceMatch?.match ?? null}
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

        <div className="sidebar-scroll">
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

              <CallerReportAlert
                voiceMatch={activeVoiceMatch}
                selectedPipeId={selectedPipe?.pipe_id ?? null}
                useMatchedPipe={useMatchedVoicePipe}
                onUseMatchedPipeChange={setUseMatchedVoicePipe}
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

              <SummaryAgent pipe={selectedPipe} useReal />

              <MultiRoleAnalysis
                pipe={selectedPipe}
                useReal
                voiceMatch={activeVoiceMatch}
                useMatchedVoicePipe={useMatchedVoicePipe}
              />

              <CriticalTable
                rows={criticalTableRows}
                selectedPipeId={selectedPipe?.pipe_id ?? null}
                onSelect={handleSelectPipe}
                totalCritical={stats.critical}
              />
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
