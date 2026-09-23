/*
 * Rufus: The Reliable USB Formatting Utility
 * Networking functionality (web file download, check for update, etc.)
 * Copyright © 2012-2026 Pete Batard <pete@akeo.ie>
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

/* Memory leaks detection - define _CRTDBG_MAP_ALLOC as preprocessor macro */
#ifdef _CRTDBG_MAP_ALLOC
#include <stdlib.h>
#include <crtdbg.h>
#endif

#include <windows.h>
#include <wininet.h>
#include <netlistmgr.h>
#include <stdio.h>
#include <malloc.h>
#include <string.h>
#include <inttypes.h>
#include <assert.h>
#include <time.h>
#include <virtdisk.h>

#include "rufus.h"
#include "nawam_safety.h"
#include "nawam_security.h"
#include "missing.h"
#include "resource.h"
#include "msapi_utf8.h"
#include "localization.h"
#include "bled/bled.h"
#include "dbx/dbx_info.h"

#include "settings.h"

/* Maximum download chunk size, in bytes */
#define DOWNLOAD_BUFFER_SIZE    (10*KB)
/* Default delay between update checks (1 day) */
#define DEFAULT_UPDATE_INTERVAL (24*3600)

DWORD DownloadStatus;
BYTE* fido_script = NULL;
HANDLE update_check_thread = NULL;

extern loc_cmd* selected_locale;
extern HANDLE dialog_handle;
extern BOOL is_x86_64;
extern USHORT NativeMachine;
static DWORD error_code, fido_len = 0;
#if NAWAM_SELF_UPDATE_ENABLED
static BOOL force_update_check = FALSE;
#endif
extern const char* efi_archname[ARCH_MAX];
extern char *sbat_level_txt, *sb_active_txt, *sb_revoked_txt;

#if defined(__MINGW32__)
#define INetworkListManager_get_IsConnectedToInternet INetworkListManager_IsConnectedToInternet
#endif

static char* GetShortName(const char* url)
{
	static char short_name[128];
	char *p;
	size_t i, len = safe_strlen(url);
	if (len < 5)
		return NULL;

	for (i = len - 2; i > 0; i--) {
		if (url[i] == '/') {
			i++;
			break;
		}
	}
	memset(short_name, 0, sizeof(short_name));
	static_strcpy(short_name, &url[i]);
	// If the URL is followed by a query, remove that part
	// Make sure we detect escaped queries too
	p = strstr(short_name, "%3F");
	if (p != NULL)
		*p = 0;
	p = strstr(short_name, "%3f");
	if (p != NULL)
		*p = 0;
	for (i = 0; i < strlen(short_name); i++) {
		if ((short_name[i] == '?') || (short_name[i] == '#')) {
			short_name[i] = 0;
			break;
		}
	}
	return short_name;
}

static __inline BOOL is_WOW64(void)
{
	BOOL ret = FALSE;
	IsWow64Process(GetCurrentProcess(), &ret);
	return ret;
}

// Open an Internet session
static HINTERNET GetInternetSession(const char* user_agent, BOOL bRetry)
{
	int i;
	char default_agent[64];
	BOOL decodingSupport = TRUE;
	VARIANT_BOOL InternetConnection = VARIANT_FALSE;
	DWORD dwFlags, dwTimeout = NET_SESSION_TIMEOUT, dwProtocolSupport = HTTP_PROTOCOL_FLAG_HTTP2;
	HINTERNET hSession = NULL;
	HRESULT hr = S_FALSE, com_result;
	DWORD saved_error;
	INetworkListManager* pNetworkListManager = NULL;
	// Balance COM even when the caller already initialized this apartment.
	com_result = CoInitializeEx(NULL, COINIT_APARTMENTTHREADED | COINIT_DISABLE_OLE1DDE);
	hr = CoCreateInstance(&CLSID_NetworkListManager, NULL, CLSCTX_ALL,
		&IID_INetworkListManager, (LPVOID*)&pNetworkListManager);
	if (hr == S_OK) {
		for (i = 0; i <= WRITE_RETRIES; i++) {
			hr = INetworkListManager_get_IsConnectedToInternet(pNetworkListManager, &InternetConnection);
			// INetworkListManager may fail with ERROR_SERVICE_DEPENDENCY_FAIL if the DHCP service
			// is not running, in which case we must fall back to using InternetGetConnectedState().
			// See https://github.com/pbatard/rufus/issues/1801.
			if (hr == HRESULT_FROM_WIN32(ERROR_SERVICE_DEPENDENCY_FAIL)) {
				InternetConnection = InternetGetConnectedState(&dwFlags, 0) ? VARIANT_TRUE : VARIANT_FALSE;
				break;
			}
			if (hr == S_OK || !bRetry)
				break;
			Sleep(1000);
		}
	}
	if (InternetConnection == VARIANT_FALSE) {
		SetLastError(ERROR_INTERNET_DISCONNECTED);
		goto out;
	}
	static_sprintf(default_agent, APPLICATION_NAME "/%d.%d.%d (Windows NT %lu.%lu%s)",
		rufus_version[0], rufus_version[1], rufus_version[2],
		WindowsVersion.Major, WindowsVersion.Minor, is_WOW64() ? "; WOW64" : "");
	hSession = InternetOpenA((user_agent == NULL) ? default_agent : user_agent,
		INTERNET_OPEN_TYPE_PRECONFIG, NULL, NULL, 0);
	if (hSession == NULL) goto out;
	// Set the timeouts
	InternetSetOptionA(hSession, INTERNET_OPTION_CONNECT_TIMEOUT, (LPVOID)&dwTimeout, sizeof(dwTimeout));
	InternetSetOptionA(hSession, INTERNET_OPTION_SEND_TIMEOUT, (LPVOID)&dwTimeout, sizeof(dwTimeout));
	InternetSetOptionA(hSession, INTERNET_OPTION_RECEIVE_TIMEOUT, (LPVOID)&dwTimeout, sizeof(dwTimeout));
	// Enable gzip and deflate decoding schemes
	InternetSetOptionA(hSession, INTERNET_OPTION_HTTP_DECODING, (LPVOID)&decodingSupport, sizeof(decodingSupport));
	// Enable HTTP/2 protocol support
	InternetSetOptionA(hSession, INTERNET_OPTION_ENABLE_HTTP_PROTOCOL, (LPVOID)&dwProtocolSupport, sizeof(dwProtocolSupport));

out:
	saved_error = GetLastError();
	if (pNetworkListManager != NULL) INetworkListManager_Release(pNetworkListManager);
	if (SUCCEEDED(com_result)) CoUninitialize();
	SetLastError(saved_error);
	return hSession;
}

/*
 * Download a file or fill a buffer from an URL
 * Mostly taken from http://support.microsoft.com/kb/234913
 * If file is NULL, a buffer is allocated for the download (that needs to be freed by the caller)
 * If hProgressDialog is not NULL, this function will send INIT and EXIT messages
 * to the dialog in question, with WPARAM being set to nonzero for EXIT on success
 * and also attempt to indicate progress using an IDC_PROGRESS control
 * Note that when a buffer is used, the actual size of the buffer is two more than its reported
 * size (with the extra bytes set to 0) to accommodate for calls that need NUL-terminated data.
 */
