"""Opt-in LED output transfer, applied after screen selection and smoothing.

The owner verified the warm mixed-color reference on H600B and Basilisk V3 Pro.
This is a transfer correction, not a measured gamut/white-point calibration.
"""

LINEAR = tuple(v/255/12.92 if v/255 <= .04045 else ((v/255+.055)/1.055)**2.4
               for v in range(256))


def led_output(rgb, brightness, enabled=False):
    """Return bulb RGB and separate dimmer, preserving the requested peak level."""
    if not enabled:
        return tuple(rgb), brightness
    peak = max(rgb)
    if not peak or not brightness:
        return (0, 0, 0), 0
    maximum = LINEAR[peak]
    color = tuple(round(255*LINEAR[c]/maximum) for c in rgb)
    return color, max(1, round(brightness*peak/255))


def desk_output(rgb, brightness, enabled=False):
    """Same transfer for devices whose dimmer is encoded in the RGB channels."""
    peak = max(rgb)
    if not enabled or not peak:
        return tuple(round(c*brightness/100) for c in rgb)
    normalized = tuple(round(255*LINEAR[c]/LINEAR[peak]) for c in rgb)
    return tuple(round(c*peak/255*brightness/100) for c in normalized)
