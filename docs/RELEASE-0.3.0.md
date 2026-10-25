# AmbientLink 0.3.0 alpha

Downloadable local diagnostics make slow or unreliable lights easier to investigate.
This release preserves the 0.2.2 color transitions and existing device rate limits.

## What changed

- **Download diagnostics** creates a ZIP with app/OS versions, lighting settings,
  per-light counters, command timings and recent sanitized events.
- **Mark issue now** records the moment a problem is visible, alongside a timing
  snapshot. Run the problematic scene for 30–60 seconds before exporting.
- Device rows show changed updates/s against the transport ceiling, last send
  time, P95 send time, errors and reconnects. Reports also include connect time,
  timeouts and capture-to-command age. These are software/transport timings,
  not measured physical bulb response times.
- Tapo connection/update/restore failures have stable diagnostic codes and safe
  error categories. Raw SDK exception messages are not exported.
- Local events survive app restarts, rotate across two 256 KiB files and export
  at most 500 events. Performance samples are taken every 10 seconds while
  controlling lights; there is no per-frame disk logging or automatic upload.

Reports exclude passwords, account email, tokens, IP/MAC addresses, device names,
computer/user names, full paths, screenshots and screen colors. Credential and
settings files are never copied into the ZIP. Lights are numbered in panel order.

## Investigating Tapo delay

Tapo L530/L530E remains experimental, with a conservative **5 Hz** send ceiling.
It has not been physically validated by this project. Lack of Bluetooth alone
does not explain a delay; acknowledgement time, network conditions, smoothing
and device firmware behavior can contribute. This release adds measurements,
not a claimed hardware latency fix or a higher send rate.

Compare **Apply color** with **Start screen sync**, then mark/export the issue.
Send the report with the exact model, firmware, approximate delay and whether
manual colors are also delayed. A static scene may legitimately show 0 updates/s.

## Install

Download **AmbientLink-0.3.0-windows-x64.zip**, extract it and run **AmbientLink.exe**.
Python is bundled. Windows 10/11 x64 is required. The EXE is unsigned; checksums
are provided in **SHA256SUMS.txt**.

Quit the previous AmbientLink instance before replacing it. Existing settings and
DPAPI-protected Tapo credentials remain in the Windows user data directory; no
re-pairing is required. Avoid running another controller against the same bulbs.

## Validation

53 automated tests pass, including report privacy, bounded logs, persistence,
unwritable-history fallback, HTTP Host/Origin/CSRF protections, ZIP export,
Tapo timeout categorization and sender recovery/timing counters. Existing
capture, color, pacing and device tests remain passing. Hardware performance
for the friend's Tapo installation will be assessed from a real diagnostic report.
