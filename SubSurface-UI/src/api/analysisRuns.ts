import type {
  AnalysisRunRequest,
  AnalysisRunResponse,
  Workflow2Health,
} from "../types/analysisRun";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";
const W2_TIMEOUT_MS = Number(
  import.meta.env.VITE_WORKFLOW2_TIMEOUT_MS ?? 1_800_000,
);
const W2_TIMEOUT_MINUTES = Math.round(W2_TIMEOUT_MS / 60_000);

async function parseError(res: Response, fallback: string): Promise<string> {
  const body = await res.text().catch(() => "");
  let detail = body.trim();
  try {
    const parsed = JSON.parse(body) as { detail?: string };
    if (parsed.detail) detail = parsed.detail;
  } catch {
    /* plain text */
  }
  return detail ? `${fallback} (${res.status}): ${detail}` : `${fallback} (${res.status}).`;
}

export async function fetchWorkflow2Health(): Promise<Workflow2Health> {
  const url = `${API_BASE}/health/workflow2`;
  let res: Response;
  try {
    res = await fetch(url);
  } catch {
    throw new Error(
      "Cannot reach Workflow 2 health endpoint. Start the SubSurface backend on port 8000.",
    );
  }
  if (!res.ok) {
    throw new Error(await parseError(res, "Workflow 2 health check failed"));
  }
  return res.json() as Promise<Workflow2Health>;
}

export async function createAnalysisRun(
  request: AnalysisRunRequest,
  signal?: AbortSignal,
): Promise<AnalysisRunResponse> {
  const url = `${API_BASE}/api/analysis-runs`;
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), W2_TIMEOUT_MS);
  const abortFromCaller = () => controller.abort();
  signal?.addEventListener("abort", abortFromCaller, { once: true });

  let res: Response;
  try {
    res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pipe_id: request.pipe_id,
        use_real: request.use_real ?? true,
        use_latest_voice_transcript: request.use_latest_voice_transcript ?? true,
        transcript_path: request.transcript_path ?? null,
      }),
      signal: controller.signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      if (signal?.aborted) {
        throw new Error("Workflow 2 analysis was cancelled.");
      }
      throw new Error(`Workflow 2 timed out after ${W2_TIMEOUT_MINUTES} minutes.`);
    }
    throw new Error(
      "Cannot reach Workflow 2 API. Start the SubSurface backend on port 8000.",
    );
  } finally {
    window.clearTimeout(timeout);
    signal?.removeEventListener("abort", abortFromCaller);
  }

  if (!res.ok) {
    throw new Error(await parseError(res, "Workflow 2 analysis failed"));
  }
  return res.json() as Promise<AnalysisRunResponse>;
}

export async function getAnalysisRun(runId: string): Promise<AnalysisRunResponse> {
  const url = `${API_BASE}/api/analysis-runs/${encodeURIComponent(runId)}`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(await parseError(res, "Failed to load analysis run"));
  }
  return res.json() as Promise<AnalysisRunResponse>;
}
