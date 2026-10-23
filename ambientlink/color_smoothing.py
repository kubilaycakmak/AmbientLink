"""Crossfade actual LED channel levels, avoiding peaks from hue normalization."""
import math


def linear(value):
    value = value/255
    return value/12.92 if value <= .04045 else ((value+.055)/1.055)**2.4


def drive(rgb):
    peak = max(rgb)
    if peak <= 0:
        return (0., 0., 0.)
    maximum = linear(peak)
    return tuple(peak*linear(c)/maximum for c in rgb)


def encode(channels):
    """Inverse of the existing corrected RGB + dimmer transfer (before rounding)."""
    peak = max(channels)
    if peak <= 0:
        return (0., 0., 0.)
    maximum = linear(peak)
    result = []
    for channel in channels:
        value = maximum*channel/peak
        srgb = 12.92*value if value <= .0031308 else 1.055*value**(1/2.4)-.055
        result.append(max(0., min(255., srgb*255)))
    return tuple(result)


class LinearLightSmoother:
    def __init__(self, tau=.35, corrected=True):
        self.tau = tau
        self.corrected = corrected
        self.channels = None
        self.levels = None
        self.anchors = None
        self.remaining = None

    def update(self, colors, elapsed):
        targets = [drive(rgb) if self.corrected else tuple(rgb) for rgb in colors]
        if self.channels is None:
            self.channels = targets
            self.levels = [max(rgb) for rgb in colors]
            self.anchors = list(targets)
            self.remaining = [0.]*len(colors)
            return [tuple(rgb) for rgb in colors]
        # Permit the public app's 15 FPS mode, but a capture stall must not
        # consume a whole transition in one step.
        dt = max(0., min(elapsed, .1))
        for i, (rgb, target) in enumerate(zip(colors, targets)):
            dark = max(rgb) <= 5
            changed = max(abs(a-b) for a,b in zip(target,self.anchors[i])) > 2
            if changed:
                rising = max(rgb) > self.levels[i]+2
                self.remaining[i] = max(.45 if rising else .18, self.tau)
                self.anchors[i] = target
                self.levels[i] = max(rgb)
            if dark:
                alpha = 1-math.exp(-dt/.035)
                self.remaining[i] = 0.
            else:
                # Retarget from the current output to the newest sample. There
                # is no frame history to replay. When a target stops changing,
                # finish the ramp in a bounded time instead of an exponential
                # tail lasting seconds. Tiny sampling noise cannot restart it.
                remaining = self.remaining[i]
                alpha = min(1., dt/remaining) if remaining > 1e-9 else float(dt>0)
                self.remaining[i] = max(0., remaining-dt)
            old = self.channels[i]
            delta = [alpha*(b-a) for a,b in zip(old,target)]
            # One common interpolation fraction: every intermediate LED vector
            # stays between the current output and target. Do not normalize its
            # peak back up; that manufactured a bright flash during hue changes.
            value = tuple(a+d for a,d in zip(old,delta))
            if dark and dt > 0 and max(abs(a-b) for a,b in zip(value,target)) < .5:
                value = target
            self.channels[i] = value
        return [encode(value) if self.corrected else tuple(value) for value in self.channels]
