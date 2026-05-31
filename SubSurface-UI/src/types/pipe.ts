export type RiskLevel = "Critical" | "High" | "Medium" | "Low";

export interface ShapContributor {
  feature: string;
  feature_value: number;
  shap_contribution: number;
  impact: string;
}

export interface Pipe {
  pipe_id: string;
  lat0: number;
  lon0: number;
  lat1: number;
  lon1: number;
  lat: number;
  lon: number;
  street?: string;
  pipe_type: string;
  ward: string;
  material: string;
  install_year?: number;
  age: number;
  diameter_mm: number;
  length_m: number;
  predicted_break_probability: number;
  risk_score: number;
  risk_percentile: number;
  risk_level: RiskLevel;
  risk_color: string;
  prediction_date?: string;
  ml_top_shap_contributors?: ShapContributor[];
  break_count_10yr?: number;
  ml_break_count_10yr?: number;
  properties_affected?: number;
  emergency_cost: number;
  replacement_cost: number;
  expected_savings: number;
  priority_rank?: number;
  data_source?: string;
}

export interface PipesResponse {
  count: number;
  records: Pipe[];
  source: string;
}

export interface FilterState {
  riskLevels: RiskLevel[];
  materials: string[];
  wards: string[];
  pipeTypes: string[];
  minRiskScore: number;
  colorMode: "risk" | "type";
}

export interface PipeGeoJSON extends GeoJSON.FeatureCollection {
  features: GeoJSON.Feature<GeoJSON.LineString, {
    pipe_id: string;
    risk_level: RiskLevel;
    risk_color: string;
    risk_score: number;
    pipe_type: string;
  }>[];
}
