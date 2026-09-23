# Nawam website

Professional Indonesian landing page for Nawam Bootable USB Creator.
Developed by SHANNA Digital Systems. Static HTML/CSS/JavaScript, no database,
no analytics, no runtime third-party CDN. Firebase serves `public/` only.

## Local development

Node.js 24 and Firebase CLI 15.30.0 were used.

    npm ci
    npm test
    firebase emulators:start --only hosting --project nawam-shanna

Open http://127.0.0.1:5081.
In another terminal:

    node scripts/browser-check.mjs

The browser check uses an installed Chrome, checks 1440/768/390/320 widths,
keyboard tabs, mobile menu, FAQ, images, console errors and axe WCAG rules.
Screenshots/reports are in `artifacts/` (not committed).
For live QA: `QA_URL=https://nawam.web.app node scripts/browser-check.mjs`.

## Release packaging

From the root application project, first build and test the final executable.
From this directory run:

    python scripts/legal.py
    python scripts/package_release.py

The packaging script verifies the binary metadata and produces a corresponding
source ZIP from an explicit project allowlist, without installed toolchains,
account configuration or credentials. It generates release.json and SHA256SUMS.
Downloads are excluded from git AND Firebase deploy: the Spark plan forbids EXE files.
Upload the generated Nawam.exe, source ZIP and SHA256SUMS.txt to
https://github.com/shannacore/nawam-releases/releases/tag/v1.0.0 before deploying.
Never change Firebase billing or disguise an executable to bypass this restriction.

## Deploy

    npm test
    firebase deploy --only hosting --project nawam-shanna --non-interactive

Firebase project: `nawam-shanna`; active site: `nawam`.
Live URL: https://nawam.web.app
Intended canonical URL: https://nawam.web.app
Development source: https://github.com/shannacore/nawam (private)
Public release artifacts and corresponding source: https://github.com/shannacore/nawam-releases

## Site address

Primary site: https://nawam.web.app. No custom DNS configuration is needed.
The previous `nawam-shanna` Hosting site is disabled after new-site verification.
The Firebase PROJECT remains `nawam-shanna`; the active Hosting SITE is `nawam`.

## Editing

- `public/index.html`: all main content, FAQ and compatibility copy.
- `public/assets/site.css`: Fresh Mint palette and responsive design.
- `public/assets/site.js`: mobile menu, keyboard tabs, checksum copy.
- `public/release.json`: generated actual release metadata; not a desktop update feed.
- `public/open-source.html`: legal attribution and source download.
- `public/privacy.html`: actual data practices.
- `firebase.json`: dedicated Hosting site, caching and security headers.

The main preview is a clearly labeled SVG UI illustration for legibility, not
a screenshot or proof of runtime state. The original app screenshot is linked separately.
Never claim physical-drive write/boot tests unless they have been performed.
Self-updates remain disabled in the desktop application.

## Font and images

Manrope is self-hosted under SIL OFL; license in public/licenses/Manrope-OFL.txt.
Nawam USB vector icon: new artwork from the application project. Third-party toolbar
icons inside the product screenshot retain attribution on the legal page.

## Security

No credentials belong in source. Firebase account tokens remain in the user CLI
credential store; Git authentication uses the existing Windows credential helper.
No service account key has been created or committed. No auto-deploy workflow is
configured: deployment is explicit, so pushing source cannot silently overwrite live.
