# AmbientLink

Turn supported RGB lights into Windows screen lighting. Runs locally from one
EXE and opens a control panel in your browser. No Echo, Home Assistant or separate server is required. Govee needs no account; Tapo uses your Tapo account to authenticate directly with the light on your local network.

**0.3.2 alpha — Windows 10/11 x64, primary monitor only.** The H600B transport
comes from a working hardware setup; this standalone app is an early release,
not universal RGB support. Govee LAN output still needs physical validation.

## Download for Windows

**[Download AmbientLink.exe](https://github.com/kubilaycakmak/AmbientLink/releases/download/v0.3.2/AmbientLink.exe)** · [ZIP with licenses and README](https://github.com/kubilaycakmak/AmbientLink/releases/download/v0.3.2/AmbientLink-0.3.2-windows-x64.zip)

[Release notes and all downloads](https://github.com/kubilaycakmak/AmbientLink/releases/tag/v0.3.2)
· [All releases](https://github.com/kubilaycakmak/AmbientLink/releases)

Download the **Windows ZIP above**, not GitHub's automatically generated
"Source code" ZIP. Right-click the download, select **Extract All**, and run
`AmbientLink.exe` from the extracted folder. Keep the included license files
with it. Python is bundled; no separate Python installation is needed.

The EXE opens a local control panel in your default browser. That browser tab
is the app's interface; there is no separate native window or tray icon in 0.3.2.
No administrator access is required for normal use. Tapo requires its account credentials.

The build is unsigned. Windows SmartScreen may show an unknown-publisher warning.
Download only from this repository's Releases page and verify the release hash
if needed. Checksums identify a file; they do not establish publisher identity.

### Requirements

- Windows 10 or 11, **64-bit x64**. ARM64 and macOS builds are not provided.
- A supported RGB light (see the table below), powered on and within range.
- For H600B: a working Bluetooth LE adapter with Bluetooth enabled in Windows.
- For Govee LAN: the PC and light on the same local network, with **LAN Control**
  enabled for a model that provides it. Wi-Fi support alone is not sufficient.
- An unlocked Windows desktop and the primary monitor displaying the content.

## Devices

| Adapter | Support | Transport |
| --- | --- | --- |
| Govee H600B | Based on live-tested encrypted BLE transport | Bluetooth LE, acknowledged writes, up to 30 Hz |
| Govee LAN Control | Experimental; model and firmware dependent, physical validation pending | Local UDP, up to 10 Hz; no delivery acknowledgement |
| Tapo L530 / L530E | Experimental adapter; **not physically tested** | Authenticated local LAN, adaptive, up to 10 requests/s; actual rate depends on firmware/network |
| Other Govee BLE models / other brands | Not yet supported | Add a model-specific adapter |

Bluetooth and Wi-Fi are transports, not a common lighting protocol. A device
must implement one of the supported protocols. No firmware is replaced.

## Quick start

1. Unzip the Windows package and run **AmbientLink.exe**. Python is bundled.
2. Leave Bluetooth on and close other applications controlling the same bulbs.
3. Click **Find lights**, then add the devices you own. For supported Govee LAN
   models, enable **LAN Control** in Govee Home first. A private IPv4 address can
   also be entered manually.
4. Choose dominant color for the room or left/center/right screen regions. Assign
   each light to a region, set brightness, and click **Start screen sync**.
5. Use **Match** to visually adjust RGB channel gains and LED transfer correction.
   Use a dim room and several reference colors. This is not instrument calibration.

For H600B, set the bulb to a **solid RGB color** in Govee Home once before the
first connection, then close Govee Home and other light controllers. You do not
need to remove the bulb from your Govee account. Do not run another Ambilight
application against the same bulbs at the same time.

### Add a Tapo L530E (experimental)

1. Set up the bulb in the Tapo phone app and select a solid color. AmbientLink does not pair an unconfigured bulb or restore dynamic effects.
2. Put the PC and bulb on the same reachable local network. Find the bulb's private IPv4 address in your router or Tapo device information; a DHCP reservation prevents address changes.
3. Click **Add Tapo**, enter that IP, a name, and the email/password used in Tapo. This is local device authentication, not an AmbientLink account. If connection fails, also check the Tapo **Third-Party Compatibility** setting available on some firmware.
4. Click **Save & add light**, select its screen region, then **Start screen sync** or **Apply color**. Adding a row alone does not verify connectivity. The device row shows connection failures.
5. Use **Add Tapo → Forget account** to remove the saved credentials. Changing/removing the account stops active Tapo control. One saved Tapo account is shared by added Tapo lights.

Credentials are encrypted with Windows DPAPI for the current user in
`%LOCALAPPDATA%/AmbientLink/tapo-credentials.dpapi`. They are not returned by the
panel API, written to `settings.json`, included in exports, or shipped in releases.
Do not share this file. Moving the app to another Windows account requires entering
credentials again. Gamma correction starts disabled for Tapo; use **Match** only
if needed. Neutral RGB uses the bulb's 6500 K white mode.

The adapter uses the MIT-licensed [tapo client](https://github.com/mihai-dinculescu/tapo).
Command conversion, deduplication, reconnect/restore and secret storage have automated
tests. **L530E physical response, firmware compatibility and sustained update rate
have not been verified on our hardware.** The adaptive 10 Hz ceiling is a software limit, not a measured physical rate;
60 capture FPS does not mean 60 Tapo updates per second.

### Choose how colors follow the screen

| Control | What it does |
| --- | --- |
| One dominant color for every light | All enabled lights follow the same representative screen color. |
| Left / center / right regions | Each light follows the region assigned in its device row. Change the region to swap physical positions. |
| Average screen color | Uses the screen's average color; mixed scenes can look less saturated. |
| Brightness | Sets the overall output level. Start around 40–60% in a dim room. |
| Capture FPS | Requests 15, 30 or 60 screen samples per second. This is not the number of physical light updates. |
| Transition (ms) | Sets the finite color transition window. Defaults to 350 ms; a stable target completes within this window (minimum 180 ms), or at least 450 ms when brightening. Full black fades faster. Capture stalls and device transport add latency. |
| Apply color | Stops screen sync and applies the selected manual color. |
| Device Turn on / Turn off | Includes or excludes that device without reconnecting other lights. |

Try a video with large, clear color areas first. For a three-light layout, assign
one light to **Left**, one to **Center**, and one to **Right**, then select the
regional mode. Full-screen video avoids including browser controls in the sample.

### Match colors to your bulbs

1. Work in a dim room and click **Stop & restore**.
2. Click **Match** on a device and choose a reference color.
3. Click **Save & test color** to compare the light with the on-screen patch.
4. Adjust the red, green and blue gains for that device and test again. Try several
   colors, including a warm tone and a neutral gray, before settling on a setting.
5. Close the dialog and click **Start screen sync** to return to Ambilight.

**LED transfer correction** is enabled by default for H600B and can change mixed
colors substantially. The test color is sent to all enabled lights, but gains
and transfer correction apply to the device whose Match dialog is open.
Monitor settings, wall color and LED hardware affect the result; visual matching
cannot guarantee colorimeter-level accuracy.

### Stop, switch off, or exit

**Stop & restore** restores the captured H600B or Tapo solid-color/white-temperature, brightness and power state while the connection is available. Govee LAN devices keep their last output because that adapter has no verified original-state readback. **Lights off** explicitly
sends black/power-off. **Quit app** stops the worker and closes its connections.
Closing the browser tab alone leaves the app running; reopening the EXE returns
to its panel. No startup task is installed and screen capture never starts merely
because the EXE was launched.

Because quitting attempts to restore the original H600B state, **Lights off**
followed by **Quit app** may turn a previously lit H600B back on. Use the stop and
restore behavior intentionally when handing control back to another application.

## Troubleshooting

| Problem | Try this |
| --- | --- |
| No H600B found | Check power and Bluetooth, move the PC/adapter closer, close other controllers, then use Find lights again. A bulb already connected elsewhere may not advertise. |
| A solid RGB color is requested | Set a solid color in Govee Home, exit that app, then retry. The app cannot safely restore every vendor scene mode. |
| No LAN devices found | Check LAN Control and local-network reachability. Try Add LAN address using the bulb's private IPv4 address. Some networks block multicast discovery. |
| LAN says UDP unconfirmed | The app has sent commands, but the protocol provides no delivery confirmation here. Verify the actual light response; unsupported models may ignore commands. |
| Lights update slowly or disconnect | Compare the device update/send timings with Capture FPS, move the PC/adapter closer, and test with one light. Compare 30 and 60 capture FPS; lowering capture FPS alone does not increase radio throughput. 60 capture FPS does not mean 60 bulb updates per second. |
| Colors look pink, washed out or inaccurate | Use Match in a dim room and compare several colors. Check LED transfer correction and reset gains if needed. HDR is not color-managed in this release. |
| Capture stops or reports an error | Unlock Windows and click Start screen sync again. Protected video, remote sessions and display changes can prevent DXGI capture. |
| The browser says App disconnected | Run AmbientLink.exe again. Closing the app ends its local web server. |

### Share a diagnostic report

1. Open the **Troubleshooting** card below Connected lights.
2. Run the scene that shows the problem for **30–60 seconds**. Click **Mark issue
   now** when you notice a delay, flicker or connection failure.
3. Click **Download diagnostics**. Share the downloaded ZIP with the maintainer
   or attach it to a [GitHub issue](https://github.com/kubilaycakmak/AmbientLink/issues).
4. In your message, include the exact bulb model/firmware, roughly how many
   milliseconds or seconds it lags, and whether **Apply color** also feels slow.

The ZIP includes app/Windows versions, tuning settings, per-light timing and
error counters, safe error codes/source locations, and recent samples taken every
10 seconds while controlling lights. An issue marker captures an extra sample.
Lights are numbered in panel order. Errors and connection events are recorded
when they happen; the report can include previous sessions.

**Nothing is uploaded automatically.** Reports exclude passwords, tokens, account
email, IP/MAC addresses, device names, computer/user names, full paths, raw exception
messages, screenshots and sampled colors. They do not copy `settings.json` or the
credential file. Local history lives in `%LOCALAPPDATA%\AmbientLink\diagnostics`
and rotates between two 256 KiB files; exports include at most 500 recent events.
To erase local history, quit AmbientLink and delete that diagnostics folder.

### Tapo cannot connect

Version 0.3.2 fixes an overly short **3-second HTTP timeout during login**. Initial
HTTP requests now allow 10 seconds, with a 30-second overall login limit and a
separate 10-second settings read. Color updates still have a 3-second deadline;
the startup allowance does not queue delayed colors or slow normal sends.

Before login, a bounded **unicast discovery query** targets only the configured
bulb IP. This can wake the local API on firmware that starts it after discovery.
It sends no account credentials and does not re-pair or reset the bulb. If UDP
does not reply, normal HTTP login is still attempted. A discovery reply alone
does not prove that HTTP authentication will work.

- **Connection timed out / network request failed:** verify the current bulb IP
  in the router or Tapo app. The PC must be able to reach the bulb locally;
  successful phone/cloud control does not prove that. Check guest Wi-Fi/client
  isolation and whether the VPN permits local LAN traffic.
- **Account rejected:** stop control and save the exact case-sensitive Tapo
  email/password again through Add Tapo. Then restart screen sync.
- **Local access denied (403):** check Third-Party Compatibility in the Tapo app
  if available for that firmware, then stop and restart control.
- **Login locked / unsupported protocol:** repeated login attempts are paused.
  For a lockout, correct the account and allow the bulb's lockout to expire before
  restarting. For unsupported firmware, share diagnostics and the firmware version.

Reports now distinguish timeout, network, account, access-denied, lockout and
unsupported-protocol errors, plus the login/settings-read stage and whether
discovery replied. Raw SDK messages and private network details remain excluded.
If the problem continues, send a **new report from 0.3.2**: older reports cannot
recover details that were already removed. Real Tapo hardware remains unverified.

### Tapo is slow: what to compare

L530E uses local 2.4 GHz Wi-Fi. Wi-Fi itself does not establish whether a light is
faster or slower than Bluetooth. This adapter waits for command acknowledgement
and now automatically adjusts sends up to **10 Hz** (at least 100 ms between command starts).
Slower replies reduce the rate with headroom; failed writes reduce it further,
then successful replies gradually restore the rate. There is one in-flight
command per bulb, and the next send uses the newest target. Capture FPS, the Transition setting, the
network, device processing and firmware fade behavior can all contribute to what
you see. The optimized sender is the default for existing and new Tapo lights. New
settings use 60 capture FPS and a 350 ms transition; saved timing/calibration
choices are preserved. The area-weighted dark-scene filter and bounded,
non-overshooting crossfades used by H600B are shared across adapters.
Hardware-specific gamma/gains are not blindly copied between bulb models.
This reduces the previous software ceiling but does **not** establish physical
Tapo performance without a real-device report.

- Compare **Apply color** with screen sync. Manual color skips screen capture and
  interpolation, helping separate those from transport/device delay.
- Read **ms last**, **ms P95**, errors and reconnects in the light's row. P95 is
  the 95th-percentile send time over the last 120 successful changed writes.
- Try one bulb on the same reachable network with other light controllers closed.
  If sends take seconds or repeatedly time out, export diagnostics while it happens.
- A low command time with a visibly slow physical response needs a description or
  optional video from the user: the app cannot measure the bulb's optical response.

### Verify a download

Download `SHA256SUMS.txt` from the same release. In PowerShell, compute the ZIP's
hash and compare it with the matching filename in that checksum file:

```powershell
Get-FileHash .\AmbientLink-0.3.2-windows-x64.zip -Algorithm SHA256
```

## Performance and privacy

Capture targets 15/30/60 FPS. Hardware update rates depend on the radio, firmware,
and number of lights. Each light has an independent sender with only the latest
target; no queue of stale video colors is accumulated. Black scenes have a faster
fade than normal cuts. Dark pixels now count toward each region's brightness:
10% white text on a 90% black background produces approximately 10% white output,
not a fully bright light. Area-filtered sampling reduces thin-text color aliasing;
only very small near-neutral color biases are neutralized. Modest symmetric black
movie bars are cropped when the remaining content is sufficiently lit; sparse title
cards and dark screen regions are preserved. Transitions now interpolate LED channel levels for devices with transfer correction,
so mixed intermediate colors are not boosted back to full brightness. Each device
has its own transition state after its RGB gains; devices with correction disabled
use raw RGB interpolation. New samples replace the target instead of queuing old
video colors. A stable target completes a finite ramp rather than trailing for
seconds. Full black still fades quickly. The H600B version of this algorithm was
compared on a live three-bulb setup; this does not validate every adapter or firmware.

Each device row shows **updates/s** against its transport ceiling, **ms last**,
**ms P95**, errors and reconnects. Updates/s counts changed outputs over the last
three seconds. These are local diagnostics, not
optical measurements or a guaranteed hardware refresh rate. A static scene can
correctly show zero updates/s. UDP output remains unconfirmed.

The UI binds to `127.0.0.1` on a random port, checks Host/Origin and requires a
request token for changes. Images are sampled in memory; they are not saved or
uploaded. There is no telemetry. Device addresses, names and calibration live
only in `%LOCALAPPDATA%\AmbientLink\settings.json`. Do not attach that file to a
public issue without removing addresses and personal labels.

DXGI capture can fail on a locked desktop, protected video or display changes.
HDR color management, multi-monitor selection, per-zone LAN segments and
automatic startup are not implemented. Keyboard, mouse, motherboard and fan RGB
integrations are not included in this standalone release. These are separate
roadmap items.

## Build from source

Use Python 3.12 x64 on Windows:

```powershell
git clone https://github.com/kubilaycakmak/AmbientLink.git
cd AmbientLink
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe run.py
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
```

The build script runs tests before producing `dist/AmbientLink.exe`, a ZIP, and
SHA-256 checksums. The process-local execution-policy argument does not change
the system policy. CI builds Windows artifacts on manual dispatch and version tags.

## Add an adapter

Implement `connect()`, `send(rgb, brightness)`, `close(restore=True)` and `rate`,
then register the class in `ambientlink/drivers.py`. Add strict configuration
validation, discovery and packet tests. Document exact models, required setup,
physical test results, state restoration and transport rate limits. Never claim
an entire brand is supported from one matching device name.

Planned adapters: WiZ, WLED, Philips Hue and additional Govee models. Contributions
should use documented local protocols where available. Cloud-only control is a
poor fit for video-rate output and is not silently substituted.

MIT licensed. See [THIRD_PARTY.md](THIRD_PARTY.md) for protocol research and dependencies.
AmbientLink is an independent project, not affiliated with Govee or Philips.
