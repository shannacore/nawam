# Nawam 1.0.1 — publisher and About update

Bootable USB Creator. Copyright © 2026 Shanna Studio.

Official application website: https://nawam.shanna.id
Firebase hosting remains available: https://nawam.web.app
The custom domain is managed separately by the owner; this update does not
claim that DNS or TLS for it has been configured.

## Changes

- Windows executable CompanyName: Shanna Studio.
- About: Nawam 1.0.1, Bootable USB Creator, copyright Shanna Studio and website.
- Removed the Developed by line from About.
- Application website links now use https://nawam.shanna.id.
- SHANNA Digital Systems remains the internal configuration namespace to retain
  existing settings. No disk/format/partitioning algorithms changed.

## Assets

- Nawam.exe — Windows x64 application.
- Nawam-1.0.1-source.zip — matching application source, resources and build instructions.
- SHA256SUMS.txt — checksums for both packages.

13 source regression tests and PE/resource verification pass.
This build is unsigned: Windows UAC may still show Unknown publisher.
No physical USB write or boot tests were automated. Back up data before use.
Self-updates remain disabled; install this release manually.

Based on the open-source Rufus project, GPL-3.0-or-later.
Copyright © 2011–2026 Pete Batard and respective upstream contributors.
Original license and attribution remain in License & Open Source and source.
