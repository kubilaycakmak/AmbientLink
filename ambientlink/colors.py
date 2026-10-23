"""Small RGB samples -> dominant colors, without mixing unrelated hues."""
import numpy as np


def dominant(sample):
    pixels = np.asarray(sample, dtype=np.float32).reshape(-1, 3)
    if not len(pixels):
        return (0, 0, 0)
    value = pixels.max(axis=1)
    usable = value > 12  # Letterbox bars must not dilute the scene.
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


def screen_colors(rgb, mode="zones"):
    if mode == "average":
        result = tuple(int(round(v)) for v in np.asarray(rgb).mean(axis=(0,1)))
        return [result]*3
    if mode == "dominant":
        return [dominant(rgb)]*3
    if mode != "zones":
        raise ValueError("Invalid screen color mode")
    return [dominant(region) for region in np.array_split(rgb, 3, axis=1)]
