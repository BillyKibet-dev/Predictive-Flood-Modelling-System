"""One photo per citizen report, re-encoded so no metadata (GPS, phone model, time) survives.

The upload is decoded with Pillow, turned the right way up, shrunk to at most 1600 px and
saved as a fresh JPEG. Nothing from the original file is copied except the pixels, so EXIF,
XMP, ICC profiles and anything hidden after the image data are dropped. Files are named by
their hash and only staff can read them.
"""
import hashlib
import io
import os
from pathlib import Path
import tempfile
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

from src.api.config import settings

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 40_000_000          # decompression-bomb guard (about 7,700 x 5,200)
LONG_SIDE = 1600
ACCEPTED = {"JPEG", "PNG", "WEBP"}


class PhotoRejected(ValueError):
    """The upload is not an acceptable image; the message is safe to show the resident."""


def photo_dir() -> Path:
    path = Path(settings.REPORT_PHOTO_DIR)
    return path if path.is_absolute() else Path(__file__).resolve().parents[3] / path


def clean_jpeg(raw: bytes) -> bytes:
    if not raw:
        raise PhotoRejected("The photo is empty.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise PhotoRejected("The photo is larger than 8 MB.")
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in ACCEPTED:
                    raise PhotoRejected("Use a JPEG, PNG or WebP photo.")
                image.load()
                upright = ImageOps.exif_transpose(image)   # honour rotation, then drop the tag
                pixels = upright.convert("RGB")
    except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning, OSError, SyntaxError):
        raise PhotoRejected("That file could not be read as a photo.") from None
    pixels.thumbnail((LONG_SIDE, LONG_SIDE))
    clean = Image.frombytes("RGB", pixels.size, pixels.tobytes())   # pixels only: no info dict carried over
    out = io.BytesIO()
    clean.save(out, format="JPEG", quality=82, optimize=True)
    return out.getvalue()


def store(raw: bytes) -> tuple[str, int]:
    """Clean and save; returns (sha256, size). Writes atomically, never overwrites."""
    data = clean_jpeg(raw)
    digest = hashlib.sha256(data).hexdigest()
    directory = photo_dir()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{digest}.jpg"
    if not target.exists():
        handle, temporary = tempfile.mkstemp(dir=directory, suffix=".part")
        with os.fdopen(handle, "wb") as file:
            file.write(data)
        os.replace(temporary, target)
    return digest, len(data)


def read(digest: str) -> bytes:
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise FileNotFoundError(digest)
    data = (photo_dir() / f"{digest}.jpg").read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise FileNotFoundError(digest)
    return data
