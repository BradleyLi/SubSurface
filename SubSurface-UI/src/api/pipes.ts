import type { Pipe, PipesResponse } from "../types/pipe";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

export async function fetchPipes(useReal = true): Promise<PipesResponse> {
  const url = `${API_BASE}/api/pipes?use_real=${useReal}`;

  let res: Response;
  try {
    res = await fetch(url);
  } catch {
    throw new Error(
      "Cannot reach CityNerve API at /api/pipes. Start the backend: cd SubSurface && ./scripts/run_citynerve.sh",
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
        ? `Failed to load pipes (${res.status}): ${detail}`
        : `Failed to load pipes (${res.status}). Restart the SubSurface backend.`,
    );
  }

  return res.json() as Promise<PipesResponse>;
}

export async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/health`);
    return res.ok;
  } catch {
    return false;
  }
}

export function formatCurrency(value: number): string {
  if (value >= 1_000_000) {
    return `$${(value / 1_000_000).toFixed(1)}M`;
  }
  if (value >= 1_000) {
    return `$${Math.round(value / 1_000)}K`;
  }
  return `$${value.toLocaleString()}`;
}

export function formatPercent(probability: number): string {
  return `${(probability * 100).toFixed(1)}%`;
}

export function topShapFeature(pipe: Pipe): string {
  const contributors = pipe.ml_top_shap_contributors;
  if (!contributors?.length) return "—";
  return contributors[0].feature.replace(/_/g, " ");
}
