import { useCallback, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import type { Pipe } from "../types/pipe";
import type { AnalysisRunResponse, AnalysisRunState } from "../types/analysisRun";
import type { VoiceMatchResponse } from "../types/voice";
import {
  createAnalysisRun,
  fetchWorkflow2Health,
} from "../api/analysisRuns";
import type { Workflow2Health } from "../types/analysisRun";

interface MultiRoleAnalysisProps {
  pipe: Pipe | null;
  useReal?: boolean;
  voiceMatch: VoiceMatchResponse | null;
  useMatchedVoicePipe: boolean;
}

type TabKey = "engineer" | "police" | "field" | "operations" | "final";

const TAB_LABELS: { key: TabKey; label: string; roleKey?: string }[] = [
  { key: "engineer", label: "Engineer", roleKey: "engineer" },
  { key: "police", label: "Police", roleKey: "police" },
  { key: "field", label: "Field", roleKey: "field" },
  { key: "operations", label: "Operations", roleKey: "operations" },
  { key: "final", label: "Final plan" },
];

function formatCurrency(value: number, currency = "CAD"): string {
  return new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(value);
}

function BomTable({ data }: { data: AnalysisRunResponse }) {
  const bom = data.bill_of_materials;
  if (!bom?.line_items?.length) return null;

  return (
    <div className="w2-bom">
      <h4>Bill of Materials and supplier awards</h4>
      <div className="w2-table-wrap">
        <table className="w2-table">
          <thead>
            <tr>
              <th>Item</th>
              <th>Qty</th>
              <th>Unit</th>
              <th>Supplier</th>
              <th>Unit $</th>
              <th>Line $</th>
            </tr>
          </thead>
          <tbody>
            {bom.line_items.map((line) => (
              <tr key={line.line_id}>
                <td>{line.description}</td>
                <td>{line.qty}</td>
                <td>{line.unit}</td>
                <td>{line.chosen_supplier_name ?? "—"}</td>
                <td>{line.unit_price != null ? formatCurrency(line.unit_price) : "—"}</td>
                <td>{formatCurrency(line.line_total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="w2-bom-total">
        Estimated total with contingency/tax:{" "}
        {formatCurrency(bom.total_estimate, bom.currency)}
      </p>
    </div>
  );
}

function AwardsTable({ data }: { data: AnalysisRunResponse }) {
  const awards = data.bill_of_materials?.contract_awards ?? [];
  if (!awards.length) return null;

  return (
    <div className="w2-awards">
      <h4>Recommended supplier contract awards</h4>
      <div className="w2-table-wrap">
        <table className="w2-table">
          <thead>
            <tr>
              <th>Supplier</th>
              <th>Type</th>
              <th>Scope</th>
              <th>Award $</th>
              <th>Approval</th>
            </tr>
          </thead>
          <tbody>
            {awards.map((award) => (
              <tr key={`${award.supplier_id}-${award.scope}`}>
                <td>{award.supplier_name}</td>
                <td>{award.supplier_type}</td>
                <td>{award.scope}</td>
                <td>{formatCurrency(award.award_subtotal)}</td>
                <td>
                  {award.requires_human_approval ? "Required" : "Not flagged"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function MultiRoleAnalysis({
  pipe,
  useReal = true,
  voiceMatch,
  useMatchedVoicePipe,
}: MultiRoleAnalysisProps) {
  const [health, setHealth] = useState<Workflow2Health | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>("engineer");
  const [state, setState] = useState<AnalysisRunState>({ status: "idle" });
  const [cachedRuns, setCachedRuns] = useState<
    Record<string, AnalysisRunResponse>
  >({});

  const matchedPipeId = voiceMatch?.match?.pipe_id ?? null;
  const effectivePipeId =
    useMatchedVoicePipe && matchedPipeId
      ? matchedPipeId
      : pipe?.pipe_id ?? null;

  useEffect(() => {
    fetchWorkflow2Health()
      .then(setHealth)
      .catch(() =>
        setHealth({
          profile: "workflow2",
          ok: false,
          model: "",
          base_url: "",
          detail: "Health check failed",
        }),
      );
  }, []);

  useEffect(() => {
    if (!effectivePipeId) {
      setState({ status: "idle" });
      return;
    }
    const cached = cachedRuns[effectivePipeId];
    if (cached) {
      setState({ status: "ready", pipeId: effectivePipeId, data: cached });
    } else {
      setState({ status: "idle" });
    }
  }, [effectivePipeId, cachedRuns]);

  const runAnalysis = useCallback(async () => {
    if (!effectivePipeId) return;

    setState({ status: "loading", pipeId: effectivePipeId });
    try {
      const data = await createAnalysisRun({
        pipe_id: effectivePipeId,
        use_real: useReal,
        use_latest_voice_transcript: true,
      });
      setCachedRuns((prev) => ({ ...prev, [effectivePipeId]: data }));
      setState({ status: "ready", pipeId: effectivePipeId, data });
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Workflow 2 analysis failed.";
      setState({ status: "error", pipeId: effectivePipeId, message });
    }
  }, [effectivePipeId, useReal]);

  const w2Ok = health?.ok ?? false;

  if (!pipe && !matchedPipeId) {
    return (
      <section className="w2-panel w2-panel-empty" aria-label="Multi-role analysis">
        <header className="w2-panel-header">
          <div>
            <span className="w2-panel-label">Workflow 2</span>
            <h3>Multi-Role Analysis</h3>
          </div>
          <span className="w2-panel-status idle">Standby</span>
        </header>
        <p className="w2-panel-placeholder">
          Select a pipe segment or receive a voice caller report to run Nemotron
          Super multi-role analysis.
        </p>
      </section>
    );
  }

  const isStale =
    state.status !== "idle" &&
    state.status !== "loading" &&
    state.pipeId !== effectivePipeId;

  const result =
    state.status === "ready" && !isStale ? state.data : null;
  const rolesByName = Object.fromEntries(
    (result?.roles ?? []).map((r) => [r.role, r]),
  );

  return (
    <section className="w2-panel" aria-label="Multi-role analysis">
      <header className="w2-panel-header">
        <div>
          <span className="w2-panel-label">Workflow 2 · Nemotron Super</span>
          <h3>Multi-Role Analysis</h3>
        </div>
        {state.status === "loading" && !isStale && (
          <span className="w2-panel-status loading">
            <span className="summary-agent-dot" aria-hidden="true" />
            Running
          </span>
        )}
      </header>

      {!w2Ok && health && (
        <p className="w2-health-warn" role="alert">
          Workflow 2 unavailable: {health.detail || "check Ollama :11434"}
        </p>
      )}

      {effectivePipeId && (
        <p className="w2-target-pipe">
          Target pipe: <code>{effectivePipeId}</code>
          {useMatchedVoicePipe && matchedPipeId === effectivePipeId && (
            <span className="w2-voice-badge">from voice match</span>
          )}
        </p>
      )}

      <button
        type="button"
        className="w2-run-button"
        disabled={!w2Ok || !effectivePipeId || state.status === "loading"}
        onClick={() => void runAnalysis()}
      >
        Run multi-role analysis (Super)
      </button>

      {state.status === "loading" && !isStale && (
        <div className="w2-loading">
          <p>
            Running transcript orchestrator, Engineer, Police, Field, Operations,
            and synthesis on Super for {effectivePipeId}…
          </p>
          <small>This may take several minutes when Ollama is running locally.</small>
        </div>
      )}

      {state.status === "error" && !isStale && (
        <div className="summary-agent-error" role="alert">
          {state.message}
        </div>
      )}

      {result && (
        <div className="w2-results">
          <p className="w2-run-meta">
            Run <code>{result.run_id}</code> · source: {result.source} · model:{" "}
            {result.models.workflow2 ?? "super"}
          </p>

          <div className="w2-tabs" role="tablist">
            {TAB_LABELS.map(({ key, label }) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={activeTab === key}
                className={`w2-tab${activeTab === key ? " active" : ""}`}
                onClick={() => setActiveTab(key)}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="w2-tab-panel" role="tabpanel">
            {activeTab !== "final" ? (
              <>
                {(() => {
                  const roleKey = TAB_LABELS.find((t) => t.key === activeTab)
                    ?.roleKey;
                  const report = roleKey ? rolesByName[roleKey] : undefined;
                  return (
                    <>
                      <p className="w2-role-source">
                        {activeTab.charAt(0).toUpperCase() + activeTab.slice(1)} ·{" "}
                        {report?.source ?? "unknown"}
                      </p>
                      <div className="w2-markdown">
                        <ReactMarkdown>
                          {report?.markdown || "_No content_"}
                        </ReactMarkdown>
                      </div>
                      {activeTab === "operations" && (
                        <>
                          <BomTable data={result} />
                          <AwardsTable data={result} />
                        </>
                      )}
                    </>
                  );
                })()}
              </>
            ) : (
              <>
                <div className="w2-markdown">
                  <ReactMarkdown>{result.final_markdown}</ReactMarkdown>
                </div>
                <AwardsTable data={result} />
                <details className="w2-action-plan">
                  <summary>Action plan (JSON)</summary>
                  <pre>{JSON.stringify(result.action_plan, null, 2)}</pre>
                </details>
              </>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
