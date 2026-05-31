export interface Workflow1Summary {
  pipe_id: string;
  headline: string;
  risk_sentence: string;
  top_reasons: string[];
  recommended_next_step: string;
  caveats: string[];
}

export interface RiskSummaryResponse {
  summary: Workflow1Summary;
  source: "nemotron" | "template";
  model: string | null;
}

export type RiskSummaryState =
  | { status: "idle" }
  | { status: "loading"; pipeId: string }
  | { status: "ready"; pipeId: string; data: RiskSummaryResponse }
  | { status: "error"; pipeId: string; message: string };
