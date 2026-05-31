import type { RiskLevel } from "../types/pipe";

export const RISK_COLORS: Record<RiskLevel, string> = {
  Critical: "#ff3d3d",
  High: "#ffa726",
  Medium: "#ffdd57",
  Low: "#1de9b6",
};

export const TYPE_COLORS: Record<string, string> = {
  Transmission: "#1de9b6",
  Distribution: "#4fc3f7",
  Synthetic: "#8faabf",
};

export const RISK_LEVELS: RiskLevel[] = ["Critical", "High", "Medium", "Low"];

export const MAP_STYLE = "mapbox://styles/mapbox/light-v11";

export const TORONTO_CENTER = {
  latitude: 43.7,
  longitude: -79.38,
  zoom: 10.8,
  pitch: 55,
  bearing: -17,
};

export const RISK_LINE_WIDTH: Record<RiskLevel, number> = {
  Critical: 4,
  High: 3.5,
  Medium: 3,
  Low: 2.5,
};

export const TYPE_LINE_WIDTH: Record<string, number> = {
  Transmission: 4,
  Distribution: 2.5,
  Synthetic: 2.5,
};

export const CRITICAL_TABLE_LIMIT = 100;
