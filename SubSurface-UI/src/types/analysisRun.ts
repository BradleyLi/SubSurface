export type RoleName = "engineer" | "police" | "field" | "operations";

export interface RoleReport {
  role: RoleName;
  markdown: string;
  source: "nemotron" | "template";
  filename: string;
}

export interface RecommendedAction {
  action: string;
  owner: string;
  urgency: "immediate" | "near_term" | "routine";
  requires_human_approval: boolean;
  evidence: string[];
}

export interface ActionPlan {
  run_id: string;
  priority: string;
  recommended_actions: RecommendedAction[];
  missing_data: string[];
  model_versions: Record<string, string>;
}

export interface BomLineItem {
  line_id: string;
  item_id: string;
  kind: "part" | "service";
  category: string;
  description: string;
  qty: number;
  unit: string;
  chosen_supplier_id: string | null;
  chosen_supplier_name: string | null;
  unit_price: number | null;
  line_total: number;
  alternatives: Record<string, unknown>[];
  reason: string | null;
}

export interface ContractAwardRecommendation {
  supplier_id: string;
  supplier_name: string;
  supplier_type: string;
  scope: string;
  line_item_ids: string[];
  award_subtotal: number;
  rationale: string;
  requires_human_approval: boolean;
}

export interface BillOfMaterials {
  pipe_id: string;
  run_id: string;
  line_items: BomLineItem[];
  contract_awards: ContractAwardRecommendation[];
  parts_subtotal: number;
  services_subtotal: number;
  subtotal: number;
  contingency_pct: number;
  tax_pct: number;
  total_estimate: number;
  currency: string;
  notes: string[];
  missing_data: string[];
}

export interface AnalysisRunResponse {
  run_id: string;
  status: "completed" | "failed";
  pipe_id: string;
  roles: RoleReport[];
  final_markdown: string;
  action_plan: ActionPlan;
  bill_of_materials: BillOfMaterials | null;
  source: "nemotron" | "template" | "partial";
  models: Record<string, string>;
  created_at: string;
  storage_dir: string | null;
}

export interface AnalysisRunRequest {
  pipe_id: string;
  use_real?: boolean;
  use_latest_voice_transcript?: boolean;
  transcript_path?: string | null;
}

export interface Workflow2Health {
  profile: string;
  ok: boolean;
  model: string;
  base_url: string;
  detail: string;
  models_available?: string[];
}

export type AnalysisRunState =
  | { status: "idle" }
  | { status: "loading"; pipeId: string }
  | { status: "ready"; pipeId: string; data: AnalysisRunResponse }
  | { status: "error"; pipeId: string; message: string };
