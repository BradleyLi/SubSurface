import { useEffect, useState } from "react";
import type { Pipe } from "../types/pipe";
import type { RiskSummaryResponse, RiskSummaryState } from "../types/riskSummary";
import { fetchRiskSummary } from "../api/riskSummary";

interface SummaryAgentProps {
  pipe: Pipe | null;
  useReal?: boolean;
}

function sourceBadge(source: RiskSummaryResponse["source"]): {
  label: string;
  className: string;
} {
  if (source === "nemotron") {
    return { label: "Nemotron W1", className: "summary-agent-badge nemotron" };
  }
  return { label: "Template fallback", className: "summary-agent-badge template" };
}

export default function SummaryAgent({ pipe, useReal = true }: SummaryAgentProps) {
  const [state, setState] = useState<RiskSummaryState>({ status: "idle" });

  useEffect(() => {
    if (!pipe) {
      setState({ status: "idle" });
      return;
    }

    const pipeId = pipe.pipe_id;
    let cancelled = false;

    setState({ status: "loading", pipeId });

    fetchRiskSummary(pipeId, useReal)
      .then((data) => {
        if (cancelled) return;
        setState({ status: "ready", pipeId, data });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof Error ? err.message : "Failed to load risk summary.";
        setState({ status: "error", pipeId, message });
      });

    return () => {
      cancelled = true;
    };
  }, [pipe?.pipe_id, useReal]);

  if (!pipe) {
    return (
      <section className="summary-agent summary-agent-empty" aria-label="Summary Agent">
        <header className="summary-agent-header">
          <div>
            <span className="summary-agent-label">Workflow 1</span>
            <h3>Summary Agent</h3>
          </div>
          <span className="summary-agent-status idle">Standby</span>
        </header>
        <p className="summary-agent-placeholder">
          Select a pipe segment to generate a Nemotron risk summary.
        </p>
      </section>
    );
  }

  const isStale =
    state.status !== "idle" &&
    state.status !== "loading" &&
    state.pipeId !== pipe.pipe_id;

  return (
    <section className="summary-agent" aria-label="Summary Agent">
      <header className="summary-agent-header">
        <div>
          <span className="summary-agent-label">Workflow 1 · Nemotron Nano</span>
          <h3>Summary Agent</h3>
        </div>
        {state.status === "loading" && !isStale && (
          <span className="summary-agent-status loading">
            <span className="summary-agent-dot" aria-hidden="true" />
            Analyzing
          </span>
        )}
        {state.status === "ready" && !isStale && (
          <span className={sourceBadge(state.data.source).className}>
            {sourceBadge(state.data.source).label}
          </span>
        )}
      </header>

      {state.status === "loading" && (
        <div className="summary-agent-loading">
          <p>Building evidence packet and calling Nemotron for {pipe.pipe_id}…</p>
          <small>This may take 20–50 seconds when Ollama is running locally.</small>
        </div>
      )}

      {state.status === "error" && !isStale && (
        <div className="summary-agent-error" role="alert">
          {state.message}
        </div>
      )}

      {state.status === "ready" && !isStale && (
        <div className="summary-agent-body">
          <p className="summary-agent-headline">{state.data.summary.headline}</p>
          <p className="summary-agent-risk">{state.data.summary.risk_sentence}</p>

          {state.data.summary.top_reasons.length > 0 && (
            <ul className="summary-agent-reasons">
              {state.data.summary.top_reasons.slice(0, 5).map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          )}

          <p className="summary-agent-next">
            <strong>Next:</strong> {state.data.summary.recommended_next_step}
          </p>

          {state.data.summary.caveats.length > 0 && (
            <p className="summary-agent-caveats">
              {state.data.summary.caveats.slice(0, 2).join(" · ")}
            </p>
          )}

          {state.data.model && (
            <p className="summary-agent-model">Model: {state.data.model}</p>
          )}
        </div>
      )}
    </section>
  );
}
