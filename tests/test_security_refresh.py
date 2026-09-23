"""Native isolated seams: real refresh/parser code, synthetic test responses only.
No application launch, internet request, registry write, or drive operation.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
GCC = ROOT / 'tools/w64devkit/bin/gcc.exe'


def function(text, signature):
    start = text.index(signature)
    # Function-closing braces in these C sources are at column zero.
    return text[start:text.index('\n}', start) + 2]


def run_c(test, code, args=()):
    with tempfile.TemporaryDirectory(dir=ROOT / 'tests') as d:
        src = Path(d) / 'seam.c'
        exe = src.with_suffix('.exe')
        src.write_text(code, encoding='utf-8')
        result = subprocess.run([str(GCC), '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                 '-I', str(ROOT/'src'), str(src), '-o', str(exe)],
                                capture_output=True, text=True)
        test.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([str(exe), *args], capture_output=True, text=True)
        test.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class SecurityRefreshTests(unittest.TestCase):
    def test_worker_retains_old_data_on_failure_and_reports_partial(self):
        net = (ROOT/'src/net.c').read_text(encoding='utf-8')
        self.assertIn('DWORD WINAPI NawamSecurityRefreshThread(LPVOID', net,
                      'Manual-only security worker is missing')
        parsers = (ROOT/'src/parser.c').read_text(encoding='utf-8')
        source = r'''
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "nawam_safety.h"
#include "nawam_security.h"
#define RUFUS_URL "https://rufus.ie"
#define SHA1_HASHSIZE 20
#define IS_HEXASCII(c) (((c)>='0'&&(c)<='9')||((c)>='a'&&(c)<='f')||((c)>='A'&&(c)<='F'))
#define FROM_HEXASCII(c) ((c)<='9'?(c)-'0':((c)|32)-'a'+10)

#define safe_free(p) do { free(p); (p)=NULL; } while(0)
#define IGNORE_RETVAL(x) ((void)(x))
#define uprintf(...) ((void)0)
typedef struct { char* product; uint32_t version; } sbat_entry_t;
typedef struct { uint32_t count; uint8_t list[0][20]; } thumbprint_list_t;
char *sbat_level_txt, *sb_active_txt, *sb_revoked_txt, *image_path;
sbat_entry_t* sbat_entries;
thumbprint_list_t *sb_active_certs, *sb_revoked_certs;
BOOL op_in_progress = TRUE;
DWORD ErrorStatus;
static int scenario, downloads;
static uint64_t DownloadToFileOrBuffer(const char* url, const char* file, BYTE** out, HWND h, BOOL b) {
    const char* s;
    (void)h; (void)b;
    if (file || strncmp(url,"https://rufus.ie/",17) || strstr(url,".ver") || strstr(url,".exe")) abort();
    downloads++;
    *out = NULL;
    if (scenario == 0) return 0;
    if (strstr(url,"sbat_level.txt")) s = "# fixture\nsbat,1,2025051000\nshim,4\nBOOTMGRSECURITYVERSIONNUMBER,0x70000\n";
    else if (strstr(url,"sb_active.txt")) s = "0123456789abcdef0123456789abcdef01234567\n";
    else if (strstr(url,"sb_revoked.txt")) s = "89abcdef0123456789abcdef0123456789abcdef\n";
    else abort();
    if (scenario == 2 || (scenario == 3 && strstr(url,"sb_active.txt"))) s = "<html>error</html>";
    if (scenario == 4) s = "shim,4\ntrailing corrupt row";
    *out = (BYTE*)strdup(s);
    return strlen(s);
}
static void NawamRefreshDbx(unsigned* ok, unsigned* failed) {
    if (scenario == 1) (*ok)++; else (*failed)++;
}
'''
        source += function(parsers, 'sbat_entry_t* GetSbatEntries(') + '\n'
        source += function(parsers, 'thumbprint_list_t* GetThumbprintEntries(') + '\n'
        start = net.index('/* NAWAM_SECURITY_TEXT_BEGIN */')
        end = net.index('/* NAWAM_SECURITY_TEXT_END */', start)
        source += net[start:end]
        source += r'''
int main(void) {
    char *old_sbat, *old_active, *old_revoked;
    sbat_entry_t* old_entries;
    thumbprint_list_t *old_a, *old_r;
    sbat_level_txt = strdup("shim,1\n"); sbat_entries = GetSbatEntries(sbat_level_txt);
    sb_active_txt = strdup("1111111111111111111111111111111111111111\n");
    sb_revoked_txt = strdup("2222222222222222222222222222222222222222\n");
    sb_active_certs = GetThumbprintEntries(sb_active_txt); sb_revoked_certs = GetThumbprintEntries(sb_revoked_txt);
    old_sbat=sbat_level_txt; old_active=sb_active_txt; old_revoked=sb_revoked_txt;
    old_entries=sbat_entries; old_a=sb_active_certs; old_r=sb_revoked_certs;
    for (int i=0; i<3; i++) {
        scenario = i == 0 ? 0 : i == 1 ? 2 : 4;
        if (NawamSecurityRefreshThread(NULL) != 0) return 10+i;
        if (sbat_level_txt!=old_sbat || sb_active_txt!=old_active || sb_revoked_txt!=old_revoked ||
            sbat_entries!=old_entries || sb_active_certs!=old_a || sb_revoked_certs!=old_r) return 20+i;
    }
    scenario=3;
    if (NawamSecurityRefreshThread(NULL)!=1 || sb_active_certs!=old_a || sb_active_txt!=old_active) return 30;
    if (strcmp(sbat_entries[1].product,"shim") || sbat_entries[1].version!=4) return 31;
    scenario=1;
    if (NawamSecurityRefreshThread(NULL)!=2 || sb_active_certs->count!=1) return 32;
    downloads=0; image_path="fixture.iso";
    if (NawamSecurityRefreshThread(NULL)!=0 || downloads) return 33;
    image_path=NULL; op_in_progress=FALSE;
    if (NawamSecurityRefreshThread(NULL)!=0 || downloads) return 34;
    free(sbat_entries); free(sbat_level_txt); free(sb_active_certs); free(sb_active_txt);
    free(sb_revoked_certs); free(sb_revoked_txt);
    return 0;
}
'''
        run_c(self, source)


class DbxRefreshTests(unittest.TestCase):
    def test_complete_timestamp_json_and_calendar(self):
        source = r'''
#include "nawam_security.h"
#define CHECK(s, expected) do { uint64_t t=0; char sha[41]; \
    if (!!NawamCommitTimestamp(s,sizeof(s)-1,&t,sha) != (expected)) return __LINE__; } while(0)
int main(void) {
#define GOOD "[{\"sha\":\"0123456789abcdef0123456789abcdef01234567\",\"commit\":{\"committer\":{\"date\":\"2026-09-01T22:05:39Z\"}}}]"
    CHECK(GOOD, 1);
    CHECK(GOOD "trailing", 0);
    CHECK("[]", 0);
    CHECK("[{\"date\":\"2026-09-01T22:05:39Z\"}]", 0);
    CHECK("[{\"sha\":\"0123456789abcdef0123456789abcdef01234567\",\"commit\":{\"committer\":{\"date\":\"2026-02-30T22:05:39Z\"}}}]", 0);
    CHECK("[{\"sha\":\"0123456789abcdef0123456789abcdef01234567\",\"commit\":{\"committer\":{\"date\":\"2026-09-01T22:05:39Zjunk\"}}}]", 0);
    return 0;
}'''
        run_c(self, source)

    def test_atomic_dbx_cache_and_refresh_failure(self):
        net = (ROOT/'src/net.c').read_text(encoding='utf-8')
        self.assertTrue('/* NAWAM_SECURITY_DBX_BEGIN */' in net, 'Validated atomic DBX refresh is missing')
        begin = net.index('/* NAWAM_SECURITY_DBX_BEGIN */')
        end = net.index('/* NAWAM_SECURITY_DBX_END */', begin)
        block = net[begin:end]
        self.assertNotIn('_chdir', block)
        self.assertIn('MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH', block)
        source = r'''
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <time.h>
#include "nawam_security.h"
#include "nawam_safety.h"
#define FILES_DIR "files"
#define uprintf(...) ((void)0)
#define safe_free(p) do { free(p); (p)=NULL; } while(0)
#define static_sprintf(a,...) snprintf(a,sizeof(a),__VA_ARGS__)
static char* app_data_dir;
static const char* efi_archname[] = {"unknown","x64"};
static struct { const char* url; uint64_t timestamp; } dbx_info[] = {
 {"https://api.github.com/repos/microsoft/secureboot_objects/contents/PostSignedObjects/SignedByKEK2023/dbx_x64.efiauth2",1}};
static uint64_t stored;
static int scenario, commits, moves;
static BYTE fixture[116];
static int64_t ReadSetting64(const char* key) { (void)key; return stored; }
static BOOL WriteSetting64(const char* key, int64_t value) { (void)key; stored=value; commits++; return TRUE; }
static wchar_t* utf8_to_wchar(const char* s) { int n=MultiByteToWideChar(CP_UTF8,0,s,-1,NULL,0); wchar_t* w=calloc(n,sizeof(*w)); MultiByteToWideChar(CP_UTF8,0,s,-1,w,n); return w; }
static BOOL test_move(const wchar_t* a, const wchar_t* b, DWORD flags) {
 if (flags!=(MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH)) abort();
 if (scenario==3) return FALSE;
 moves++; return MoveFileExW(a,b,flags);
}
#define MoveFileExW test_move
static uint64_t DownloadToFileOrBuffer(const char* u,const char* f,BYTE** b,HWND w,BOOL v) {
 (void)w; (void)v; if(f) abort(); *b=NULL;
 if (scenario==0) return 0;
 if (strstr(u,"commits?path=")) {
  const char* s="[{\"sha\":\"0123456789abcdef0123456789abcdef01234567\",\"commit\":{\"committer\":{\"date\":\"2026-09-01T22:05:39Z\"}}}]";
  *b=(BYTE*)strdup(s); return strlen(s);
 }
 if (!strstr(u,"?ref=0123456789abcdef0123456789abcdef01234567")) abort();
 *b=malloc(sizeof(fixture)); memcpy(*b,fixture,sizeof(fixture));
 if (scenario==2) (*b)[64]=0;
 return sizeof(fixture);
}
'''
        source += block
        source += r'''
int main(int argc,char** argv) {
 unsigned ok,failed; BYTE* data=NULL; DWORD n=0; char path[MAX_PATH];
 static const BYTE sha256[] = {0x26,0x16,0xc4,0xc1,0x4c,0x50,0x92,0x40,0xac,0xa9,0x41,0xf9,0x36,0x93,0x43,0x28};
 if(argc!=2) return 1;
 app_data_dir=argv[1];
 fixture[16]=24; fixture[56]=76; fixture[64]=48; memcpy(fixture+40,sha256,16);
 for(scenario=0;scenario<4;scenario++) {
   ok=failed=0; NawamRefreshDbx(&ok,&failed);
   if (scenario==1) { if(ok!=1||failed||commits!=1||moves!=1) return 2; stored=0; }
   else if(ok||failed!=1||stored) return 3;
 }
 static_sprintf(path,"%s\\files\\dbx_x64.bin",app_data_dir);
 if(!NawamReadDbxCache(path,&data,&n) || n!=116 || memcmp(data,fixture,n)) return 4;
 free(data); scenario=1; stored=UINT64_MAX;
 ok=failed=0; NawamRefreshDbx(&ok,&failed);
 if(!failed || ok || commits!=1 || moves!=1) return 5;
 return 0;
}'''
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as d:
            run_c(self, source, (d,))


if __name__ == '__main__':
    unittest.main(verbosity=2)
