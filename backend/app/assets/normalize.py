"""Logo normalization.

Twelve of the thirty supplied logo files ship with an opaque white background
while the rest are transparent, so rendering them together produced a mix of
crest-on-dark and white-box-on-dark. This module derives a transparent copy by
flood-filling near-white *from the image edges only* — white inside a mark (the
Nets wordmark, the Spurs horns) touches no border pixel and survives.

Derived files are written to a gitignored `derived/` folder beside the source:
originals are never modified, and the manifest records which copy is served.
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from app.core.logging import get_logger

logger = get_logger(__name__)

DERIVED_DIRNAME = "derived"
_SENTINEL = (255, 0, 254)
_WHITE_MIN = 238  # a pixel at least this bright on every channel reads as background
_FLOOD_THRESHOLD = 26


def has_opaque_light_border(image: Image.Image) -> bool:
    """True when the corners are opaque and near-white — the signature of a logo
    exported onto a white card rather than onto transparency."""
    rgba = image.convert("RGBA")
    width, height = rgba.size
    corners = [(0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)]
    opaque_light = 0
    for xy in corners:
        pixel = rgba.getpixel(xy)
        if not isinstance(pixel, tuple) or len(pixel) < 4:
            continue
        red, green, blue, alpha = pixel[0], pixel[1], pixel[2], pixel[3]
        if alpha > 250 and min(red, green, blue) >= _WHITE_MIN:
            opaque_light += 1
    return opaque_light >= 3


def normalize_logo(source: Path, derived_dir: Path) -> Path | None:
    """Return a transparent-background copy of `source`, or None when the file
    already has transparency and should be served as-is.

    Regenerated only when the derived file is missing or older than the source,
    so repeat indexing runs stay cheap.
    """
    try:
        with Image.open(source) as opened:
            image = opened.convert("RGBA")
    except Exception as exc:  # unreadable/corrupt file — serve the original
        logger.warning("could not read logo %s: %s", source.name, exc)
        return None

    if not has_opaque_light_border(image):
        return None

    derived_dir.mkdir(parents=True, exist_ok=True)
    target = derived_dir / f"{source.stem}.png"
    if target.exists() and target.stat().st_mtime >= source.stat().st_mtime:
        return target

    # Flood the background with a sentinel colour from every edge midpoint and
    # corner; anything the fill reaches is background.
    flat = image.convert("RGB")
    width, height = flat.size
    seeds = [
        (0, 0),
        (width - 1, 0),
        (0, height - 1),
        (width - 1, height - 1),
        (width // 2, 0),
        (width // 2, height - 1),
        (0, height // 2),
        (width - 1, height // 2),
    ]
    for seed in seeds:
        pixel = flat.getpixel(seed)
        if not isinstance(pixel, tuple) or len(pixel) < 3:
            continue
        if min(pixel[0], pixel[1], pixel[2]) >= _WHITE_MIN:
            ImageDraw.floodfill(flat, seed, _SENTINEL, thresh=_FLOOD_THRESHOLD)

    filled = np.array(flat)
    background = (
        (filled[:, :, 0] == _SENTINEL[0])
        & (filled[:, :, 1] == _SENTINEL[1])
        & (filled[:, :, 2] == _SENTINEL[2])
    )
    rgba = np.array(image)
    rgba[background, 3] = 0

    Image.fromarray(rgba, mode="RGBA").save(target, "PNG", optimize=True)
    logger.info(
        "normalized logo background: %s (%d%% of pixels)",
        source.name,
        round(100 * float(background.mean())),
    )
    return target
