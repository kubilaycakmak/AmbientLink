"""Small RGB samples -> dominant colors, without mixing unrelated hues."""
import numpy as np


def _hue(sample):
    pixels = np.asarray(sample, dtype=np.float32).reshape(-1, 3)
    if not len(pixels):
        return (0, 0, 0)
    value = pixels.max(axis=1)
    usable = value > 12
    if usable.sum() < max(1, len(pixels) * .015):
        return (0, 0, 0)
    pixels, value = pixels[usable], value[usable]
    low = pixels.min(axis=1)
    delta = value-low
    saturation = delta / np.maximum(value, 1)
    chromatic = saturation > .22
    # Neutral/muted areas must compete with colorful areas. Previously 12%
    # saturated pixels excluded every neutral pixel and could tint a mostly
    # gray film scene pink. Count area with only a small brightness preference;
    # saturation must not let a small vivid accent defeat the main scene.
    weights = .85 + .15*np.sqrt(value/255)
    neutral = ~chromatic
    if not chromatic.any():
        return tuple(int(round(v)) for v in np.average(pixels,axis=0,weights=weights))
    rgb, v, d, sat = pixels[chromatic], value[chromatic], delta[chromatic], saturation[chromatic]
    maximum = rgb.argmax(axis=1)
    hue = np.zeros(len(rgb), dtype=np.float32)
    for channel, offset, a, b in ((0,0,1,2),(1,2,2,0),(2,4,0,1)):
        mask = maximum == channel
        hue[mask] = (offset + (rgb[mask,a]-rgb[mask,b])/d[mask]) % 6
    bins = np.floor(hue*6).astype(int) % 36
    color_weights = weights[chromatic]
    histogram = np.bincount(bins, weights=color_weights, minlength=36)
    # Score the same hue neighborhood that will supply the final color. A
    # broad main hue should not lose to a narrow, highly saturated accent.
    score = sum(np.roll(histogram,offset) for offset in range(-2,3))
    winner = int(score.argmax())
    if neutral.any() and weights[neutral].sum() >= score[winner]:
        color = np.average(pixels[neutral],axis=0,weights=weights[neutral])
        return tuple(int(round(v)) for v in color)
    distance = np.minimum((bins-winner)%36, (winner-bins)%36)
    chosen = distance <= 2
    color = np.average(rgb[chosen], axis=0, weights=color_weights[chosen])
    return tuple(int(round(v)) for v in color)


def dominant(sample):
    """Choose a hue by area, but keep the whole region's light level."""
    pixels = np.asarray(sample, dtype=np.float32).reshape(-1, 3)
    if not len(pixels):
        return (0, 0, 0)
    color = np.asarray(_hue(sample), dtype=np.float32)
    peak = float(color.max())
    if peak <= 0:
        return (0, 0, 0)
    # Dark pixels count toward brightness, even though they have no useful hue.
    # Small subtitles/highlights must never light an otherwise black region fully.
    level = min(peak, float(pixels.max(axis=1).mean()))
    # Suppress tiny neutral fringes before device gamma amplifies them. Keep
    # visibly colored scenes intact; this is not a guessed hardware white point.
    if (peak-float(color.min()))/peak <= .06:
        color[:] = peak
    return tuple(int(round(v)) for v in color * (level/peak))


def content_area(rgb):
    """Remove modest symmetric horizontal letterboxing, never isolated text."""
    rgb = np.asarray(rgb)
    if rgb.ndim != 3 or not rgb.shape[0] or not rgb.shape[1]:
        return rgb
    lit = rgb.max(axis=2) > 12
    rows = lit.any(axis=1)
    indices = np.flatnonzero(rows)
    if not len(indices):
        return rgb
    top, bottom = int(indices[0]), len(rows)-1-int(indices[-1])
    if (top >= 2 and bottom >= 2 and abs(top-bottom) <= 2
            and max(top,bottom) <= len(rows)*.24
            and lit[top:len(rows)-bottom].mean() >= .45):
        return rgb[top:len(rows)-bottom]
    return rgb


def screen_colors(rgb, mode="zones"):
    rgb = content_area(rgb)
    if mode == "average":
        result = tuple(int(round(v)) for v in np.asarray(rgb).mean(axis=(0,1)))
        return [result]*3
    if mode == "dominant":
        return [dominant(rgb)]*3
    if mode != "zones":
        raise ValueError("Invalid screen color mode")
    return [dominant(region) for region in np.array_split(rgb, 3, axis=1)]
