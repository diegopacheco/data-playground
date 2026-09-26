import colorsys

import daft
import numpy as np
from daft import DataType

import embed

FEATURES = DataType.struct({
    "dominant_color": DataType.string(),
    "dominant_hex": DataType.string(),
    "brightness": DataType.float64(),
    "saturation": DataType.float64(),
})

EMBEDDING = DataType.embedding(DataType.float32(), embed.DIM)

HUES = [(15, "red"), (40, "orange"), (70, "yellow"), (170, "green"), (260, "blue"), (300, "purple"), (345, "pink"), (360, "red")]


def color_name(hue, saturation, value):
    if saturation < 0.25:
        if value < 0.3:
            return "black"
        return "white" if value > 0.85 else "gray"
    return next(name for limit, name in HUES if hue * 360 < limit)


def dominant_rgb(pixels):
    keys = (pixels[:, 0] >> 3).astype(np.int32) << 10 | (pixels[:, 1] >> 3).astype(np.int32) << 5 | (pixels[:, 2] >> 3).astype(np.int32)
    mode = np.bincount(keys).argmax()
    return pixels[keys == mode].mean(axis=0)


@daft.func(return_dtype=FEATURES, unnest=True)
def image_features(thumbnail: np.ndarray):
    pixels = thumbnail.reshape(-1, 3)
    r, g, b = dominant_rgb(pixels)
    hue, saturation, value = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    return {
        "dominant_color": color_name(hue, saturation, value),
        "dominant_hex": "#{:02x}{:02x}{:02x}".format(round(r), round(g), round(b)),
        "brightness": round(value * 100, 1),
        "saturation": round(saturation * 100, 1),
    }


@daft.func.batch(return_dtype=EMBEDDING)
def text_embedding(texts):
    return np.array(embed.passages(texts.to_pylist()), dtype=np.float32)
