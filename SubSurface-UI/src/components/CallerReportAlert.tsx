import type { VoiceMatchResponse } from "../types/voice";
import { voiceClientUrl } from "../api/voice";

interface CallerReportAlertProps {
  voiceMatch: VoiceMatchResponse | null;
  selectedPipeId: string | null;
  useMatchedPipe: boolean;
  onUseMatchedPipeChange: (value: boolean) => void;
}

export default function CallerReportAlert({
  voiceMatch,
  selectedPipeId,
  useMatchedPipe,
  onUseMatchedPipeChange,
}: CallerReportAlertProps) {
  const match = voiceMatch?.match;
  const payload = voiceMatch?.payload;

  if (!match) {
    return (
      <section className="voice-section voice-section-empty" aria-label="Voice reporting">
        <header className="voice-section-header">
          <div>
            <span className="voice-section-label">Voice Reporting Line</span>
            <h3>Caller Reports</h3>
          </div>
        </header>
        <p className="voice-section-placeholder">
          No active caller report. Open the{" "}
          <a href={voiceClientUrl()} target="_blank" rel="noreferrer">
            Voice Reporting Line
          </a>{" "}
          to record a push-to-talk session.
        </p>
      </section>
    );
  }

  const incident = payload?.incident;
  const loc =
    incident && typeof incident === "object" && "location" in incident
      ? (incident.location as { address?: string } | undefined)
      : undefined;
  const address = loc?.address ?? "reported location";
  const where = match.matched_neighbourhood
    ? `${address} · neighbourhood ${match.matched_neighbourhood}`
    : address;

  const showOverride =
    selectedPipeId !== null && match.pipe_id !== selectedPipeId;

  return (
    <section className="voice-section" aria-label="Active caller report">
      <header className="voice-section-header">
        <div>
          <span className="voice-section-label">Voice Reporting Line</span>
          <h3>Active Caller Report</h3>
        </div>
        <span className="voice-alert-dot" aria-hidden="true" />
      </header>

      <div className="voice-alert" role="status">
        <p className="voice-alert-location">{where}</p>
        <p className="voice-alert-meta">
          Matched to <strong>{match.pipe_id}</strong> ·{" "}
          {Math.round(match.confidence * 100)}% confidence · {match.method}
        </p>
      </div>

      {showOverride && (
        <label className="voice-override">
          <input
            type="checkbox"
            checked={useMatchedPipe}
            onChange={(e) => onUseMatchedPipeChange(e.target.checked)}
          />
          Use matched caller pipe ({match.pipe_id}) instead of map selection (
          {selectedPipeId})
        </label>
      )}

      <p className="voice-client-link">
        <a href={voiceClientUrl()} target="_blank" rel="noreferrer">
          Open Voice Reporting Line
        </a>
      </p>
    </section>
  );
}
