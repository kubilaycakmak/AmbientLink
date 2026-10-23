# AmbientLink 0.2.2 alpha

Screen lighting transitions should no longer manufacture a bright intermediate
color or trail through old colors for seconds after a scene change.

## Changes

- **LED-aware crossfades.** With LED transfer correction enabled, interpolate the
  effective LED channel levels instead of boosting every intermediate hue to its
  maximum channel. This reduces the brightness hump seen in mixed-color cuts.
- **Finite transitions.** New samples replace the target. Once the target is
  stable, the color ramp finishes within the configured transition window, with
  a minimum of 180 ms for ordinary changes and 450 ms for brightening. Full black
  retains its faster fade. Radio delays and capture stalls add latency.
- **Independent device matching.** Apply each light's RGB gains before its own
  transition. Devices with correction disabled interpolate raw RGB. Changing
  these settings or a region does not reconnect the other lights.
- **Local delivery diagnostics.** Device rows show changed updates per second
  over a three-second window and the last send duration. A static scene can show
  zero updates/s. These are transport measurements, not optical response times;
  Govee LAN output remains unconfirmed.
- The English README explains the new Transition control, diagnostics and the
  difference between screen capture FPS and actual light updates.

The transition algorithm was compared on a three-H600B setup: the owner reported
reduced flashing and improved tracking. Bluetooth stepping can still occur;
60 capture FPS is not a promise of 60 physical bulb updates per second. Govee
LAN and Tapo L530/L530E remain experimental and have not been physically verified
by this project. This release does not add new device models.

## Download and run

Download **AmbientLink-0.2.2-windows-x64.zip**, extract it, then run
**AmbientLink.exe**. Python is included. Windows 10/11 x64 is required; the EXE is
unsigned. Use `SHA256SUMS.txt` to verify the download.

Close the previous AmbientLink instance before replacing it. Existing settings
and saved Tapo credentials stay in your Windows user data directory; no migration
or re-pairing is required. Stop any other application controlling the same bulbs
before starting screen sync.

Start with **60 Capture FPS** and **280–350 ms Transition**, then compare using
the same scene. The Match dialog, per-light RGB gains, region assignments, manual
colors and Tapo credential controls remain available.

## Validation

Automated tests cover corrected/raw interpolation, no modeled light-level
overshoot, bounded settling after multiple scene changes, fast black transitions,
calibration round trips, mixed device settings, live controls, slow transports,
HTTP protections and the experimental Tapo adapter. Hardware-wide compatibility
and optical timing are not established by these tests.
