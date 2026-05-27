"""Lookup-table geocoder for Houston-area locations.

Resolves human-written location strings like "Memorial High School" or
"Sharpstown neighborhood" to (lat, lon). Covers the 10 shelters + Houston
neighborhoods + a handful of landmarks — the locations the demo's stress
personas reference.

This is intentionally NOT a call to Google Maps Geocoding. Reasons:
  • Deterministic across builds (the eval video should reproduce frame-for-frame)
  • Zero cost / quota per query
  • Avoids the cold-start latency of a live API call inside the agent loop
  • The location vocabulary is small (Houston only) and the demo cases hit it

When DisasterLens expands beyond Houston, swap this for a real geocoder.
"""
from __future__ import annotations

from data.personas import SHELTERS
from data.variants import fold_diacritics

# Houston downtown — also the default when nothing matches.
HOUSTON_CENTER: tuple[float, float] = (29.7604, -95.3698)

# Hand-curated locations beyond the shelter list. Keys are lowercase, ascii-folded.
_EXTRA_LOCATIONS: dict[str, tuple[float, float]] = {
    "sharpstown":               (29.7110, -95.5345),
    "alief":                    (29.6929, -95.6021),
    "bellaire":                 (29.7050, -95.4647),
    "memorial":                 (29.7757, -95.5188),  # neighborhood (matches the school too)
    "downtown":                 (29.7604, -95.3698),
    "midtown":                  (29.7445, -95.3756),
    "the heights":              (29.7959, -95.3973),
    "heights":                  (29.7959, -95.3973),
    "katy":                     (29.7858, -95.8245),
    "pasadena":                 (29.6911, -95.2091),
    "spring branch":            (29.7913, -95.5076),
    "river oaks":               (29.7575, -95.4244),
    "galveston":                (29.3013, -94.7977),
    "sugar land":               (29.6197, -95.6349),
    "houston":                  HOUSTON_CENTER,

    # Landmarks
    "mosque hamza":             (29.7110, -95.5345),  # Sharpstown vicinity
    "rice university":          (29.7174, -95.4018),
    "university of houston":    (29.7199, -95.3422),
    "texas children's hospital": (29.7106, -95.4014),
    "methodist hospital":       (29.7106, -95.4007),
}


def _build_lookup() -> dict[str, tuple[float, float]]:
    """Lowercase + ascii-fold both the shelter names and the extra locations."""
    out: dict[str, tuple[float, float]] = {}
    for shelter in SHELTERS:
        key = fold_diacritics(str(shelter["name"])).lower()
        out[key] = (float(shelter["lat"]), float(shelter["lon"]))
        # Also index by shelter_id slug — "sh_memorial_high" without the prefix
        slug = str(shelter["shelter_id"]).removeprefix("sh_").replace("_", " ")
        out[slug] = (float(shelter["lat"]), float(shelter["lon"]))
    for key, coord in _EXTRA_LOCATIONS.items():
        out[fold_diacritics(key).lower()] = coord
    return out


_LOOKUP: dict[str, tuple[float, float]] | None = None


def _lookup() -> dict[str, tuple[float, float]]:
    global _LOOKUP
    if _LOOKUP is None:
        _LOOKUP = _build_lookup()
    return _LOOKUP


def geocode_location(location_text: str) -> dict:
    """Resolve a free-text location string to a {lat, lon, matched, source} dict.

    Strategy: ascii-fold + lowercase the input, then look for the longest
    key in the lookup table that's a substring of the input. Falls back to
    Houston downtown if no key matches.

    Args:
        location_text: free-text location, e.g. "Memorial High School (sophomore)"
            or "near Sharpstown" or "downtown Houston"

    Returns:
        {
          "lat": float,
          "lon": float,
          "matched": "<the lookup key that matched>",
          "source": "lookup_table" | "fallback_houston_center",
          "input": "<original text>"
        }
    """
    if not location_text:
        return {
            "lat": HOUSTON_CENTER[0],
            "lon": HOUSTON_CENTER[1],
            "matched": None,
            "source": "fallback_houston_center",
            "input": location_text,
        }

    needle = fold_diacritics(location_text).lower()
    lookup = _lookup()

    # Longest-key match wins ("memorial high school" beats "memorial").
    best_key: str | None = None
    for key in sorted(lookup.keys(), key=len, reverse=True):
        if key in needle:
            best_key = key
            break

    if best_key is None:
        lat, lon = HOUSTON_CENTER
        return {"lat": lat, "lon": lon, "matched": None,
                "source": "fallback_houston_center", "input": location_text}

    lat, lon = lookup[best_key]
    return {"lat": lat, "lon": lon, "matched": best_key,
            "source": "lookup_table", "input": location_text}
