"""
Georeference an APT image from the pass TLE and start time.

Each APT line is one AVHRR scan (2 lines/s). The 909 image pixels span the
AVHRR scan of ±55.37° from nadir, perpendicular to the ground track, and are
resampled to be evenly spaced in ground distance (not in scan angle) —
checked by overlaying coastlines on real passes.
Pixel 0 lies to the right of the direction of travel (that's why
northbound passes look upside down when displayed unrotated).
"""
from datetime import datetime, timedelta
import numpy as np
from pyorbital.orbital import Orbital

R_EARTH = 6371.0
SCAN_HALF_ANGLE = np.radians(55.37)
LINE_SECONDS = 0.5
PIXELS = 909
NOMINAL_ALT_KM = 850.0


def parse_time(s: str) -> datetime:
    return datetime.strptime(s.replace("Z", ""), "%Y-%m-%dT%H:%M:%S")

def _destination(lat, lon, bearing, dist_km):
    """Great-circle destination point (all angles in radians)."""
    d = dist_km / R_EARTH
    lat2 = np.arcsin(np.sin(lat) * np.cos(d) + np.cos(lat) * np.sin(d) * np.cos(bearing))
    lon2 = lon + np.arctan2(np.sin(bearing) * np.sin(d) * np.cos(lat),
                            np.cos(d) - np.sin(lat) * np.sin(lat2))
    return lat2, (lon2 + np.pi) % (2 * np.pi) - np.pi

def _bearing(lat1, lon1, lat2, lon2):
    dlon = lon2 - lon1
    y = np.sin(dlon) * np.cos(lat2)
    x = np.cos(lat1) * np.sin(lat2) - np.sin(lat1) * np.cos(lat2) * np.cos(dlon)
    return np.arctan2(y, x)

def _max_central_angle(h):
    """Earth central angle from nadir to the edge of the swath."""
    return np.arcsin((R_EARTH + h) / R_EARTH * np.sin(SCAN_HALF_ANGLE)) - SCAN_HALF_ANGLE

def cross_track_fraction(step: int = 1) -> np.ndarray:
    j = np.arange(0, PIXELS, step)
    return (PIXELS // 2 - j) / (PIXELS // 2)          # +ve = right of track, ±1 at edges

def scan_angles(step: int = 1, h: float = NOMINAL_ALT_KM) -> np.ndarray:
    """Instrument view angle (radians) for each pixel."""
    gamma = cross_track_fraction(step) * _max_central_angle(h)
    return np.arctan2(R_EARTH * np.sin(gamma), R_EARTH + h - R_EARTH * np.cos(gamma))

def track(satellite, tle1, tle2, start_utc, n_lines, time_offset_s=0.0):
    """Sub-satellite point, altitude and heading for every line."""
    orb = Orbital(satellite, line1=tle1, line2=tle2)
    t0 = parse_time(start_utc) + timedelta(seconds=time_offset_s)
    times = np.array([t0 + timedelta(seconds=i * LINE_SECONDS) for i in range(n_lines + 1)],
                     dtype="datetime64[ms]")
    lon, lat, alt = orb.get_lonlatalt(times)
    lat, lon = np.radians(lat), np.radians(lon)
    heading = _bearing(lat[:-1], lon[:-1], lat[1:], lon[1:])
    return lat[:-1], lon[:-1], alt[:-1], heading, times[:-1]

def geolocate(satellite, tle1, tle2, start_utc, n_lines, step=1, time_offset_s=0.0, mirror=False):
    """Latitude/longitude (degrees) of every pixel, shape (n_lines, 909/step)."""
    lat, lon, alt, heading, times = track(satellite, tle1, tle2, start_utc, n_lines, time_offset_s)
    frac = cross_track_fraction(step)
    if mirror:
        frac = -frac

    # Pixels are evenly spaced in ground distance out to the swath edge
    dist = np.abs(frac) * R_EARTH * _max_central_angle(alt.mean())

    side = np.where(frac >= 0, np.pi / 2, -np.pi / 2)
    bearing = heading[:, None] + side[None, :]
    plat, plon = _destination(lat[:, None], lon[:, None], bearing, dist[None, :])
    return np.degrees(plat), np.degrees(plon), times

def locate_point(satellite, tle1, tle2, start_utc, n_lines, lat0, lon0,
                 time_offset_s=0.0, mirror=False):
    """Line/pixel that views (lat0, lon0), or None if outside the swath."""
    plat, plon, times = geolocate(satellite, tle1, tle2, start_utc, n_lines, step=4,
                                  time_offset_s=time_offset_s, mirror=mirror)
    p1, l1 = np.radians(plat), np.radians(plon)
    p0, l0 = np.radians(lat0), np.radians(lon0)
    d = R_EARTH * np.arccos(np.clip(np.sin(p0) * np.sin(p1) +
                                    np.cos(p0) * np.cos(p1) * np.cos(l1 - l0), -1, 1))
    i, j4 = np.unravel_index(np.argmin(d), d.shape)
    if d[i, j4] > 25:       # coarse grid spacing is ~16 km at worst
        return None
    if i in (0, n_lines - 1):
        return None
    j = j4 * 4
    return {"line": int(i), "pixel": int(j),
            "scan_angle_deg": float(np.degrees(scan_angles()[j] * (-1 if mirror else 1))),
            "time": str(times[i]),
            "dist_km": float(d[i, j4])}
