# Nawam website

The product website for Nawam, a bootable USB creation utility for Windows.

Copyright © 2026 Shanna Studio.
Website: https://nawam.shanna.id

## Content

- Product features and supported configurations.
- Step-by-step instructions and data-loss warnings.
- Downloads, checksums and version information.
- Frequently asked questions.
- License, open-source notices and privacy information.

Indonesian is available at `/`; English at `/en/`.
The active language flag switches to the matching translated page.

## Design

Light background, white cards, blue actions and cyan accents.
The original Nawam USB logo is retained.
Header uses one row and is not sticky.
Product images must be original screenshots, not simulated application interfaces.
The supplied screenshot is kept at its native resolution without recompression.

## Checks

    npm ci
    npm test
    node scripts/browser-check.mjs
    node scripts/browser-i18n-check.mjs

Browser checks cover desktop and mobile layout, language navigation, keyboard
interaction, clipboard behavior and accessibility. Generated reports remain local.

## License

Application license and component attribution are available on the website's
License & Open Source page and in the corresponding application source.
