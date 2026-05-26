import { useEffect, useRef } from "react";
import maplibregl, { Map as MlMap, Marker } from "maplibre-gl";
import type { PendingDecision, Shelter } from "../lib/api";

interface Props {
  shelters: Shelter[];
  focused: PendingDecision | null;
}

// OSM raster tiles — no API key needed. Swap to a Mapbox style for the final
// submission once a public token is provisioned.
const TILE_STYLE: maplibregl.StyleSpecification = {
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

export function ReunificationMap({ shelters, focused }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MlMap | null>(null);
  const markersRef = useRef<Map<string, Marker>>(new Map());

  // Initialise map once.
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: TILE_STYLE,
      center: [-95.42, 29.74], // Houston-ish
      zoom: 10.2,
    });
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Render shelter pins.
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

  // Highlight the focused candidate's shelter and recentre on it.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    markersRef.current.forEach((marker, shelterId) => {
      const el = marker.getElement();
      el.classList.toggle("shelter-pin--focused", shelterId === focused?.candidate_shelter);
    });
    if (focused) {
      const shelter = shelters.find((s) => s.shelter_id === focused.candidate_shelter);
      if (shelter) {
        map.flyTo({ center: [shelter.lon, shelter.lat], zoom: 12.5, speed: 0.8 });
      }
    }
  }, [focused, shelters]);

  return <div ref={containerRef} className="map" />;
}
