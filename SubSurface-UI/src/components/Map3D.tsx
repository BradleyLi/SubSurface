import { useCallback, useEffect, useMemo, useRef } from "react";
import type { MapLayerMouseEvent } from "mapbox-gl";
import Map, {
  Layer,
  NavigationControl,
  Source,
  type MapRef,
} from "react-map-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import type { Pipe } from "../types/pipe";
import { MAP_STYLE, TORONTO_CENTER } from "../constants/colors";
import {
  lineWidthExpression,
  pipesToGeoJSON,
  riskColorExpression,
  selectedPipeGeoJSON,
  voiceMarkerGeoJSON,
} from "../utils/geojson";
import type { VoicePipeMatch } from "../types/voice";

interface Map3DProps {
  pipes: Pipe[];
  colorMode: "risk" | "type";
  selectedPipe: Pipe | null;
  onSelectPipe: (pipe: Pipe | null) => void;
  voiceMatch?: VoicePipeMatch | null;
}

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN ?? "";

export default function Map3D({
  pipes,
  colorMode,
  selectedPipe,
  onSelectPipe,
  voiceMatch,
}: Map3DProps) {
  const mapRef = useRef<MapRef>(null);
  const geojson = useMemo(
    () => pipesToGeoJSON(pipes, colorMode),
    [pipes, colorMode],
  );
  const selectionGeojson = useMemo(
    () => selectedPipeGeoJSON(selectedPipe),
    [selectedPipe],
  );
  const voiceGeojson = useMemo(
    () => voiceMarkerGeoJSON(voiceMatch?.lat, voiceMatch?.lon),
    [voiceMatch?.lat, voiceMatch?.lon],
  );

  const flyToPipe = useCallback((pipe: Pipe) => {
    mapRef.current?.flyTo({
      center: [pipe.lon, pipe.lat],
      zoom: 14,
      pitch: 60,
      bearing: -20,
      duration: 1200,
      essential: true,
    });
  }, []);

  useEffect(() => {
    if (selectedPipe) flyToPipe(selectedPipe);
  }, [selectedPipe, flyToPipe]);

  const handleClick = useCallback(
    (event: MapLayerMouseEvent) => {
      const feature = event.features?.[0];
      if (!feature?.properties?.pipe_id) {
        onSelectPipe(null);
        return;
      }
      const pipe = pipes.find((p) => p.pipe_id === feature.properties?.pipe_id);
      onSelectPipe(pipe ?? null);
    },
    [pipes, onSelectPipe],
  );

  if (!MAPBOX_TOKEN) {
    return (
      <div className="map-error">
        <h2>Mapbox token required</h2>
        <p>
          Copy <code>.env.example</code> to <code>.env</code> and set{" "}
          <code>VITE_MAPBOX_TOKEN</code>.
        </p>
        <p>
          Get a free token at{" "}
          <a
            href="https://account.mapbox.com/access-tokens/"
            target="_blank"
            rel="noreferrer"
          >
            mapbox.com
          </a>
        </p>
      </div>
    );
  }

  return (
    <div className="map-shell">
      <Map
        ref={mapRef}
        mapboxAccessToken={MAPBOX_TOKEN}
        initialViewState={TORONTO_CENTER}
        mapStyle={MAP_STYLE}
        style={{ width: "100%", height: "100%" }}
        interactiveLayerIds={["pipes-layer"]}
        onClick={handleClick}
        cursor="pointer"
        antialias
        fog={{
          color: "rgb(230, 240, 250)",
          "high-color": "rgb(200, 220, 240)",
          "horizon-blend": 0.08,
          "space-color": "rgb(180, 200, 220)",
          "star-intensity": 0,
        }}
        onLoad={(e) => {
          const map = e.target;
          if (!map.getSource("mapbox-dem")) {
            map.addSource("mapbox-dem", {
              type: "raster-dem",
              url: "mapbox://mapbox.mapbox-terrain-dem-v1",
              tileSize: 512,
              maxzoom: 14,
            });
          }
          map.setTerrain({ source: "mapbox-dem", exaggeration: 1.2 });
        }}
      >
        <NavigationControl position="bottom-right" showCompass showZoom />

        <Source id="pipes" type="geojson" data={geojson}>
          <Layer
            id="pipes-layer"
            type="line"
            paint={{
              "line-color": riskColorExpression(colorMode) as mapboxgl.Expression,
              "line-width": lineWidthExpression(colorMode) as mapboxgl.Expression,
              "line-opacity": 0.88,
            }}
            layout={{
              "line-cap": "round",
              "line-join": "round",
            }}
          />
        </Source>

        <Source id="selection" type="geojson" data={selectionGeojson}>
          <Layer
            id="selection-glow"
            type="line"
            filter={["==", ["geometry-type"], "LineString"]}
            paint={{
              "line-color": "#ff4fd8",
              "line-width": 8,
              "line-opacity": 0.35,
            }}
          />
          <Layer
            id="selection-line"
            type="line"
            filter={["==", ["geometry-type"], "LineString"]}
            paint={{
              "line-color": "#ff4fd8",
              "line-width": 4,
              "line-opacity": 1,
            }}
          />
          <Layer
            id="selection-point"
            type="circle"
            filter={["==", ["geometry-type"], "Point"]}
            paint={{
              "circle-radius": 8,
              "circle-color": "#ff4fd8",
              "circle-stroke-width": 2,
              "circle-stroke-color": "#ffffff",
            }}
          />
        </Source>

        <Source id="voice-marker" type="geojson" data={voiceGeojson}>
          <Layer
            id="voice-marker-glow"
            type="circle"
            paint={{
              "circle-radius": 16,
              "circle-color": "#f97316",
              "circle-opacity": 0.25,
            }}
          />
          <Layer
            id="voice-marker-point"
            type="circle"
            paint={{
              "circle-radius": 8,
              "circle-color": "#f97316",
              "circle-stroke-width": 2,
              "circle-stroke-color": "#ffffff",
            }}
          />
        </Source>
      </Map>

      <div className="map-legend">
        {colorMode === "risk" ? (
          <>
            <span className="legend-item">
              <i style={{ background: "#ff3d3d" }} /> Critical
            </span>
            <span className="legend-item">
              <i style={{ background: "#ffa726" }} /> High
            </span>
            <span className="legend-item">
              <i style={{ background: "#ffdd57" }} /> Medium
            </span>
            <span className="legend-item">
              <i style={{ background: "#1de9b6" }} /> Low
            </span>
          </>
        ) : (
          <>
            <span className="legend-item">
              <i style={{ background: "#1de9b6" }} /> Transmission
            </span>
            <span className="legend-item">
              <i style={{ background: "#4fc3f7" }} /> Distribution
            </span>
          </>
        )}
      </div>
    </div>
  );
}
