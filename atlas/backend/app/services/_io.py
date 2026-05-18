"""Atomic JSON read/write — used by every service that mutates facility data."""

from __future__ import annotations

import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    """Temp-file + rename so a crashed write never leaves a half-file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(path)


def ensure_tools_on_path() -> None:
    """Lazy sys.path injection so we can `import fetch_*` from atlas/backend."""
    import sys

    from app.paths import REPO_ROOT
    tools_dir = REPO_ROOT / "tools"
    if not tools_dir.exists():
        raise RuntimeError(f"Cannot find tools/ at {tools_dir}")
    p = str(tools_dir)
    if p not in sys.path:
        sys.path.insert(0, p)


@dataclass
class ImageMeta:
    """Subset of EXIF tags we keep when persisting a user-uploaded photo.
    Anything not on this struct is discarded by safe_image_write."""
    lat: float | None = None
    lng: float | None = None
    alt: float | None = None
    heading: float | None = None
    timestamp: str | None = None  # ISO 8601


def _gps_to_decimal(coord: tuple, ref: str) -> float | None:
    """EXIF GPS is stored as ((deg_num, deg_den), (min_num, min_den), (sec_num, sec_den))
    plus a 'N'/'S'/'E'/'W' ref. Convert to signed decimal degrees."""
    try:
        d = float(coord[0])
        m = float(coord[1])
        s = float(coord[2])
    except (TypeError, ValueError, IndexError):
        return None
    val = d + m / 60.0 + s / 3600.0
    if ref in ("S", "W"):
        val = -val
    return val


def safe_image_write(raw: bytes, path: Path) -> ImageMeta:
    """Re-encode an uploaded image to JPEG, stripping all EXIF except a small
    GPS/timestamp whitelist. Writes to ``path`` atomically. Returns the parsed
    metadata.

    Defense-in-depth: even if the upload's MIME claims image/jpeg, Pillow
    decodes + re-encodes so we never persist attacker-controlled bytes
    verbatim. EXIF that survives the round-trip is ONLY the fields we
    explicitly copy back in.
    """
    from PIL import Image, ExifTags  # type: ignore

    # HEIC/HEIF support: pillow-heif registers as a Pillow plugin so
    # Image.open() decodes iPhone .heic uploads transparently. The output
    # is always JPEG (we re-encode below) regardless of input format.
    try:
        from pillow_heif import register_heif_opener  # type: ignore
        register_heif_opener()
    except ImportError:
        pass

    img = Image.open(io.BytesIO(raw))
    img.load()

    # Parse the GPS + datetime fields BEFORE we drop EXIF.
    meta = ImageMeta()
    try:
        exif = img.getexif()
    except Exception:
        exif = None

    if exif:
        # DateTimeOriginal lives in the Exif sub-IFD at tag 0x9003 on phone
        # photos, but some legacy cams put it at the top level. Check both.
        candidates: list[Any] = []
        candidates.append(exif.get(0x9003))
        try:
            exif_ifd = exif.get_ifd(ExifTags.IFD.Exif)
            if exif_ifd:
                candidates.append(exif_ifd.get(0x9003))
        except Exception:
            pass
        for value in candidates:
            if isinstance(value, str) and value:
                try:
                    date, time = value.split(" ", 1)
                    meta.timestamp = f"{date.replace(':', '-')}T{time}"
                    break
                except ValueError:
                    continue

        # GPS is in a sub-IFD.
        try:
            gps_ifd = exif.get_ifd(ExifTags.IFD.GPSInfo)
        except Exception:
            gps_ifd = None
        if gps_ifd:
            gps = {ExifTags.GPSTAGS.get(k, k): v for k, v in gps_ifd.items()}
            lat = _gps_to_decimal(gps.get("GPSLatitude"), gps.get("GPSLatitudeRef", "N"))
            lng = _gps_to_decimal(gps.get("GPSLongitude"), gps.get("GPSLongitudeRef", "E"))
            if lat is not None and lng is not None:
                meta.lat = lat
                meta.lng = lng
            alt_raw = gps.get("GPSAltitude")
            if alt_raw is not None:
                try:
                    alt = float(alt_raw)
                    if gps.get("GPSAltitudeRef") == 1:  # below sea level
                        alt = -alt
                    meta.alt = alt
                except (TypeError, ValueError):
                    pass
            heading = gps.get("GPSImgDirection")
            if heading is not None:
                try:
                    meta.heading = float(heading)
                except (TypeError, ValueError):
                    pass

    # Re-encode without EXIF. Pillow's save() with no exif kwarg drops it.
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    img.save(tmp, format="JPEG", quality=85, optimize=True)
    tmp.replace(path)
    return meta


def ensure_streetview_poc_on_path() -> None:
    """Lazy sys.path injection so we can `from streetview_poc.poc import ...`
    from atlas/backend. The POC modules are reused by the streetview_edges
    service rather than copied."""
    import sys

    from app.paths import REPO_ROOT
    poc_root = REPO_ROOT / "streetview_poc"
    if not poc_root.exists():
        raise RuntimeError(f"Cannot find streetview_poc/ at {poc_root}")
    # Insert the parent so `streetview_poc.poc.X` imports work.
    p = str(REPO_ROOT)
    if p not in sys.path:
        sys.path.insert(0, p)