uint64_t DownloadToFileOrBufferEx(const char* url, const char* file, const char* user_agent,
	BYTE** buffer, HWND hProgressDialog, BOOL bTaskBarProgress)
{
	const char* accept_types[] = {"*/*\0", NULL};
	const char* short_name;
	unsigned char buf[DOWNLOAD_BUFFER_SIZE];
	char hostname[256], urlpath[2048], strsize[32], *bak_file = NULL;
	BOOL r = FALSE, file_created = FALSE, backup_moved = FALSE;
	DWORD dwSize, dwWritten, dwDownloaded;
	HANDLE hFile = INVALID_HANDLE_VALUE;
	HINTERNET hSession = NULL, hConnection = NULL, hRequest = NULL;
	URL_COMPONENTSA UrlParts = { sizeof(URL_COMPONENTSA), NULL, 1, (INTERNET_SCHEME)0,
		hostname, sizeof(hostname), 0, NULL, 1, urlpath, sizeof(urlpath), NULL, 1 };
	uint64_t size = 0, total_size = 0;

	ErrorStatus = 0;
	DownloadStatus = 404;
	if (hProgressDialog != NULL)
		UpdateProgressWithInfoInit(hProgressDialog, FALSE);

	assert(url != NULL);
	if (buffer != NULL)
		*buffer = NULL;

	short_name = (file != NULL) ? PathFindFileNameU(file) : PathFindFileNameU(url);

	if (hProgressDialog != NULL) {
		PrintInfo(5000, MSG_085, short_name);
		uprintf("Downloading %s", url);
	}

	if ( (!InternetCrackUrlA(url, (DWORD)safe_strlen(url), 0, &UrlParts))
	  || (UrlParts.lpszHostName == NULL) || (UrlParts.lpszUrlPath == NULL)) {
		uprintf("Unable to decode URL: %s", WindowsErrorString());
		goto out;
	}
	hostname[sizeof(hostname)-1] = 0;

	hSession = GetInternetSession(user_agent, TRUE);
	if (hSession == NULL) {
		uprintf("Could not open Internet session: %s", WindowsErrorString());
		goto out;
	}

	hConnection = InternetConnectA(hSession, UrlParts.lpszHostName, UrlParts.nPort, NULL, NULL, INTERNET_SERVICE_HTTP, 0, (DWORD_PTR)NULL);
	if (hConnection == NULL) {
		uprintf("Could not connect to server %s:%d: %s", UrlParts.lpszHostName, UrlParts.nPort, WindowsErrorString());
		goto out;
	}

	hRequest = HttpOpenRequestA(hConnection, "GET", UrlParts.lpszUrlPath, NULL, NULL, accept_types,
		INTERNET_FLAG_IGNORE_REDIRECT_TO_HTTPS |
		INTERNET_FLAG_NO_COOKIES | INTERNET_FLAG_NO_UI | INTERNET_FLAG_NO_CACHE_WRITE | INTERNET_FLAG_HYPERLINK |
		((UrlParts.nScheme == INTERNET_SCHEME_HTTPS) ? INTERNET_FLAG_SECURE : 0), (DWORD_PTR)NULL);
	if (hRequest == NULL) {
		uprintf("Could not open URL %s: %s", url, WindowsErrorString());
		goto out;
	}

	// If we are querying the GitHub API, we need to enable raw content
	if (strstr(url, "api.github.com") != NULL && !HttpAddRequestHeadersA(hRequest,
		"Accept: application/vnd.github.v3.raw", (DWORD)-1, HTTP_ADDREQ_FLAG_ADD)) {
		uprintf("Unable to enable raw content from GitHub API: %s", WindowsErrorString());
		goto out;
	}
	// Must use "Accept-Encoding: identity" to get the file size
	// This is needed for GitHub as the Microsoft HTTP APIs can't seem to read content-length for
	// compressed content from GitHub, and using "identity" disables compression.
	if (!HttpSendRequestA(hRequest, "Accept-Encoding: identity", -1L, NULL, 0))
		goto out;

	// Get the file size
	dwSize = sizeof(DownloadStatus);
	if (!HttpQueryInfoA(hRequest, HTTP_QUERY_STATUS_CODE | HTTP_QUERY_FLAG_NUMBER, (LPVOID)&DownloadStatus, &dwSize, NULL))
		goto out;
	if (DownloadStatus != 200) {
		error_code = ERROR_INTERNET_ITEM_NOT_FOUND;
		SetLastError(RUFUS_ERROR(error_code));
		uprintf("%s '%s': %d", (DownloadStatus == 404) ? "File not found" : "Unable to access file", url, DownloadStatus);
		goto out;
	}
	dwSize = sizeof(strsize);
	if (!HttpQueryInfoA(hRequest, HTTP_QUERY_CONTENT_LENGTH, (LPVOID)strsize, &dwSize, NULL)) {
		uprintf("Unable to retrieve file length: %s", WindowsErrorString());
		goto out;
	}
	if (dwSize >= sizeof(strsize) || !NawamParseContentLength(strsize, dwSize, &total_size) ||
		!NawamDownloadLengthValid(total_size, file == NULL)) {
		SetLastError(ERROR_INVALID_DATA);
		uprintf("Rejected invalid or excessive download length");
		goto out;
	}
	if (hProgressDialog != NULL) {
		char msg[128];
		uprintf("File length: %s", SizeToHumanReadable(total_size, FALSE, FALSE));
		if (right_to_left_mode)
			static_sprintf(msg, "(%s) %s", SizeToHumanReadable(total_size, FALSE, FALSE), GetShortName(url));
		else
			static_sprintf(msg, "%s (%s)", GetShortName(url), SizeToHumanReadable(total_size, FALSE, FALSE));
		PrintStatus(5000, MSG_085, msg);
	}

	if (file != NULL) {
		if (PathFileExistsU((char*)file)) {
			bak_file = calloc(1, strlen(file) + 6);
			if (bak_file == NULL)
				goto out;
			strcpy(bak_file, file);
			strcat(bak_file, ".bak");
			if (!MoveFileU(file, bak_file))
				goto out;
			backup_moved = TRUE;
		}
		hFile = CreateFileU(file, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
		if (hFile == INVALID_HANDLE_VALUE) {
			uprintf("Unable to create file '%s': %s", short_name, WindowsErrorString());
			goto out;
		}
		file_created = TRUE;
	} else {
		if (buffer == NULL) {
			uprintf("No buffer pointer provided for download");
			goto out;
		}
		// Allocate one extra byte, so that caller can rely on NUL-terminated text if needed
		*buffer = calloc((size_t)total_size + 2, 1);
		if (*buffer == NULL) {
			uprintf("Could not allocate buffer for download");
			goto out;
		}
	}

	// Keep checking for data until there is nothing left.
	while (1) {
		// User may have cancelled the download
		if (IS_ERROR(ErrorStatus))
			goto out;
		if (!InternetReadFile(hRequest, buf, sizeof(buf), &dwDownloaded))
			goto out;
		if (dwDownloaded == 0)
			break;
		if (!NawamDownloadChunkValid(total_size, size, dwDownloaded)) {
			SetLastError(ERROR_INVALID_DATA);
			ErrorStatus = RUFUS_ERROR(ERROR_INVALID_DATA);
			uprintf("Rejected download chunk exceeding declared length");
			goto out;
		}
		if (hProgressDialog != NULL)
			UpdateProgressWithInfo(OP_NOOP, MSG_241, size, total_size);
		if (file != NULL) {
			if (!WriteFile(hFile, buf, dwDownloaded, &dwWritten, NULL)) {
				uprintf("Error writing file '%s': %s", short_name, WindowsErrorString());
				goto out;
			} else if (dwDownloaded != dwWritten) {
				uprintf("Error writing file '%s': Only %d/%d bytes written", short_name, dwWritten, dwDownloaded);
				goto out;
			}
		} else {
			memcpy(&(*buffer)[size], buf, dwDownloaded);
		}
		size += dwDownloaded;
	}

	if (size != total_size) {
		uprintf("Could not download complete file - read: %lld bytes, expected: %lld bytes", size, total_size);
		ErrorStatus = RUFUS_ERROR(ERROR_WRITE_FAULT);
		goto out;
	} else {
		DownloadStatus = 200;
		r = TRUE;
		if (hProgressDialog != NULL) {
			UpdateProgressWithInfo(OP_NOOP, MSG_241, total_size, total_size);
			uprintf("Successfully downloaded '%s'", short_name);
		}
	}

out:
	error_code = GetLastError();
	if (hFile != INVALID_HANDLE_VALUE) {
		// Force a flush - May help with the PKI API trying to process downloaded updates too early...
		FlushFileBuffers(hFile);
		CloseHandle(hFile);
	}
	if (!r) {
		if (file_created)
			DeleteFileU(file);
		if (backup_moved)
			MoveFileU(bak_file, file);
		if (buffer != NULL)
			safe_free(*buffer);
	} else if (bak_file != NULL) {
		DeleteFileU(bak_file);
	}
	safe_free(bak_file);
	if (hRequest)
		InternetCloseHandle(hRequest);
	if (hConnection)
		InternetCloseHandle(hConnection);
	if (hSession)
		InternetCloseHandle(hSession);

	SetLastError(error_code);
	return r ? size : 0;
}

// Download and validate a signed file. The file must have a corresponding '.sig' on the server.
DWORD DownloadSignedFile(const char* url, const char* file, HWND hProgressDialog, BOOL bPromptOnError)
{
	char* url_sig = NULL;
	BYTE *buf = NULL, *sig = NULL;
	DWORD buf_len = 0, sig_len = 0;
	DWORD ret = 0;
	HANDLE hFile = INVALID_HANDLE_VALUE;

	assert(url != NULL);

	url_sig = malloc(strlen(url) + 5);
	if (url_sig == NULL) {
		uprintf("Could not allocate signature URL");
		goto out;
	}
	strcpy(url_sig, url);
	strcat(url_sig, ".sig");

	buf_len = (DWORD)DownloadToFileOrBuffer(url, NULL, &buf, hProgressDialog, FALSE);
	if (buf_len == 0)
		goto out;
	sig_len = (DWORD)DownloadToFileOrBuffer(url_sig, NULL, &sig, NULL, FALSE);
	if ((sig_len != RSA_SIGNATURE_SIZE) || (!ValidateOpensslSignature(buf, buf_len, sig, sig_len))) {
		uprintf("FATAL: Download signature is invalid ✗");
		DownloadStatus = 403;	// Forbidden
		ErrorStatus = RUFUS_ERROR(APPERR(ERROR_BAD_SIGNATURE));
		SendMessage(GetDlgItem(hProgressDialog, IDC_PROGRESS), PBM_SETSTATE, (WPARAM)PBST_ERROR, 0);
		SetTaskbarProgressState(TASKBAR_ERROR);
		goto out;
	}

	uprintf("Download signature is valid ✓");
	DownloadStatus = 206;	// Partial content
	hFile = CreateFileU(file, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
	if (hFile == INVALID_HANDLE_VALUE) {
		uprintf("Unable to create file '%s': %s", PathFindFileNameU(file), WindowsErrorString());
		goto out;
	}
	if (!WriteFile(hFile, buf, buf_len, &ret, NULL)) {
		uprintf("Error writing file '%s': %s", PathFindFileNameU(file), WindowsErrorString());
		ret = 0;
		goto out;
	} else if (ret != buf_len) {
		uprintf("Error writing file '%s': Only %d/%d bytes written", PathFindFileNameU(file), ret, buf_len);
		ret = 0;
		goto out;
	}
	DownloadStatus = 200;	// Full content

out:
	if (hProgressDialog != NULL)
		SendMessage(hProgressDialog, UM_PROGRESS_EXIT, (WPARAM)ret, 0);
	if ((bPromptOnError) && (DownloadStatus != 200)) {
		PrintInfo(0, MSG_242);
		SetLastError(error_code);
		Notification(MB_OK | MB_ICONERROR, lmprintf(MSG_044), IS_ERROR(ErrorStatus) ? StrError(ErrorStatus, FALSE) : WindowsErrorString());
	}
	safe_closehandle(hFile);
	free(url_sig);
	free(buf);
	free(sig);
	return ret;
}

/* Threaded download */
typedef struct {
	const char* url;
	const char* file;
	HWND hProgressDialog;
	BOOL bPromptOnError;
} DownloadSignedFileThreadArgs;

static DWORD WINAPI DownloadSignedFileThread(LPVOID param)
{
	DownloadSignedFileThreadArgs* args = (DownloadSignedFileThreadArgs*)param;
	ExitThread(DownloadSignedFile(args->url, args->file, args->hProgressDialog, args->bPromptOnError));
}

HANDLE DownloadSignedFileThreaded(const char* url, const char* file, HWND hProgressDialog, BOOL bPromptOnError)
{
	static DownloadSignedFileThreadArgs args;
	args.url = url;
	args.file = file;
	args.hProgressDialog = hProgressDialog;
	args.bPromptOnError = bPromptOnError;
	return CreateThread(NULL, 0, DownloadSignedFileThread, &args, 0, NULL);
}

#if NAWAM_SELF_UPDATE_ENABLED
static __inline uint64_t to_uint64_t(uint16_t x[3]) {
	int i;
	uint64_t ret = 0;
	for (i = 0; i < 3; i++)
		ret = (ret << 16) + x[i];
	return ret;
}
#endif

BOOL UseLocalDbx(int arch)
{
	char reg_name[32];
	static_sprintf(reg_name, "DBXTimestamp_%s", efi_archname[arch]);
	return (uint64_t)ReadSetting64(reg_name) > dbx_info[arch - 1].timestamp;
}

/* NAWAM_SECURITY_DBX_BEGIN */
static BOOL NawamReadDbxCache(const char* path, BYTE** data, DWORD* size)
{
	wchar_t* wide = utf8_to_wchar(path);
	HANDLE file = INVALID_HANDLE_VALUE;
	LARGE_INTEGER length;
	DWORD read = 0;
	BOOL valid = FALSE;
	*data = NULL;
	*size = 0;
	if (wide == NULL) return FALSE;
	file = CreateFileW(wide, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
	free(wide);
	if (file == INVALID_HANDLE_VALUE) return FALSE;
	if (!GetFileSizeEx(file, &length) || length.QuadPart <= 0 ||
		!NawamDownloadLengthValid((uint64_t)length.QuadPart, TRUE)) goto out;
	*size = (DWORD)length.QuadPart;
	*data = malloc(*size);
	if (*data != NULL && ReadFile(file, *data, *size, &read, NULL) && read == *size)
		valid = NawamDbxValid(*data, *size);
out:
	CloseHandle(file);
	if (!valid) { safe_free(*data); *size = 0; }
	return valid;
}

static BOOL NawamCommitDbxCache(const char* path, const BYTE* data, DWORD size)
{
	wchar_t *target = NULL, *directory = NULL, *separator;
	wchar_t temporary[MAX_PATH] = { 0 };
	HANDLE file = INVALID_HANDLE_VALUE;
	DWORD written = 0, read = 0;
	BYTE* verify = NULL;
	BOOL result = FALSE;
	if (!NawamDbxValid(data, size)) return FALSE;
	target = utf8_to_wchar(path);
	directory = utf8_to_wchar(path);
	if (target == NULL || directory == NULL) goto out;
	separator = wcsrchr(directory, L'\\');
	if (separator == NULL) goto out;
	*separator = 0;
	if (!CreateDirectoryW(directory, NULL) && GetLastError() != ERROR_ALREADY_EXISTS) goto out;
	/* A sibling temp ensures replacement never crosses a volume boundary. */
	if (!GetTempFileNameW(directory, L"ndb", 0, temporary)) goto out;
	file = CreateFileW(temporary, GENERIC_READ | GENERIC_WRITE, 0, NULL, OPEN_EXISTING,
		FILE_ATTRIBUTE_NORMAL | FILE_FLAG_WRITE_THROUGH, NULL);
	if (file == INVALID_HANDLE_VALUE) goto out;
	if (!WriteFile(file, data, size, &written, NULL) || written != size || !FlushFileBuffers(file)) goto out;
	verify = malloc(size);
	if (verify == NULL || SetFilePointer(file, 0, NULL, FILE_BEGIN) == INVALID_SET_FILE_POINTER ||
		!ReadFile(file, verify, size, &read, NULL) || read != size || memcmp(data, verify, size) ||
		!NawamDbxValid(verify, size)) goto out;
	if (!CloseHandle(file)) { file = INVALID_HANDLE_VALUE; goto out; }
	file = INVALID_HANDLE_VALUE;
	result = MoveFileExW(temporary, target, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH);
out:
	if (file != INVALID_HANDLE_VALUE) CloseHandle(file);
	if (temporary[0] != 0 && !result) DeleteFileW(temporary);
	free(target);
	free(directory);
	free(verify);
	return result;
}

static void NawamRefreshDbx(unsigned* ok, unsigned* failed)
{
	unsigned i;
	char timestamp_url[512], pinned_url[512], path[MAX_PATH], key[32], sha[41];
	const char *part, *p;
	char* out;
	BYTE *metadata = NULL, *data = NULL, *cached = NULL;
	uint64_t size, timestamp;
	int64_t previous, now;
	DWORD cache_size;
	int n;
	for (i = 0; i < ARRAYSIZE(dbx_info); i++) {
		part = strstr(dbx_info[i].url, "contents/");
		if (part == NULL) goto fail;
		n = snprintf(timestamp_url, sizeof(timestamp_url), "%.*scommits?path=",
			(int)(part - dbx_info[i].url), dbx_info[i].url);
		if (n < 0 || n >= (int)sizeof(timestamp_url)) goto fail;
		out = timestamp_url + n;
		for (p = part + 9; *p != 0; p++) {
			if ((size_t)(out - timestamp_url) + 32 >= sizeof(timestamp_url)) goto fail;
			if (*p == '/') { memcpy(out, "%2F", 3); out += 3; }
			else *out++ = *p;
		}
		strcpy(out, "&page=1&per_page=1");
		size = DownloadToFileOrBuffer(timestamp_url, NULL, &metadata, NULL, FALSE);
		if (!NawamCommitTimestamp((char*)metadata, (size_t)size, &timestamp, sha)) goto fail;
		safe_free(metadata);
		now = (int64_t)time(NULL);
		if (now <= 0 || timestamp > (uint64_t)now + 86400) goto fail;
		static_sprintf(key, "DBXTimestamp_%s", efi_archname[i + 1]);
		previous = ReadSetting64(key);
		if (previous < 0 || (uint64_t)previous > (uint64_t)now + 86400) goto fail;
		if (timestamp <= dbx_info[i].timestamp && (uint64_t)previous <= dbx_info[i].timestamp) {
			(*ok)++;
			uprintf("Security refresh: embedded DBX %s is current", efi_archname[i + 1]);
			continue;
		}
		n = snprintf(path, sizeof(path), "%s\\%s\\dbx_%s.bin", app_data_dir, FILES_DIR, efi_archname[i + 1]);
		if (n < 0 || n >= (int)sizeof(path)) goto fail;
		if ((uint64_t)previous >= timestamp) {
			if (NawamReadDbxCache(path, &cached, &cache_size)) {
				safe_free(cached);
				(*ok)++;
				continue;
			}
			/* Repair a missing/corrupt equal-version cache, never roll back. */
			if ((uint64_t)previous > timestamp) goto fail;
		}
		n = snprintf(pinned_url, sizeof(pinned_url), "%s?ref=%s", dbx_info[i].url, sha);
		if (n < 0 || n >= (int)sizeof(pinned_url)) goto fail;
		size = DownloadToFileOrBuffer(pinned_url, NULL, &data, NULL, FALSE);
		if (!NawamDownloadLengthValid(size, TRUE) || !NawamDbxValid(data, (size_t)size) ||
			!NawamCommitDbxCache(path, data, (DWORD)size)) goto fail;
		/* Publish the monotonic marker only after validated atomic replacement. */
		if (!WriteSetting64(key, (int64_t)timestamp) || ReadSetting64(key) != (int64_t)timestamp) goto fail;
		safe_free(data);
		(*ok)++;
		uprintf("Security refresh: saved Microsoft DBX %s (%llu bytes)", efi_archname[i + 1], size);
		continue;
fail:
		safe_free(metadata);
		safe_free(data);
		safe_free(cached);
		(*failed)++;
		uprintf("Security refresh: DBX %s failed (download, validation, cache or setting); prior valid data retained when possible",
			efi_archname[i + 1]);
	}
}
/* NAWAM_SECURITY_DBX_END */

/* NAWAM_SECURITY_TEXT_BEGIN */
/* Caller owns the operation gate and keeps the modal disabled until joined.
 * Parsed SBAT products point into their text buffer, so transfer both together.
 */
static BOOL NawamRefreshSecurityText(unsigned kind)
{
	static const char* urls[] = { RUFUS_URL "/sbat_level.txt", RUFUS_URL "/sb_active.txt", RUFUS_URL "/sb_revoked.txt" };
	char* text = NULL;
	sbat_entry_t* sbat = NULL;
	thumbprint_list_t* certs = NULL;
	uint64_t size;
	unsigned expected, count = 0;
	size = DownloadToFileOrBuffer(urls[kind], NULL, (BYTE**)&text, NULL, FALSE);
	expected = NawamSecurityTextValid(text, (size_t)size, kind != 0);
	if (expected == 0)
		goto fail;
	if (kind == 0) {
		sbat = GetSbatEntries(text);
		if (sbat == NULL)
			goto fail;
		while (sbat[count].product != NULL) count++;
		if (count != expected)
			goto fail;
		safe_free(sbat_entries);
		safe_free(sbat_level_txt);
		sbat_entries = sbat;
		sbat_level_txt = text;
	} else {
		certs = GetThumbprintEntries(text);
		if (certs == NULL || certs->count != expected)
			goto fail;
		if (kind == 1) {
			safe_free(sb_active_certs);
			safe_free(sb_active_txt);
			sb_active_certs = certs;
			sb_active_txt = text;
		} else {
			safe_free(sb_revoked_certs);
			safe_free(sb_revoked_txt);
			sb_revoked_certs = certs;
			sb_revoked_txt = text;
		}
	}
	uprintf("Security refresh: accepted %u entries from %s", expected, urls[kind]);
	return TRUE;
fail:
	free(sbat);
	free(certs);
	free(text);
	uprintf("Security refresh: download/validation failed for %s; previous data retained", urls[kind]);
	return FALSE;
}

DWORD WINAPI NawamSecurityRefreshThread(LPVOID param)
{
	unsigned i, ok = 0, failed = 0;
	IGNORE_RETVAL(param);
	/* op_in_progress is set by the manual caller before creating this thread. */
	if (!op_in_progress || image_path != NULL)
		return 0;
	for (i = 0; i < 3; i++) {
		if (NawamRefreshSecurityText(i)) ok++; else failed++;
	}
	NawamRefreshDbx(&ok, &failed);
	uprintf("Security refresh: %u data sources refreshed/current; %u failed", ok, failed);
	return ok == 0 ? 0 : failed == 0 ? 2 : 1;
}
/* NAWAM_SECURITY_TEXT_END */

/*
 * Background thread to check for updates (including UEFI DBX updates)
 */
#if NAWAM_SELF_UPDATE_ENABLED
static DWORD WINAPI CheckForUpdatesThread(LPVOID param)
{
	BOOL releases_only = TRUE, found_new_version = FALSE;
	int status = 0;
	const char* server_url = RUFUS_URL "/";
	int i, j, k, max_channel, verbose = 0, verpos[4];
	static const char* channel[] = { "release", "beta", "test" };		// release channel
	const char* accept_types[] = { "*/*\0", NULL };
	char* buf = NULL;
	char agent[64], hostname[64], urlpath[128], sigpath[256];
	DWORD dwSize, dwDownloaded, dwTotalSize, dwStatus;
	BYTE *sig = NULL;
	HINTERNET hSession = NULL, hConnection = NULL, hRequest = NULL;
	URL_COMPONENTSA UrlParts = { sizeof(URL_COMPONENTSA), NULL, 1, (INTERNET_SCHEME)0,
		hostname, sizeof(hostname), 0, NULL, 1, urlpath, sizeof(urlpath), NULL, 1 };
	SYSTEMTIME ServerTime, LocalTime;
	FILETIME FileTime;
	int64_t local_time = 0, reg_time, server_time, update_interval;
	verbose = ReadSetting32(SETTING_VERBOSE_UPDATES);
	// Without this the FileDialog will produce error 0x8001010E when compiled for Vista or later
	IGNORE_RETVAL(CoInitializeEx(NULL, COINIT_APARTMENTTHREADED | COINIT_DISABLE_OLE1DDE));
	// Unless the update was forced, wait a while before performing the update check
	if (!force_update_check) {
		// It would of course be a lot nicer to use a timer and wake the thread, but my
		// development time is limited and this is FASTER to implement.
		do {
			for (i = 0; ( i < 30) && (!force_update_check); i++)
				Sleep(500);
		} while ((!force_update_check) && ((op_in_progress || (dialog_showing > 0))));
		if (!force_update_check) {
			if ((ReadSetting32(SETTING_UPDATE_INTERVAL) == -1)) {
				vuprintf("Check for updates disabled, as per settings.");
				goto out;
			}
			reg_time = ReadSetting64(SETTING_LAST_UPDATE);
			update_interval = (int64_t)ReadSetting32(SETTING_UPDATE_INTERVAL);
			if (update_interval == 0) {
				WriteSetting32(SETTING_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL);
				update_interval = DEFAULT_UPDATE_INTERVAL;
			}
			GetSystemTime(&LocalTime);
			if (!SystemTimeToFileTime(&LocalTime, &FileTime))
				goto out;
			local_time = ((((int64_t)FileTime.dwHighDateTime) << 32) + FileTime.dwLowDateTime) / 10000000;
			vvuprintf("Local time: %" PRId64, local_time);
			if (local_time < reg_time + update_interval) {
				vuprintf("Next update check in %" PRId64 " seconds.", reg_time + update_interval - local_time);
				goto out;
			}
		}
	}

	// Perform the DBX Update check
	PrintInfoDebug(3000, MSG_352);
	{ unsigned ok = 0, failed = 0; NawamRefreshDbx(&ok, &failed); }

	PrintInfoDebug(3000, MSG_243);
	status++;	// 1

	if (!InternetCrackUrlA(server_url, (DWORD)safe_strlen(server_url), 0, &UrlParts))
		goto out;
	hostname[sizeof(hostname)-1] = 0;

	static_sprintf(agent, APPLICATION_NAME "/%d.%d.%d (Windows NT %lu.%lu%s)",
		rufus_version[0], rufus_version[1], rufus_version[2],
		WindowsVersion.Major, WindowsVersion.Minor, is_WOW64() ? "; WOW64" : "");
	hSession = GetInternetSession(NULL, FALSE);
	if (hSession == NULL)
		goto out;
	hConnection = InternetConnectA(hSession, UrlParts.lpszHostName, UrlParts.nPort,
		NULL, NULL, INTERNET_SERVICE_HTTP, 0, (DWORD_PTR)NULL);
	if (hConnection == NULL)
		goto out;

	status++;	// 2
	// BETAs are only made available when the application arch is x86_64
	if (is_x86_64)
		releases_only = !ReadSettingBool(SETTING_INCLUDE_BETAS);

	// Test releases get their own distribution channel (and also force beta checks)
#if defined(TEST)
	max_channel = (int)ARRAYSIZE(channel);
#else
	max_channel = releases_only ? 1 : (int)ARRAYSIZE(channel) - 1;
#endif
	vuprintf("Using %s for the update check", RUFUS_URL);
	for (k = 0; (k < max_channel) && (!found_new_version); k++) {
		// Get the arch name and convert it lowercase
		char* archname = strdup(GetArchName(WindowsVersion.Arch));
		safe_strtolower(archname);
		// Free any previous buffers we might have used
		safe_free(buf);
		safe_free(sig);
		uprintf("Checking %s channel...", channel[k]);
		// At this stage we can query the server for various update version files.
		// We first try to lookup for "<appname>_<os_arch>_<os_version_major>_<os_version_minor>.ver"
		// and then remove each of the <os_> components until we find our match. For instance, we may first
		// look for rufus_win_x64_6.2.ver (Win8 x64) but only get a match for rufus_win_x64_6.ver (Vista x64 or later)
		// This allows sunsetting OS versions (eg XP) or providing different downloads for different archs/groups.
		// Note that for BETAs, we only catter for x64 regardless of the OS arch.
		static_sprintf(urlpath, "%s%s%s_win_%s_%lu.%lu.ver", APPLICATION_NAME, (k == 0) ? "": "_",
			(k == 0) ? "" : channel[k], archname, WindowsVersion.Major, WindowsVersion.Minor);
		safe_free(archname);
		vuprintf("Base update check: %s", urlpath);
		for (i = 0, j = (int)safe_strlen(urlpath) - 5; (j > 0) && (i < ARRAYSIZE(verpos)); j--) {
			if ((urlpath[j] == '.') || (urlpath[j] == '_')) {
				verpos[i++] = j;
			}
		}
		assert(i == ARRAYSIZE(verpos));

		UrlParts.lpszUrlPath = urlpath;
		UrlParts.dwUrlPathLength = sizeof(urlpath);
		for (i = 0; i < ARRAYSIZE(verpos); i++) {
			vvuprintf("Trying %s", UrlParts.lpszUrlPath);
			hRequest = HttpOpenRequestA(hConnection, "GET", UrlParts.lpszUrlPath, NULL, NULL, accept_types,
				INTERNET_FLAG_IGNORE_REDIRECT_TO_HTTPS |
				INTERNET_FLAG_NO_COOKIES | INTERNET_FLAG_NO_UI | INTERNET_FLAG_NO_CACHE_WRITE | INTERNET_FLAG_HYPERLINK |
				((UrlParts.nScheme == INTERNET_SCHEME_HTTPS) ? INTERNET_FLAG_SECURE : 0), (DWORD_PTR)NULL);
			if (hRequest == NULL) {
				uprintf("Unable to send request: %s", WindowsErrorString());
				goto out;
			}
			// Must use "Accept-Encoding: identity" to get the file size
			if (!HttpSendRequestA(hRequest, "Accept-Encoding: identity", -1L, NULL, 0))
				goto out;

			// Ensure that we get a text file
			dwSize = sizeof(dwStatus);
			dwStatus = 404;
			HttpQueryInfoA(hRequest, HTTP_QUERY_STATUS_CODE|HTTP_QUERY_FLAG_NUMBER, (LPVOID)&dwStatus, &dwSize, NULL);
			if (dwStatus == 200)
				break;
			InternetCloseHandle(hRequest);
			hRequest = NULL;
			safe_strcpy(&urlpath[verpos[i]], 5, ".ver");
		}
		if (dwStatus != 200) {
			vuprintf("Could not find a %s version file on server %s", channel[k], server_url);
			if ((releases_only) || (k + 1 >= ARRAYSIZE(channel)))
				goto out;
			continue;
		}
		vuprintf("Found match for %s on server %s", urlpath, server_url);

		// We also get a date from the web server, which we'll use to avoid out of sync check,
		// in case some set their clock way into the future and back.
		// On the other hand, if local clock is set way back in the past, we will never check.
		dwSize = sizeof(ServerTime);
		// If we can't get a date we can trust, don't bother...
		if ( (!HttpQueryInfoA(hRequest, HTTP_QUERY_DATE|HTTP_QUERY_FLAG_SYSTEMTIME, (LPVOID)&ServerTime, &dwSize, NULL))
			|| (!SystemTimeToFileTime(&ServerTime, &FileTime)) )
			goto out;
		server_time = ((((int64_t)FileTime.dwHighDateTime) << 32) + FileTime.dwLowDateTime) / 10000000;
		vvuprintf("Server time: %" PRId64, server_time);
		// Always store the server response time - the only clock we trust!
		WriteSetting64(SETTING_LAST_UPDATE, server_time);
		// Might as well let the user know
		if (!force_update_check) {
			if ((local_time > server_time + 600) || (local_time < server_time - 600)) {
				uprintf("IMPORTANT: Your local clock is more than 10 minutes in the %s. Unless you fix this, "
					APPLICATION_NAME " may not be able to check for updates...",
					(local_time > server_time + 600)?"future":"past");
			}
		}

		dwSize = sizeof(dwTotalSize);
		if (!HttpQueryInfoA(hRequest, HTTP_QUERY_CONTENT_LENGTH|HTTP_QUERY_FLAG_NUMBER, (LPVOID)&dwTotalSize, &dwSize, NULL))
			goto out;

		// Make sure the file is NUL terminated
		buf = (char*)calloc(dwTotalSize + 1, 1);
		if (buf == NULL)
			goto out;
		// This is a version file - we should be able to gulp it down in one go
		if (!InternetReadFile(hRequest, buf, dwTotalSize, &dwDownloaded) || (dwDownloaded != dwTotalSize))
			goto out;
		vuprintf("Successfully downloaded version file (%d bytes)", dwTotalSize);

		// Now download the signature file
		static_sprintf(sigpath, "%s/%s.sig", server_url, urlpath);
		dwDownloaded = (DWORD)DownloadToFileOrBuffer(sigpath, NULL, &sig, NULL, FALSE);
		if ((dwDownloaded != RSA_SIGNATURE_SIZE) || (!ValidateOpensslSignature(buf, dwTotalSize, sig, dwDownloaded))) {
			uprintf("FATAL: Version signature is invalid ✗");
			goto out;
		}
		vuprintf("Version signature is valid ✓");

		status++;
		parse_update(buf, dwTotalSize + 1);

		vuprintf("UPDATE DATA:");
		vuprintf("  version: %d.%d.%d (%s)", update.version[0], update.version[1], update.version[2], channel[k]);
		vuprintf("  platform_min: %d.%d", update.platform_min[0], update.platform_min[1]);
		vuprintf("  url: %s", update.download_url);

		found_new_version = ((to_uint64_t(update.version) > to_uint64_t(rufus_version)) || (force_update))
			&& ((WindowsVersion.Major > update.platform_min[0])
				|| ((WindowsVersion.Major == update.platform_min[0]) && (WindowsVersion.Minor >= update.platform_min[1])));
		uprintf("N%sew %s version found%c", found_new_version ? "" : "o n", channel[k], found_new_version ? '!' : '.');
	}

out:
	safe_free(buf);
	safe_free(sig);
	if (hRequest)
		InternetCloseHandle(hRequest);
	if (hConnection)
		InternetCloseHandle(hConnection);
	if (hSession)
		InternetCloseHandle(hSession);
	switch (status) {
	case 1:
		PrintInfoDebug(3000, MSG_244);
		break;
	case 2:
		PrintInfoDebug(3000, MSG_245);
		break;
	case 3:
	case 4:
		PrintInfo(3000, found_new_version ? MSG_246 : MSG_247);
	default:
		break;
	}
	// Start the new download after cleanup
	if (found_new_version) {
		// User may have started an operation while we were checking
		while ((!force_update_check) && (op_in_progress || (dialog_showing > 0))) {
			Sleep(15000);
		}
		DownloadNewVersion();
	} else if (force_update_check) {
		PostMessage(hMainDialog, UM_NO_UPDATE, 0, 0);
	}
	force_update_check = FALSE;
	update_check_thread = NULL;
	CoUninitialize();
	ExitThread(0);
}

#endif

/*
 * Initiate a check for updates. If force is true, ignore the wait period
 */
BOOL CheckForUpdates(BOOL force)
{
#if !NAWAM_SELF_UPDATE_ENABLED
	IGNORE_RETVAL(force);
	uprintf("Nawam: application updates are disabled (no signed Nawam feed configured).");
	return FALSE;
#else
	force_update_check = force;
	if (update_check_thread != NULL)
		return FALSE;

	update_check_thread = CreateThread(NULL, 0, CheckForUpdatesThread, NULL, 0, NULL);
	if (update_check_thread == NULL) {
		uprintf("Unable to start update check thread");
		return FALSE;
	}
	return TRUE;
#endif
}

/*
 * Download an ISO through Fido
 */
static DWORD WINAPI DownloadISOThread(LPVOID param)
{
	char locale_str[1024], cmdline[sizeof(locale_str) + 512], pipe[MAX_GUID_STRING_LENGTH + 16] = "\\\\.\\pipe\\";
	char powershell_path[MAX_PATH], icon_path[MAX_PATH] = { 0 }, script_path[MAX_PATH] = { 0 };
	char *url = NULL, sig_url[128];
	uint64_t uncompressed_size;
	int64_t size = -1;
	BYTE *compressed = NULL, *sig = NULL;
	HANDLE hFile = INVALID_HANDLE_VALUE, hPipe = INVALID_HANDLE_VALUE;
	DWORD dwExitCode = 99, dwCompressedSize, dwSize, dwAvail, dwPipeSize = 4096;
	GUID guid;

	dialog_showing++;
	IGNORE_RETVAL(CoInitializeEx(NULL, COINIT_APARTMENTTHREADED | COINIT_DISABLE_OLE1DDE));

	// Use a GUID as random unique string, else ill-intentioned security "researchers"
	// may either spam our pipe or replace our script to fool antivirus solutions into
	// thinking that Rufus is doing something malicious...
	IGNORE_RETVAL(CoCreateGuid(&guid));
	// coverity[fixed_size_dest]
	strcpy(&pipe[9], GuidToString(&guid, TRUE));
	static_sprintf(icon_path, "%s%s.ico", temp_dir, APPLICATION_NAME);
	ExtractAppIcon(icon_path, TRUE);

//#define FORCE_URL "https://github.com/pbatard/rufus/raw/master/res/loc/test/windows_to_go.iso"
//#define FORCE_URL "https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/debian-9.8.0-amd64-netinst.iso"
#if !defined(FORCE_URL)
#if defined(RUFUS_TEST)
	IGNORE_RETVAL(hFile);
	IGNORE_RETVAL(sig_url);
	IGNORE_RETVAL(dwCompressedSize);
	IGNORE_RETVAL(uncompressed_size);
	// In test mode, just use our local script
	static_strcpy(script_path, "D:\\Projects\\Fido\\Fido.ps1");
#else
	// If we don't have the script, download it
	if (fido_script == NULL) {
		dwCompressedSize = (DWORD)DownloadToFileOrBuffer(fido_url, NULL, &compressed, hMainDialog, FALSE);
		if (dwCompressedSize == 0)
			goto out;
		static_sprintf(sig_url, "%s.sig", fido_url);
		dwSize = (DWORD)DownloadToFileOrBuffer(sig_url, NULL, &sig, NULL, FALSE);
		if ((dwSize != RSA_SIGNATURE_SIZE) || (!ValidateOpensslSignature(compressed, dwCompressedSize, sig, dwSize))) {
			uprintf("FATAL: Download signature is invalid ✗");
			ErrorStatus = RUFUS_ERROR(APPERR(ERROR_BAD_SIGNATURE));
			SendMessage(hProgress, PBM_SETSTATE, (WPARAM)PBST_ERROR, 0);
			SetTaskbarProgressState(TASKBAR_ERROR);
			safe_free(compressed);
			free(sig);
			goto out;
		}
		free(sig);
		uprintf("Download signature is valid ✓");
		uncompressed_size = *((uint64_t*)&compressed[5]);
		if ((uncompressed_size < 1 * MB) && (bled_init(0, uprintf, NULL, NULL, NULL, NULL, &ErrorStatus) >= 0)) {
			fido_script = malloc((size_t)uncompressed_size);
			size = bled_uncompress_from_buffer_to_buffer(compressed, dwCompressedSize, fido_script, (size_t)uncompressed_size, BLED_COMPRESSION_LZMA);
			bled_exit();
		}
		safe_free(compressed);
		if (size != uncompressed_size) {
			uprintf("FATAL: Could not uncompressed download script");
			safe_free(fido_script);
			ErrorStatus = RUFUS_ERROR(ERROR_INVALID_DATA);
			SendMessage(hProgress, PBM_SETSTATE, (WPARAM)PBST_ERROR, 0);
			SetTaskbarProgressState(TASKBAR_ERROR);
			goto out;
		}
		fido_len = (DWORD)size;
		SendMessage(hProgress, PBM_SETSTATE, (WPARAM)PBST_NORMAL, 0);
		SetTaskbarProgressState(TASKBAR_NORMAL);
		SetTaskbarProgressValue(0, MAX_PROGRESS);
		SendMessage(hProgress, PBM_SETPOS, 0, 0);
	}
	PrintInfo(0, MSG_148);

	if_assert_fails((fido_script != NULL) && (fido_len != 0))
		goto out;

	// Why oh why does PowerShell refuse to open read-only files that haven't been closed?
	// Because of this limitation, we can't fully prevent TOCTOUs on the file we create, and therefore we:
	// - Create the file with a "random" non-guessable name => TOCTOUs require a permanently running script/exe
	// - Create the file in the user's AppData temp directory => TOCTOUs can't be enacted by a different user
	// - Create the file with Administrator access only => TOCTOUs require elevated privileges (in which case
	// the machine is already compromised anyway, so TOCTOU attacks become entirely moot)
	// See https://github.com/pbatard/rufus/security/advisories/GHSA-hcx5-hrhj-xhq9 and CVE-2026-23988.
	static_sprintf(script_path, "%s%s.ps1", temp_dir, GuidToString(&guid, TRUE));
	hFile = CreateFileRestrictedU(script_path, GENERIC_WRITE, FILE_SHARE_READ, CREATE_ALWAYS, FILE_ATTRIBUTE_READONLY);
	if (hFile == INVALID_HANDLE_VALUE) {
		uprintf("Unable to create download script '%s': %s", script_path, WindowsErrorString());
		goto out;
	}
	if ((!WriteFile(hFile, fido_script, fido_len, &dwSize, NULL)) || (dwSize != fido_len)) {
		uprintf("Unable to write download script '%s': %s", script_path, WindowsErrorString());
		goto out;
	}
	safe_closehandle(hFile);
#endif
	static_sprintf(powershell_path, "%s\\WindowsPowerShell\\v1.0\\powershell.exe", system_dir);
	static_sprintf(locale_str, "%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s",
		selected_locale->txt[0], lmprintf(MSG_135), lmprintf(MSG_136), lmprintf(MSG_137),
		lmprintf(MSG_138), lmprintf(MSG_139), lmprintf(MSG_040), lmprintf(MSG_140), lmprintf(MSG_141),
		lmprintf(MSG_006), lmprintf(MSG_007), lmprintf(MSG_042), lmprintf(MSG_142), lmprintf(MSG_143),
		lmprintf(MSG_144), lmprintf(MSG_145), lmprintf(MSG_146), lmprintf(MSG_199));

	hPipe = CreateNamedPipeA(pipe, PIPE_ACCESS_INBOUND,
		PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT, PIPE_UNLIMITED_INSTANCES,
		dwPipeSize, dwPipeSize, 0, NULL);
	if (hPipe == INVALID_HANDLE_VALUE) {
		uprintf("Could not create pipe '%s': %s", pipe, WindowsErrorString());
		goto out;
	}

	// Ideally, since our script is signed, we'd have '-ExecutionPolicy AllSigned' below.
	// Except that, in the myriad of execution policy options they provide, Microsoft chose
	// not to add an option that allows signed scripts that validate up to the root of trust,
	// but aren't in Trusted Publishers, to be validated:
	// https://old.reddit.com/r/PowerShell/comments/kpwi5r/powershell_script_signing_trusted_publisher_prompt/gzi10oc/
	static_sprintf(cmdline, "\"%s\" -NonInteractive -Sta -NoProfile -ExecutionPolicy Bypass "
		"-File \"%s\" -PipeName %s -LocData \"%s\" -Icon \"%s\" -AppTitle \"%s\" -PlatformArch \"%s\"",
		powershell_path, script_path, &pipe[9], locale_str, icon_path, lmprintf(MSG_149), GetArchName(NativeMachine));

#ifndef RUFUS_TEST
	// Because we can't force PowerShell to do it, we validate the signature of the local script.
	if (ValidateSignature(INVALID_HANDLE_VALUE, script_path) != NO_ERROR) {
		uprintf("FATAL: Script signature is invalid ✗");
		ErrorStatus = RUFUS_ERROR(APPERR(ERROR_BAD_SIGNATURE));
		SendMessage(hProgress, PBM_SETSTATE, (WPARAM)PBST_ERROR, 0);
		SetTaskbarProgressState(TASKBAR_ERROR);
		goto out;
	}
	uprintf("Script signature is valid ✓");
#endif

	ErrorStatus = 0;
	dwExitCode = RunCommand(cmdline, app_data_dir, TRUE);
	uprintf("Exited download script with code: %d", dwExitCode);
	if ((dwExitCode == 0) && PeekNamedPipe(hPipe, NULL, dwPipeSize, NULL, &dwAvail, NULL) && (dwAvail != 0)) {
		url = malloc(dwAvail + 1);
		dwSize = 0;
		if ((url != NULL) && ReadFile(hPipe, url, dwAvail, &dwSize, NULL) && (dwSize > 4)) {
#else
	{	{	url = strdup(FORCE_URL);
			dwSize = (DWORD)strlen(FORCE_URL);
#endif
			IMG_SAVE img_save = { 0 };
			url[min(dwSize, dwAvail)] = 0;
			EXT_DECL(img_ext, GetShortName(url), __VA_GROUP__("*.iso"), __VA_GROUP__(lmprintf(MSG_036)));
			img_save.Type = VIRTUAL_STORAGE_TYPE_DEVICE_ISO;
			img_save.ImagePath = FileDialog(TRUE, NULL, &img_ext, NULL);
			if (img_save.ImagePath == NULL) {
				goto out;
			}
			// Download the ISO and report errors if any
			SendMessage(hMainDialog, UM_PROGRESS_INIT, 0, 0);
			ErrorStatus = 0;
			SendMessage(hMainDialog, UM_TIMER_START, 0, 0);
			if (DownloadToFileOrBuffer(url, img_save.ImagePath, NULL, hMainDialog, TRUE) == 0) {
				SendMessage(hMainDialog, UM_PROGRESS_EXIT, 0, 0);
				if (SCODE_CODE(ErrorStatus) == ERROR_CANCELLED) {
					uprintf("Download cancelled by user");
					Notification(MB_ICONINFORMATION | MB_CLOSE, lmprintf(MSG_211), lmprintf(MSG_041));
					PrintInfo(0, MSG_211);
				} else {
					Notification(MB_ICONERROR | MB_CLOSE, lmprintf(MSG_194, GetShortName(url)), lmprintf(MSG_043, WindowsErrorString()));
					PrintInfo(0, MSG_212);
				}
			} else {
				// Download was successful => Select and scan the ISO
				image_path = safe_strdup(img_save.ImagePath);
				PostMessage(hMainDialog, UM_SELECT_ISO, 0, 0);
			}
			safe_free(img_save.ImagePath);
		}
	}

out:
	safe_closehandle(hPipe);
	safe_closehandle(hFile);
	if (icon_path[0] != '\0')
		DeleteFileU(icon_path);
#if !defined(RUFUS_TEST)
	if (script_path[0] != '\0') {
		SetFileAttributesU(script_path, FILE_ATTRIBUTE_NORMAL);
		DeleteFileU(script_path);
	}
#endif
	free(url);
	SendMessage(hMainDialog, UM_ENABLE_CONTROLS, 0, 0);
	dialog_showing--;
	CoUninitialize();
	ExitThread(dwExitCode);
}

BOOL DownloadISO()
{
	if (CreateThread(NULL, 0, DownloadISOThread, NULL, 0, NULL) == NULL) {
		uprintf("Unable to start Windows ISO download thread");
		ErrorStatus = RUFUS_ERROR(APPERR(ERROR_CANT_START_THREAD));
		SendMessage(hMainDialog, UM_ENABLE_CONTROLS, 0, 0);
		return FALSE;
	}
	return TRUE;
}

BOOL IsDownloadable(const char* url)
{
	DWORD dwSize;
	uint64_t dwTotalSize = 0;
	char strsize[32];
	const char* accept_types[] = { "*/*\0", NULL };
	char hostname[64], urlpath[128];
	HINTERNET hSession = NULL, hConnection = NULL, hRequest = NULL;
	URL_COMPONENTSA UrlParts = { sizeof(URL_COMPONENTSA), NULL, 1, (INTERNET_SCHEME)0,
		hostname, sizeof(hostname), 0, NULL, 1, urlpath, sizeof(urlpath), NULL, 1 };

	if (url == NULL)
		return FALSE;

	ErrorStatus = 0;
	DownloadStatus = 404;

	if ((!InternetCrackUrlA(url, (DWORD)safe_strlen(url), 0, &UrlParts))
		|| (UrlParts.lpszHostName == NULL) || (UrlParts.lpszUrlPath == NULL))
		goto out;
	hostname[sizeof(hostname) - 1] = 0;

	// Open an Internet session
	hSession = GetInternetSession(NULL, FALSE);
	if (hSession == NULL)
		goto out;

	hConnection = InternetConnectA(hSession, UrlParts.lpszHostName, UrlParts.nPort, NULL, NULL, INTERNET_SERVICE_HTTP, 0, (DWORD_PTR)NULL);
	if (hConnection == NULL)
		goto out;

	hRequest = HttpOpenRequestA(hConnection, "GET", UrlParts.lpszUrlPath, NULL, NULL, accept_types,
		INTERNET_FLAG_IGNORE_REDIRECT_TO_HTTPS |
		INTERNET_FLAG_NO_COOKIES | INTERNET_FLAG_NO_UI | INTERNET_FLAG_NO_CACHE_WRITE | INTERNET_FLAG_HYPERLINK |
		((UrlParts.nScheme == INTERNET_SCHEME_HTTPS) ? INTERNET_FLAG_SECURE : 0), (DWORD_PTR)NULL);
	if (hRequest == NULL)
		goto out;

	// Must use "Accept-Encoding: identity" to get the file size
	if (!HttpSendRequestA(hRequest, "Accept-Encoding: identity", -1L, NULL, 0))
		goto out;

	// Get the file size
	dwSize = sizeof(DownloadStatus);
	if (!HttpQueryInfoA(hRequest, HTTP_QUERY_STATUS_CODE | HTTP_QUERY_FLAG_NUMBER, (LPVOID)&DownloadStatus, &dwSize, NULL))
		goto out;
	if (DownloadStatus != 200)
		goto out;
	dwSize = sizeof(strsize);
	if (!HttpQueryInfoA(hRequest, HTTP_QUERY_CONTENT_LENGTH, (LPVOID)strsize, &dwSize, NULL) ||
		dwSize >= sizeof(strsize) || !NawamParseContentLength(strsize, dwSize, &dwTotalSize))
		dwTotalSize = 0;

out:
	if (hRequest)
		InternetCloseHandle(hRequest);
	if (hConnection)
		InternetCloseHandle(hConnection);
	if (hSession)
		InternetCloseHandle(hSession);

	return (dwTotalSize > 0);
}
