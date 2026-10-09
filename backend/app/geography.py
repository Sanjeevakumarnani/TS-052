import json
import math
from typing import Any, Optional, Tuple
from .config import LOCATION_MATCH_RADIUS_METERS


def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points on Earth in meters."""
    R = 6371000.0  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(R * c, 1)


def point_in_polygon(x: float, y: float, poly: list) -> bool:
    """Ray casting algorithm for a 2D polygon given as a list of [lon, lat] pairs."""
    n = len(poly)
    inside = False
    p1x, p1y = poly[0]
    for i in range(n + 1):
        p2x, p2y = poly[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside


def point_in_geojson_geometry(lon: float, lat: float, geometry: dict) -> bool:
    """Check if a (lon, lat) point lies inside a GeoJSON Polygon or MultiPolygon."""
    geom_type = geometry.get("type")
    coords = geometry.get("coordinates", [])
    if geom_type == "Polygon":
        # First ring is exterior boundary
        if coords and point_in_polygon(lon, lat, coords[0]):
            # Check interior rings (holes)
            for hole in coords[1:]:
                if point_in_polygon(lon, lat, hole):
                    return False
            return True
        return False
    elif geom_type == "MultiPolygon":
        for poly in coords:
            if poly and point_in_polygon(lon, lat, poly[0]):
                in_hole = False
                for hole in poly[1:]:
                    if point_in_polygon(lon, lat, hole):
                        in_hole = True
                        break
                if not in_hole:
                    return True
        return False
    return False


def verify_user_location(
    user_lat: float,
    user_lon: float,
    accuracy_meters: float,
    village: dict,
    max_radius_meters: Optional[float] = None,
) -> dict:
    """
    Verify if a user's reported coordinates match the target village.
    Distance restriction is relaxed -- any location is accepted (MVP/demo mode).
    The actual distance is recorded for informational purposes only.
    """
    # Only reject completely broken GPS readings (> 50,000 metres accuracy)
    if accuracy_meters > 50000:
        return {
            "matched": False,
            "status": "inaccurate_reading",
            "method": "rejected",
            "distance_meters": None,
            "accuracy_meters": accuracy_meters,
            "message": f"GPS accuracy radius is too broad (±{round(accuracy_meters)}m). Please retry in an open area.",
        }

    # 1. Boundary polygon check (best signal when available)
    boundary = village.get("boundary_geojson")
    if boundary:
        if isinstance(boundary, str):
            try:
                boundary = json.loads(boundary)
            except Exception:
                boundary = None
        if isinstance(boundary, dict):
            geom = boundary.get("geometry", boundary)
            if point_in_geojson_geometry(user_lon, user_lat, geom):
                return {
                    "matched": True,
                    "status": "boundary_match",
                    "method": "official_boundary_polygon",
                    "distance_meters": 0.0,
                    "accuracy_meters": accuracy_meters,
                    "message": "Location verified -- your coordinates lie inside the official village boundary.",
                }

    # 2. Centroid distance -- recorded for context, NOT used to reject
    v_lat = village.get("latitude")
    v_lon = village.get("longitude")
    if v_lat is None or v_lon is None:
        return {
            "matched": True,
            "status": "accepted_no_centroid",
            "method": "open_verification",
            "distance_meters": None,
            "accuracy_meters": accuracy_meters,
            "message": "Location accepted. Village reference coordinates are not configured on this server.",
        }

    dist = haversine_distance_meters(user_lat, user_lon, float(v_lat), float(v_lon))
    village_name = village.get("name", village.get("id", "selected village"))

    # Always accept regardless of distance (open verification mode for MVP/demo)
    return {
        "matched": True,
        "status": "accepted",
        "method": "open_verification",
        "distance_meters": dist,
        "accuracy_meters": accuracy_meters,
        "message": (
            f"Location accepted for {village_name}. "
            f"Your GPS is {round(dist / 1000, 1)} km from the village reference point "
            f"(distance check is relaxed for demo)."
        ),
    }

