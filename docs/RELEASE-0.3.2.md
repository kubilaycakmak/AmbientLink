# AmbientLink 0.3.2 alpha

Fixes the overly short Tapo login timeout and adds actionable connection errors.

## Fixes

- Initial Tapo HTTP requests allow 10 seconds instead of 3, with an overall
  30-second login limit. Reading original bulb settings has its own 10-second
  deadline. Normal color-command deadlines remain 3 seconds.
- A short, credential-free discovery query targets the configured bulb before
  login. This can wake firmware that initializes its local API after discovery;
  no response still falls through to normal login. No reset or re-pairing occurs.
- Generic exceptions from the native Tapo SDK are classified into timeout,
  network, rejected account, HTTP 403, login lockout and unsupported protocol.
  The panel shows the corresponding action instead of one generic connection error.
- Rejected accounts, lockouts and unsupported protocols pause automatic retries
  until control is stopped and restarted, avoiding repeated bad logins.
- Exported diagnostics include the connection stage, discovery outcome and retry
  pause. Timeouts now increment the timeout counter correctly. Packaged source
  locations are retained where available. Raw errors, credentials, IP addresses
  and discovery payloads remain excluded.

## Updating and checking

Quit the previous AmbientLink instance, download **AmbientLink.exe** (or extract
the Windows ZIP), and run the new EXE. Existing settings and protected credentials
are preserved. No Python installation is required. Windows 10/11 x64 is required;
the EXE is unsigned and SHA256SUMS.txt is supplied.

If a bulb still cannot connect, check its current IP and PC-to-bulb LAN access,
including VPN or guest-network isolation. Phone-app/cloud control alone does not
verify local PC access. Download a new diagnostic ZIP from 0.3.2 and include the
bulb's model and firmware version when reporting it.

The triggering report showed both bulbs failing before any successful connection
or color write, consistently near the previous 3-second HTTP limit. The old
report did not preserve the underlying SDK error, so it cannot establish whether
the original network, firmware or account was responsible. This release fixes
the software timeout/reporting defects; physical Tapo results still need retesting.

## Validation

75 automated tests pass, including a real native-SDK timeout against a local test
HTTP server, a login lasting longer than the previous deadline, optional unicast
discovery/fallback/cancellation, paused authentication retries, privacy-preserving
report export, adaptive pacing and the existing capture/color/transport tests.
The packaged EXE is smoke-tested with an isolated, empty profile; no physical
Tapo hardware is claimed as verified.
