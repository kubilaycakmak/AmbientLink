# AmbientLink 0.2.0 alpha

## Screen lighting

- Dark pixels now contribute to region brightness. Sparse white text no longer
  drives an otherwise black region at full output.
- Area-filtered capture reduces thin-text/subpixel color aliasing. Tiny neutral
  color fringes are neutralized before per-device transfer correction.
- Conservative letterbox detection preserves dark regions and title cards.
- Color easing now has a separate, slower brightness envelope. Hue crossfades
  maintain their light level; completely black scenes still extinguish quickly.
- Capture still targets up to 60 FPS. Actual bulb update rate depends on hardware.

## Experimental Tapo L530E

- Add L530/L530E bulbs by private LAN IPv4 address using **Add Tapo**.
- Tapo account credentials authenticate the local connection and are stored
  separately with Windows user-bound DPAPI encryption. **Forget account** removes
  them. No user credentials are shipped in this release.
- RGB/brightness/power are combined into acknowledged commands, capped at 5/s.
  Latest-target scheduling avoids a backlog of old colors.
- Stop attempts to restore the captured solid-color or white-temperature state,
  brightness and power. Dynamic effects must be disabled in Tapo first.
- Implemented with the MIT-licensed `tapo` client; AmbientLink remains MIT.

**Tapo physical validation is pending.** No L530E was available during development.
Automated tests cover conversion, command deduplication, reconnect/restore,
model/effect checks, credential encryption and API secrecy. These do not establish
real-device firmware compatibility, color fidelity or sustained update rate.

## Download and use

Extract `AmbientLink-0.2.0-windows-x64.zip`, then run `AmbientLink.exe`.
Windows 10/11 x64; Python is included. Close other applications controlling the
same bulbs. The package is unsigned. SHA-256 checksums accompany the download.
See the English README for setup, color matching and troubleshooting.
