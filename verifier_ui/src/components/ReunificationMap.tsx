import { useEffect, useRef } from "react";
import maplibregl, { Map as MlMap, Marker } from "maplibre-gl";
import type { PendingDecision, Shelter } from "../lib/api";

interface Props {
  shelters: Shelter[];
  focused: PendingDecision | null;
}

// Tile source — Mapbox when a token is provided (the submission story), OSM
// otherwise (zero-config dev). MapLibre-GL-JS happily renders Mapbox raster
// tiles served via the Styles API; we use raster (not vector) so we don't
// need mapbox-gl-js's licensed renderer.
//
// Provision: signup at mapbox.com → Account → Tokens → copy a `pk.*` token →
//   echo 'VITE_MAPBOX_TOKEN=pk.xxxxx' >> verifier_ui/.env.local
//   (then rebuild — Vite inlines VITE_-prefixed env at build time)
const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN as string | undefined;
const MAPBOX_STYLE = "mapbox/streets-v12";

const TILE_STYLE: maplibregl.StyleSpecification = MAPBOX_TOKEN
  ? {
      version: 8,
      sources: {
        mapbox: {
          type: "raster",
          tiles: [
            `https://api.mapbox.com/styles/v1/${MAPBOX_STYLE}/tiles/256/{z}/{x}/{y}@2x?access_token=${MAPBOX_TOKEN}`,
          ],
          tileSize: 256,
          attribution: "© Mapbox © OpenStreetMap",
        },
      },
      layers: [{ id: "mapbox", type: "raster", source: "mapbox" }],
    }
  : {
      version: 8,
      sources: {
        osm: {
          type: "raster",
          tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
          tileSize: 256,
          attribution: "© OpenStreetMap contributors",
        },
      },
      layers: [{ id: "osm", type: "raster", source: "osm" }],
    };

// Fallback seeker location: Houston downtown. The Coordinator agent calls
// geocode_location() on the Intake-extracted last_known_location_text and
// persists the result on the pending_decisions doc; the UI uses that when
// available and falls back to this constant otherwise.
const SEEKER_LOCATION_FALLBACK: [number, number] = [-95.3698, 29.7604];

function seekerLngLat(focused: PendingDecision | null): [number, number] {
  if (focused?.seeker_location) {
    return [focused.seeker_location.lon, focused.seeker_location.lat];
  }
  return SEEKER_LOCATION_FALLBACK;
}

const ARC_SOURCE_ID = "reunification-arc";
const ARC_LAYER_ID = "reunification-arc-line";
const ARC_DURATION_MS = 1500;
const ARC_STEPS = 96;

// Quadratic Bezier arc between two lng/lat points, bulged perpendicular to
// the connecting line. The bulge gives the "great circle" feel without
// needing real spherical interpolation at city scale.
function buildArc(
  from: [number, number],
  to: [number, number]
): GeoJSON.Feature<GeoJSON.LineString> {
  const mid: [number, number] = [(from[0] + to[0]) / 2, (from[1] + to[1]) / 2];
  const dx = to[0] - from[0];
  const dy = to[1] - from[1];
  // perpendicular offset, scaled by line length — bulge upward in screen-space
  const ctrl: [number, number] = [mid[0] - dy * 0.35, mid[1] + dx * 0.35];
  const coords: [number, number][] = [];
  for (let i = 0; i <= ARC_STEPS; i++) {
    const t = i / ARC_STEPS;
    const omt = 1 - t;
    coords.push([
      omt * omt * from[0] + 2 * omt * t * ctrl[0] + t * t * to[0],
      omt * omt * from[1] + 2 * omt * t * ctrl[1] + t * t * to[1],
    ]);
  }
  return {
    type: "Feature",
    properties: {},
    geometry: { type: "LineString", coordinates: coords },
  };
}

