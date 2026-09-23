/* Nawam modifications, Copyright (c) 2026 SHANNA Digital Systems.
 * GPL-3.0-or-later, like the upstream Rufus application.
 */
#pragma once

#define NAWAM_WEBSITE "https://nawam.shanna.id"
#define NAWAM_STARTUP_TITLE_EN "Nawam - Unsigned/custom build"
#define NAWAM_STARTUP_NOTICE_EN \
	"Nawam is an unsigned/custom build. Its publisher has not been verified with Authenticode.\n\n" \
	"Verify the source and SHA-256 checksum against a trusted release before use.\n\nContinue?"
#define NAWAM_STARTUP_TITLE_ID "Nawam - Build kustom tanpa tanda tangan"
#define NAWAM_STARTUP_NOTICE_ID \
	"Nawam adalah build kustom tanpa tanda tangan digital. Penerbitnya belum diverifikasi dengan Authenticode.\n\n" \
	"Verifikasi kode sumber dan checksum SHA-256 dengan rilis tepercaya sebelum digunakan.\n\nLanjutkan?"
#define NAWAM_MUTEX_NOTICE_EN \
	"Nawam could not acquire the shared application lock.\n\n" \
	"Close any running Nawam or Rufus instance, then try again."
#define NAWAM_MUTEX_NOTICE_ID \
	"Nawam tidak dapat memperoleh kunci aplikasi bersama.\n\n" \
	"Tutup Nawam atau Rufus yang sedang berjalan, lalu coba lagi."
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
