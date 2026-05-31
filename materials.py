"""
Toronto watermain material codes — stored and displayed as raw Open Data values.
Display-only helpers; no risk scoring or model overrides.
"""

from __future__ import annotations

# Map legend colors for common Toronto codes (unknown codes get a stable hash color).
MAT_PALETTE: dict[str, str] = {
    "CI": "#ff7043",
    "CICL": "#ff8a65",
    "AC": "#ab47bc",
    "CONC": "#78909c",
    "CONP": "#607d8b",
    "DIP": "#26c6da",
    "DICL": "#00acc1",
    "PVC": "#66bb6a",
    "PVCO": "#81c784",
    "PE": "#aed581",
    "CPP": "#9ccc65",
    "SP": "#ffa726",
    "SPCL": "#ffb74d",
    "COP": "#8d6e63",
    "UNK": "#90a4ae",
    "UNKN": "#90a4ae",
}
MAT_COLOR_FALLBACK = "#90a4ae"
_EXTRA_PALETTE = (
    "#ef5350",
    "#ec407a",
    "#7e57c2",
    "#5c6bc0",
    "#29b6f6",
    "#26a69a",
    "#9ccc65",
    "#ffee58",
    "#ffca28",
)


def normalize_material_code(raw: object) -> str:
    """Return Toronto material code as stored in Open Data / ML panel."""
    if raw is None or (isinstance(raw, float) and str(raw) == "nan"):
        return "UNK"
    text = str(raw).strip().upper()
    return text or "UNK"


def material_color(code: str) -> str:
    """Stable display color for any material code."""
    key = normalize_material_code(code)
    if key in MAT_PALETTE:
        return MAT_PALETTE[key]
    idx = sum(ord(c) for c in key) % len(_EXTRA_PALETTE)
    return _EXTRA_PALETTE[idx]
