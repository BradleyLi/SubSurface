import type { RiskSummaryResponse } from "../types/riskSummary";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

export async function fetchRiskSummary(
  pipeId: string,
  useReal = true,
): Promise<RiskSummaryResponse> {
  const url = `${API_BASE}/api/pipes/${encodeURIComponent(pipeId)}/risk-summary?use_real=${useReal}`;

  let res: Response;
  try {
    res = await fetch(url);
  } catch {
    throw new Error(
      "Cannot reach Workflow 1 summary API. Start the SubSurface backend on port 8000.",
    );
  }

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    let detail = body.trim();
    try {
      const parsed = JSON.parse(body) as { detail?: string };
      if (parsed.detail) detail = parsed.detail;
    } catch {
      /* plain text error body */
    }
    throw new Error(
      detail
        ? `Risk summary failed (${res.status}): ${detail}`
        : `Risk summary failed (${res.status}).`,
    );
  }

  return res.json() as Promise<RiskSummaryResponse>;
}
