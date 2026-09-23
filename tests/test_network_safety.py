"""Compile real pure-C guards; test hostile lengths without any disk operations."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NetworkSafetyTests(unittest.TestCase):
    def test_length_and_dbx_guards(self):
        header = ROOT / 'src/nawam_safety.h'
        self.assertTrue(header.exists(), 'Download guards must exist before network refresh')
        code = r'''
#include "nawam_safety.h"
#include <string.h>
int main(void) {
    unsigned char dbx[128] = {0};
    const unsigned char sha256[16] = {0x26,0x16,0xc4,0xc1,0x4c,0x50,0x92,0x40,0xac,0xa9,0x41,0xf9,0x36,0x93,0x43,0x28};
    if (!NawamDownloadLengthValid(1024, 1)) return 1;
    if (NawamDownloadLengthValid(0, 1)) return 2;
    if (NawamDownloadLengthValid(UINT64_MAX, 1)) return 3;
    if (NawamDownloadLengthValid(1024ULL*1024*1024, 1)) return 4;
    if (!NawamDownloadLengthValid(16ULL*1024*1024*1024, 0)) return 5;
    if (!NawamDownloadChunkValid(100, 90, 10)) return 6;
    if (NawamDownloadChunkValid(100, 90, 11)) return 7;
    if (NawamDownloadChunkValid(100, 101, 0)) return 8;
    if (NawamDownloadChunkValid(100, 90, UINT64_MAX)) return 9;
    if (NawamDbxValid(dbx, sizeof(dbx))) return 10;
    /* EFI_TIME(16) + certificate length24 + list28 + SHA256 signature48 */
    dbx[16] = 24; dbx[56] = 76; dbx[64] = 48;
    memcpy(dbx + 40, sha256, 16);
    if (!NawamDbxValid(dbx, 116)) return 11;
    if (NawamDbxValid(dbx, 115)) return 12;
    dbx[64] = 0;
    if (NawamDbxValid(dbx, 116)) return 13;
    dbx[64] = 16;
    if (NawamDbxValid(dbx, 116)) return 16;
    dbx[64] = 48; dbx[56] = 28;
    if (NawamDbxValid(dbx, 68)) return 17;
    dbx[56] = 76;
    if (NawamDbxValid(dbx, 117)) return 18;
    dbx[64] = 48; dbx[60] = 255;
    if (NawamDbxValid(dbx, 116)) return 14;
    dbx[60] = 0; memset(dbx + 16, 255, 4);
    if (NawamDbxValid(dbx, 116)) return 15;
    return 0;
}'''
        with tempfile.TemporaryDirectory(dir=ROOT / 'tests') as d:
            src = Path(d) / 'guard.c'; exe = src.with_suffix('.exe')
            src.write_text(code)
            subprocess.run([str(ROOT/'tools/w64devkit/bin/gcc.exe'), '-Wall', '-Wextra', '-Werror',
                            '-I', str(ROOT/'src'), str(src), '-o', str(exe)], check=True)
            self.assertEqual(subprocess.run([str(exe)]).returncode, 0)

    def test_guards_are_used_before_copy_or_disk_cache_commit(self):
        text = (ROOT/'src/net.c').read_text(encoding='utf-8')
        begin = text.index('uint64_t DownloadToFileOrBufferEx')
        end = text.index('// Download and validate a signed file.', begin)
        downloader = text[begin:end]
        self.assertIn('NawamDownloadLengthValid(total_size, file == NULL)', downloader)
        self.assertLess(downloader.index('NawamDownloadChunkValid'), downloader.index('memcpy(&(*buffer)[size]'))
        self.assertTrue('NawamDbxValid' in text, 'DBX data must be validated before commit')
        self.assertNotRegex(text, r'\bINTERNET_FLAG_IGNORE_REDIRECT_TO_HTTP\b')
        self.assertIn('if (!HttpSendRequestA', downloader)
        self.assertIn('if (!HttpQueryInfoA(hRequest, HTTP_QUERY_STATUS_CODE', downloader)
        self.assertIn('NawamParseContentLength', downloader)
        self.assertNotIn('|| (dwDownloaded == 0)', downloader)

    def test_network_session_and_probe_fail_closed(self):
        text = (ROOT/'src/net.c').read_text(encoding='utf-8')
        session = text[text.index('static HINTERNET GetInternetSession'):text.index('uint64_t DownloadToFileOrBufferEx')]
        self.assertIn('INetworkListManager_Release', session)
        self.assertIn('SUCCEEDED(com_result)', session)
        self.assertIn('CoUninitialize()', session)
        probe = text[text.index('BOOL IsDownloadable('):]
        self.assertIn('NawamParseContentLength', probe)
        self.assertIn('if (!HttpQueryInfoA(hRequest, HTTP_QUERY_CONTENT_LENGTH', probe)

    def test_strict_content_length(self):
        code = r'''
#include "nawam_safety.h"
#include <string.h>
int main(void) {
    uint64_t n = 0;
    const char* bad[] = {"", "0", "-1", "+1", " 1", "1 ", "12junk",
        "18446744073709551616", "1,1"};
    for (size_t i = 0; i < sizeof(bad)/sizeof(bad[0]); ++i)
        if (NawamParseContentLength(bad[i], strlen(bad[i]), &n)) return 1;
    if (!NawamParseContentLength("18446744073709551615", 20, &n) || n != UINT64_MAX) return 2;
    if (NawamParseContentLength("1\0x", 3, &n)) return 3;
    return 0;
}'''
        with tempfile.TemporaryDirectory(dir=ROOT / 'tests') as d:
            src = Path(d) / 'length.c'; exe = src.with_suffix('.exe')
            src.write_text(code)
            build = subprocess.run([str(ROOT/'tools/w64devkit/bin/gcc.exe'), '-Wall', '-Wextra', '-Werror',
                                    '-I', str(ROOT/'src'), str(src), '-o', str(exe)], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            self.assertEqual(subprocess.run([str(exe)]).returncode, 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
