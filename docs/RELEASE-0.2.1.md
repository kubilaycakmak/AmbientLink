# AmbientLink 0.2.1 alpha

Dark scenes now dim at the original response speed. Version 0.2.0's additional
brightness smoothing also slowed dimming into dark gray, leaving the room too
bright after a scene cut. The slower envelope now applies only when brightening.
Full-black fade, area-based brightness and neutral-text filtering are unchanged.

This does not increase the configured smoothing delay or change Bluetooth transport.
The regression suite contains 23 passing tests, including bright-to-dark-gray
transitions and the separate brightening envelope.

Includes the experimental Tapo L530/L530E adapter introduced in 0.2.0, **still
pending physical hardware validation**. Use Add Tapo with a local IP and your
Tapo account. The English README covers setup and Windows-encrypted credential storage.

Extract `AmbientLink-0.2.1-windows-x64.zip` and run `AmbientLink.exe`.
Windows 10/11 x64; unsigned portable executable; Python is bundled.
