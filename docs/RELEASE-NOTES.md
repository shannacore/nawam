# Nawam 1.0.2 — safety and usability fixes

Copyright © 2026 Shanna Studio.
Website: https://nawam.shanna.id

## New appearance

Single-panel native interface with a Nawam header, original USB logo, wider
controls and blue accents. No browser runtime or large UI framework is added.

## Fixed

- Boot-mode question mark opens the current help explanation when clicked.
- License dialog fits the monitor work area at tested DPI layouts.
- Startup describes this unsigned/custom build accurately, with No as default.
- Shared application-lock warnings identify conflicting disk utilities clearly.
- Security-data refresh has separate manual consent, dialog ownership, idle-state
  checks and device-list refresh after completion. Executable self-update stays off.
- Download lengths/chunks, HTTP errors and HTTPS downgrades fail closed.
- Security metadata is validated before use. DBX cache replacement is atomic.
- Build/source provenance prevents packaging stale executable/source combinations.

## Downloads

- Nawam.exe: compact x64 executable.
- Nawam-unpacked.exe: x64 executable without compression.
- Nawam-1.0.2-source.zip: corresponding source and build instructions.
- SHA256SUMS.txt: package checksums.

## Verification and limits

41 automated regression tests passed before the clean release build, including
compiled native-C tests and failure-path tests. PE, resources and compression
integrity are checked separately. No automated physical USB write or boot test.
This is a prerelease, not a guarantee of compatibility with every ISO or USB.

The executable is unsigned. Windows may display Unknown publisher.
Security-data trust uses HTTPS sources and structural checks; it is not independent
cryptographic verification of EFI authentication signatures. Some upstream data
sources can be unavailable, producing a partial refresh; inspect the log.

License information and component attributions are in NOTICE.md, LICENSE.txt,
the source, and the License & Open Source dialog. No license notices were removed.
