import type { Pipe, PipeGeoJSON } from "../types/pipe";
import { RISK_COLORS, TYPE_COLORS } from "../constants/colors";

export function pipesToGeoJSON(
  pipes: Pipe[],
  colorMode: "risk" | "type",
): PipeGeoJSON {
  return {
    type: "FeatureCollection",
    features: pipes.map((pipe) => ({
      type: "Feature",
      properties: {
        pipe_id: pipe.pipe_id,
        risk_level: pipe.risk_level,
        risk_color: colorMode === "risk" ? pipe.risk_color : (TYPE_COLORS[pipe.pipe_type] ?? "#8faabf"),
        risk_score: pipe.risk_score,
        pipe_type: pipe.pipe_type,
      },
      geometry: {
        type: "LineString",
        coordinates: [
          [pipe.lon0, pipe.lat0],
          [pipe.lon1, pipe.lat1],
        ],
      },
    })),
  };
}

export function selectedPipeGeoJSON(
  pipe: Pipe | null,
): GeoJSON.FeatureCollection {
  if (!pipe) {
    return { type: "FeatureCollection", features: [] };
  }

  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: { pipe_id: pipe.pipe_id },
        geometry: {
          type: "LineString",
          coordinates: [
            [pipe.lon0, pipe.lat0],
            [pipe.lon1, pipe.lat1],
          ],
        },
      },
      {
        type: "Feature",
        properties: { pipe_id: pipe.pipe_id },
        geometry: {
          type: "Point",
          coordinates: [pipe.lon, pipe.lat],
        },
      },
    ],
  };
}

type MapboxExpression = (string | number | MapboxExpression)[];

export function riskColorExpression(colorMode: "risk" | "type"): MapboxExpression {
  if (colorMode === "type") {
    return [
      "match",
      ["get", "pipe_type"],
      "Transmission",
      TYPE_COLORS.Transmission,
      "Distribution",
      TYPE_COLORS.Distribution,
      "Synthetic",
      TYPE_COLORS.Synthetic,
      "#8faabf",
    ];
  }

  return [
    "match",
    ["get", "risk_level"],
    "Critical",
    RISK_COLORS.Critical,
    "High",
    RISK_COLORS.High,
    "Medium",
    RISK_COLORS.Medium,
    "Low",
    RISK_COLORS.Low,
    "#8faabf",
  ];
}

export function lineWidthExpression(colorMode: "risk" | "type"): MapboxExpression {
  if (colorMode === "type") {
    return [
      "match",
      ["get", "pipe_type"],
      "Transmission",
      4,
      "Distribution",
      2.5,
      2.5,
    ];
  }

  return [
    "match",
    ["get", "risk_level"],
    "Critical",
    4,
    "High",
    3.5,
    "Medium",
    3,
    2.5,
  ];
}
