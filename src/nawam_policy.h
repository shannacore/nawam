/* Nawam modifications, Copyright (c) 2026 SHANNA Digital Systems.
 * GPL-3.0-or-later, like the upstream Rufus application.
 */
#pragma once

#define NAWAM_WEBSITE "https://nawam.web.app"
/* No release feed/signing authority is configured for Nawam yet.
 * Never use Rufus release metadata or executables as Nawam updates.
 * Future work requires a dedicated signed feed and an independent verifier;
 * changing this flag alone must NOT enable the upstream implementation.
 */
#define NAWAM_SELF_UPDATE_ENABLED 0
#define NAWAM_UPDATE_FEED_URL ""
#if NAWAM_SELF_UPDATE_ENABLED
#error Implement and audit a Nawam-specific signed updater before enabling it.
#endif
