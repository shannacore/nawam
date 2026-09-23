"""Exercise the real refresh gate; no application execution or physical drives."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_update_policy import function_body
ROOT = Path(__file__).resolve().parents[1]


class SecurityUiTests(unittest.TestCase):
    def test_owned_confirmation_cleanup_and_device_refresh(self):
        function = function_body('src/stdlg.c', 'static void RunSecurityRefresh(HWND hDlg)')
        self.assertIn('MessageBoxExU(hDlg', function, 'Confirmation must be owned by Settings')
        code = r'''
#include <windows.h>
#include <stdio.h>
#include <string.h>
static int creates, prompts, waits, closed, enabled=1, main_enabled=0;
static int result=2, fail_create=0, cancel=0, corrupt_state=0, notices, media, errors;
static BOOL op_in_progress=FALSE, security_refresh_active=FALSE;
static char* image_path=NULL;
static HWND hMainDialog=(HWND)2;
static WORD selected_langid=0x409;
static DWORD ErrorStatus=77;
#define UM_MEDIA_CHANGE (WM_APP+1)
#define MB_IS_RTL 0
#define uprintf(...) ((void)0)
#define IsWindow(h) TRUE
#define IsWindowEnabled(h) ((h)==hMainDialog ? main_enabled : enabled)
#define EnableWindow(h,s) ((h)==hMainDialog ? (main_enabled=(s)) : (enabled=(s)))
#define MessageBoxExU(h,t,c,f,l) notify(h,t,f)
static int notify(HWND owner,const char* text,UINT flags) {
    (void)text;
    if(owner!=(HWND)1 || !security_refresh_active || !op_in_progress || enabled || main_enabled) errors++;
    if((flags & 15)==MB_YESNO) {
        prompts++;
        if(!(flags & MB_DEFBUTTON2)) errors++;
        if(corrupt_state) image_path="unexpected.iso";
        return cancel ? IDNO : IDYES;
    }
    notices++; return IDOK;
}
#define CreateThread(...) create()
static HANDLE create(void) {
    if (!security_refresh_active || !op_in_progress || image_path || enabled || main_enabled) errors++;
    creates++; return fail_create ? NULL : (HANDLE)123;
}
#define GetExitCodeThread(h,r) (*(r)=result,TRUE)
#define CloseHandle(h) (++closed)
#define WaitForSingleObjectWithMessages(h,t) (++waits,WAIT_OBJECT_0)
#define SetCursor(c) ((HCURSOR)0)
#define LoadCursor(a,b) ((HCURSOR)0)
#define WindowsErrorString() "test"
#define RUFUS_ERROR(x) (x)
#define IGNORE_RETVAL(x) ((void)(x))
#define PostMessage(h,m,w,l) post(h,m)
static int post(HWND owner,UINT msg) {
    if(owner!=hMainDialog || msg!=UM_MEDIA_CHANGE || op_in_progress || security_refresh_active) errors++;
    media++; return TRUE;
}
'''
        code += function + r'''
int main(void) {
    op_in_progress=TRUE; RunSecurityRefresh((HWND)1);
    if(creates || !op_in_progress || prompts) return 1;
    op_in_progress=FALSE; image_path="image.iso"; RunSecurityRefresh((HWND)1);
    if(creates || prompts) return 2;
    image_path=NULL; cancel=1; RunSecurityRefresh((HWND)1);
    if(creates || op_in_progress || security_refresh_active || !enabled || main_enabled || media!=1) return 3;
    cancel=0; corrupt_state=1; RunSecurityRefresh((HWND)1);
    if(creates || op_in_progress || security_refresh_active || !enabled) return 4;
    corrupt_state=0; image_path=NULL; fail_create=1; RunSecurityRefresh((HWND)1);
    if(creates!=1 || closed || op_in_progress || security_refresh_active || !enabled) return 5;
    fail_create=0; RunSecurityRefresh((HWND)1);
    if(creates!=2 || closed!=1 || waits!=1 || !enabled || main_enabled) return 6;
    if(op_in_progress || security_refresh_active || ErrorStatus!=77 || media!=4 || errors) return 7;
    return 0;
}'''
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'gate.c'; src.write_text(code,encoding='utf-8'); exe=src.with_suffix('.exe')
            built=subprocess.run([str(ROOT/'tools/w64devkit/bin/gcc.exe'),'-std=gnu11',str(src),'-o',str(exe)],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            self.assertEqual(subprocess.run([str(exe)]).returncode,0)

    def test_main_mutations_are_blocked_while_refresh_owns_data(self):
        text=(ROOT/'src/rufus.c').read_text(encoding='utf-8')
        main=text.split('static INT_PTR CALLBACK MainCallback',1)[1]
        guard=main.split('switch (message)',1)[0]
        self.assertIn('security_refresh_active',guard)
        for message in ['WM_COMMAND','WM_CLOSE','WM_DROPFILES','UM_SELECT_ISO','UM_FORMAT_START']:
            self.assertIn(message,guard)

    def test_refresh_copy_uses_neutral_source_names(self):
        refresh = function_body('src/stdlg.c', 'static void RunSecurityRefresh(HWND hDlg)')
        self.assertNotIn('dari Rufus', refresh)
        self.assertNotIn('from Rufus', refresh)
        self.assertIn('sumber data tepercaya', refresh)
        self.assertIn('trusted data sources', refresh)
        text = (ROOT/'src/stdlg.c').read_text(encoding='utf-8')
        self.assertNotIn('download, or install Rufus releases.', text)
        self.assertNotIn('certificate revocations from Rufus', text)

    def test_manual_refresh_is_not_a_self_update(self):
        text=(ROOT/'src/stdlg.c').read_text(encoding='utf-8')
        callback=text.split('INT_PTR CALLBACK UpdateCallback',1)[1].split('static DWORD WINAPI CheckForFidoThread',1)[0]
        for expected in ['RunSecurityRefresh(hDlg)','Refresh security data','EnableWindow(hFrequency, FALSE)','security_refresh_active']:
            self.assertIn(expected,callback)
        self.assertNotIn('RunSecurityRefresh',function_body('src/stdlg.c','BOOL SetUpdateCheck(void)'))


if __name__=='__main__': unittest.main(verbosity=2)
