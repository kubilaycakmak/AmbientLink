# AmbientLink 0.3.1 alpha

Automatic Tapo pacing and downloadable local diagnostics are now included by
default. Existing H600B screen-color filtering and crossfades remain shared
across adapters.

## Default behavior

- **Tapo automatically adapts to replies, up to 10 updates/s**, replacing the
  fixed 5 Hz ceiling. Slower replies leave headroom; failed writes reduce the
  rate and hold it down for 10 seconds before successful replies gradually
  restore it. No new tuning is required
  for existing or newly added Tapo lights.
- **No backlog of old colors.** Each light has one acknowledged command in
  flight. When it completes, the sender selects the newest target, skipping
  superseded frames. Different bulbs have independent senders.
- New settings default to **60 capture FPS / 350 ms Transition**. Existing
  timing, zone and calibration choices are preserved. Dark-area brightness,
  small-text filtering and finite non-overshooting crossfades are shared with
  H600B; model-specific gamma/gains are not blindly copied to other hardware.

Tapo L530/L530E remains experimental and physically unverified by this project.
10 Hz is a command ceiling, not a guarantee of visible bulb refresh rate. Firmware
fade behavior and Wi-Fi/device response can still add delay. Physical results
need a real-device diagnostic report and the user's observations.

## Share a problem

1. Run the problematic scene for 30–60 seconds.
2. In **Troubleshooting**, click **Mark issue now** when the issue is visible.
3. Click **Download diagnostics** and send the ZIP with the exact bulb model,
   firmware, approximate delay and whether **Apply color** is also slow.

Device rows show actual changed updates/s, the current adaptive ceiling, last
command time, P95, errors and reconnects. Reports include capture and connection
timings, stable error codes and recent samples. A static scene may legitimately
show zero changed updates/s. Command completion is not optical response time.

Reports exclude passwords, account email, tokens, IP/MAC addresses, device names,
computer/user names, full paths, screenshots and screen colors. Nothing is uploaded
automatically. History is local, limited to two 256 KiB files and at most 500
exported events; timing samples occur every 10 seconds rather than every frame.

## Install

Download **AmbientLink-0.3.1-windows-x64.zip**, extract it and run **AmbientLink.exe**.
Python is included. Windows 10/11 x64 is required. The EXE is unsigned and checksums
are provided in **SHA256SUMS.txt**. Quit the previous version first; saved settings
and protected Tapo credentials are retained without re-pairing.

## Validation

57 automated tests pass, including privacy/ZIP export, bounded persistent logs,
HTTP protections, Tapo error classification, adaptive pacing under fast/slow/failing
replies, automatic rate recovery, no reconnect burst and latest-target delivery after a blocked send.
Existing capture, color, smoothing, BLE and LAN tests remain passing.
Packaged Windows launch and browser report download are also checked.
