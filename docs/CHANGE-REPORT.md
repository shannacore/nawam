# Nawam — change and verification report

## 1.0.2 safety and single-panel design update

Main window has a native Nawam header with the original USB logo, a wider
single-panel layout, and blue accents. All main control identities, sequence
and operation states remain. Native theme/high-contrast handling is preserved.

Added validated manual security-only refresh, owned consent/result dialogs,
main-command gating, and media refresh on gate release. Bounded network reads,
atomic DBX caching, clear unsigned-build notice, clickable boot help and
monitor-fitted license layout are regression-tested. Build provenance and
compression validation are mandatory. Full physical media/boot certification
is not claimed; the release remains a prerelease. See RELEASE-NOTES.md.
Solution/project display filenames are Nawam.sln and .vs/Nawam.vcxproj.
Original source attribution and sensitive internal boot identifiers are retained.

## 1.0.1 identity update

Executable publisher/CompanyName is now Shanna Studio. About has copyright only,
without the Developed by line. Application links use https://nawam.shanna.id.
The website still runs at https://nawam.web.app; custom-domain DNS is owner-managed.
Version resources/title use 1.0.1. Internal SHANNA Digital Systems settings namespace
is unchanged. No disk algorithms changed. 13 regression tests pass and a fresh
x64 build verifies CompanyName, website, version and PE security flags.

## Initial 1.0.0 implementation

## Source isolation

Original reference: sibling `rufus-master`, read-only throughout development.
`docs/upstream-sha256.json` records SHA-256 for all 816 original files.
The initial copy was verified byte-for-byte. Original hashes were rechecked
with no changed entries after the main rebranding and website work.

## Modified upstream files

- `.vs/rufus.vcxproj`: Nawam TargetName/ProductName display, icon path, quoted
  prebuild locale commands for paths containing spaces. Project GUIDs retained.
- `.vs/rufus.vcxproj.filters`: icon reference.
- `res/hogger/hogger.c`, `hogger.asm`: isolated Nawam command-line helper mutex.
- `res/loc/rufus.loc`: application branding across 38 locales, preserving syntax,
  placeholders, warnings, original translator names and technical exceptions.
- `src/rufus.h`: product/developer macros and explicit update policy include.
- `src/rufus.rc`: Nawam 1.0.0 metadata, dialog captions, USB vector icon,
  compact About and separate expanded License & Open Source dialog.
- `src/rufus.c`: INI/log/locale/app-marker paths, command helper identity,
  one user-facing log message, shared upstream disk-safety mutex retained,
  and explicit used attributes for MinGW security load-config constants.
- `src/stdlg.c`: simple About, legal notices/translator credits moved to the
  license dialog, disabled self-update initialization/download, disabled update
  settings UI, developer website link.
- `src/license.h`: compact Nawam-only About, separate source/legal introduction.
  GPL and third-party copyright corpus preserved.
- `src/net.c`: hard-disabled CheckForUpdates entry point. The upstream worker
  remains in source, but no Nawam self-update thread can be created by it.
- `src/icon.c`, `src/vhd.c`: only website text in generated media annotations.
- `README.md`: Nawam build, use, attribution and limitations documentation.

## Added files

`src/nawam_policy.h`, `res/nawam.ico`, `res/nawam.png`, `res/nawam.ini`,
`res/hogger/nawam-hogger.exe`, `scripts/build.py`, `scripts/make_icon.py`,
`scripts/qa_ui.py`, Python regression tests, original-hash manifest and reports.
`README.upstream.md` preserves the original project README.
`website/` contains the landing page, legal/privacy pages, Firebase config,
browser/static tests, release packager and local font/license assets.

## Intentionally preserved

Raw disk, partitioning, formatting, ISO extraction, filesystem and bootloader
algorithms; elevation manifest; Secure Boot signatures and component hashes;
USB HDD safety defaults; destructive confirmation and warning messages;
resource identifiers, technical Rufus MBR name, compatibility EFI paths;
all original source copyright headers and third-party licenses.
Only x64 is delivered. Original x86/ARM64 solution configurations remain,
but were not compiled or tested during this task.

## Build

Toolchain: w64devkit 2.10.0, GCC 16.2.0, GNU Make 4.4.1, windres.
Native dependencies come from the upstream source. No system-wide compiler install.

    python scripts/build.py --clean

Output: `dist/Nawam.exe`. Log: `docs/build-x64.log`.
The build uses upstream configure/Make, rebuilds the helper, generates locale
resources, applies upstream `res/scripts/loadcfg.py`, then verifies the PE.

## Verification actually performed

- Initial upstream baseline compiled: zero compiler warnings/errors.
- Final modified application compiled successfully, including compact About.
- x64 PE, GUI subsystem, version 1.0.0 and Nawam metadata verified.
- DEP/ASLR and DependentLoadFlags 0x800 verified.
- 13 Python regression tests passed after the About redesign.
- Compiled actual disabled updater entry points in an isolated executable;
  forced and ordinary update checks both return false, download path returns.
- Main application opened under Windows 11; original smoke capture detected
  the attached USB, GPT/UEFI, NTFS, cluster size and disabled Start without ISO.
- About/legal resources of the revised build parsed and verified separately.
- Website static tests and real Chrome/axe QA passed at four viewport widths.

## Explicit limitations / warnings

- One expected compiler warning: unused upstream `CheckForUpdatesThread`.
- No Authenticode signing identity: Windows may show Unknown publisher.
- No physical USB write, format, actual boot or full ISO compatibility test.
- Final revised About requires a new app launch for live visual inspection;
  resource verification is not claimed as live interaction verification.
- Automatic Fido and remote DBX refresh coupled to the old update flow remain
  inactive by default. Embedded revocation and boot resources are retained.
- Self-update feed/signing infrastructure is not implemented.
- Primary address is nawam.web.app; no custom DNS is required.

## Website publication

Firebase project/site: `nawam-shanna` (dedicated, no existing SHANNA site changed).
Canonical address: `https://nawam.web.app`. Active Hosting site: `nawam`.
GitHub target: `shannacore/nawam`, private source repository.
Public artifacts: `shannacore/nawam-releases`. Firebase Spark forbids EXE hosting,
so executable/source/checksums are hosted as GitHub release assets, not disguised
or deployed to Firebase. No billing plan change was made.
No credentials or installed toolchains are included in git or the public source ZIP.
