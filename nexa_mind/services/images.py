import warnings
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 20_000_000


def normalize_image(upload):
    data = upload.stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("Choose an image under 8 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ValueError("Supported formats are JPEG, PNG, and WebP.")
                if source.width * source.height > MAX_PIXELS:
                    raise ValueError("Choose an image smaller than 20 megapixels.")
                if getattr(source, "is_animated", False):
                    raise ValueError("Choose a still image rather than an animation.")
                source.load()
                oriented = ImageOps.exif_transpose(source).convert("RGBA")
                canvas = Image.new("RGBA", oriented.size, "white")
                canvas.alpha_composite(oriented)
                image = canvas.convert("RGB")
                image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
                return image
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("This file is not a readable image. Choose a valid JPEG, PNG, or WebP.") from exc