export function ReunificationMap({ shelters, focused }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MlMap | null>(null);
  const markersRef = useRef<Map<string, Marker>>(new Map());
  const seekerMarkerRef = useRef<Marker | null>(null);
  const animRef = useRef<number | null>(null);

  // Initialise map + arc layer once.
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: TILE_STYLE,
      center: [-95.42, 29.74],
      zoom: 10.2,
    });
    map.addControl(new maplibregl.NavigationControl(), "top-right");

    map.on("load", () => {
      map.addSource(ARC_SOURCE_ID, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: ARC_LAYER_ID,
        type: "line",
        source: ARC_SOURCE_ID,
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": "#14b8a6",
          "line-width": 3,
          "line-opacity": 0.85,
        },
      });

      // Seeker pin (location is updated on focused change below).
      const seekerEl = document.createElement("div");
      seekerEl.className = "seeker-pin";
      seekerEl.title = "Seeker's last-known location";
      seekerMarkerRef.current = new maplibregl.Marker({ element: seekerEl })
        .setLngLat(SEEKER_LOCATION_FALLBACK)
        .setPopup(new maplibregl.Popup({ offset: 12 }).setText("Seeker — Houston (default)"))
        .addTo(map);
    });

    mapRef.current = map;
    return () => {
      if (animRef.current !== null) cancelAnimationFrame(animRef.current);
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Render shelter pins once shelters arrive.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || shelters.length === 0) return;

    const onLoad = () => {
      for (const s of shelters) {
        if (markersRef.current.has(s.shelter_id)) continue;
        const el = document.createElement("div");
        el.className = "shelter-pin";
        el.title = s.name;
        const marker = new maplibregl.Marker({ element: el })
          .setLngLat([s.lon, s.lat])
          .setPopup(
            new maplibregl.Popup({ offset: 12 }).setText(`${s.name} (${s.shelter_id})`)
          )
          .addTo(map);
        markersRef.current.set(s.shelter_id, marker);
      }
    };
    if (map.loaded()) onLoad();
    else map.once("load", onLoad);
  }, [shelters]);

  // On focused change: highlight pin, recenter, redraw arc with animation.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    markersRef.current.forEach((marker, shelterId) => {
      marker.getElement().classList.toggle(
        "shelter-pin--focused",
        shelterId === focused?.candidate_shelter
      );
    });

    if (animRef.current !== null) {
      cancelAnimationFrame(animRef.current);
      animRef.current = null;
    }

    const apply = () => {
      const src = map.getSource(ARC_SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
      if (!src) return;
      if (!focused) {
        src.setData({ type: "FeatureCollection", features: [] });
        return;
      }
      const shelter = shelters.find((s) => s.shelter_id === focused.candidate_shelter);
      if (!shelter) return;
      const dest: [number, number] = [shelter.lon, shelter.lat];
      const origin = seekerLngLat(focused);

      // Move the seeker pin to the focused decision's location + update its popup.
      if (seekerMarkerRef.current) {
        seekerMarkerRef.current.setLngLat(origin);
        const popupText = focused.seeker_location_text
          ? `Seeker — ${focused.seeker_location_text}`
          : "Seeker — Houston (default)";
        seekerMarkerRef.current.setPopup(
          new maplibregl.Popup({ offset: 12 }).setText(popupText)
        );
      }

      const fullArc = buildArc(origin, dest);
      const allCoords = fullArc.geometry.coordinates as [number, number][];

      // Fit both endpoints comfortably in view.
      const bounds = new maplibregl.LngLatBounds(origin, dest);
      map.fitBounds(bounds, { padding: 80, duration: 700, maxZoom: 12 });

      // Animate the arc by progressively revealing more of the LineString.
      // line-trim-offset would be cleaner but isn't typed in MapLibre 4.7;
      // re-setting the geojson per frame is portable and fast enough.
      let start = 0;
      const step = (ts: number) => {
        if (!start) start = ts;
        const t = Math.min((ts - start) / ARC_DURATION_MS, 1);
        const eased = 1 - (1 - t) * (1 - t); // ease-out quad
        const cutoff = Math.max(2, Math.floor(eased * allCoords.length));
        src.setData({
          type: "FeatureCollection",
          features: [{
            type: "Feature",
            properties: {},
            geometry: { type: "LineString", coordinates: allCoords.slice(0, cutoff) },
          }],
        });
        if (t < 1) animRef.current = requestAnimationFrame(step);
        else animRef.current = null;
      };
      // Start hidden, then animate in.
      src.setData({ type: "FeatureCollection", features: [] });
      animRef.current = requestAnimationFrame(step);
    };

    if (map.loaded() && map.getSource(ARC_SOURCE_ID)) apply();
    else map.once("load", apply);
  }, [focused, shelters]);

  return <div ref={containerRef} className="map" />;
}
