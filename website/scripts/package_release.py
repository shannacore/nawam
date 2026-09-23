"""Package actual verified application/source. Never include credentials/toolchains."""
from pathlib import Path
import hashlib
import json
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / 'website/public'
sys.path.insert(0, str(ROOT / 'tools/python'))
import pefile
exe = ROOT / 'dist/Nawam.exe'
pe = pefile.PE(str(exe))
info = {k.decode(): v.decode() for group in pe.FileInfo for item in group
        if hasattr(item, 'StringTable') for table in item.StringTable for k, v in table.entries.items()}
assert info['ProductName'] == 'Nawam' and info['FileVersion'] == '1.0.1'
assert pe.FILE_HEADER.Machine == 0x8664
assert pe.DIRECTORY_ENTRY_LOAD_CONFIG.struct.DependentLoadFlags == 0x800
pe.close()
files = set(json.loads((ROOT / 'docs/upstream-sha256.json').read_text()))
files.update(['README.upstream.md', 'src/nawam_policy.h', 'res/nawam.ico',
              'res/nawam.png', 'res/nawam.svg', 'res/nawam.ini', 'res/hogger/nawam-hogger.exe',
              'docs/upstream-sha256.json', 'docs/CHANGE-REPORT.md'])
for directory in ('scripts', 'tests'):
    files.update(p.relative_to(ROOT).as_posix() for p in (ROOT / directory).glob('*.py'))
files = sorted(files)
assert all((ROOT / file).is_file() for file in files)
assert not any('..' in Path(file).parts or Path(file).is_absolute() for file in files)
assert not any(x in file for file in files for x in ('node_modules', 'service-account', '.env', 'tools/'))
dest = WEB / 'downloads'
dest.mkdir(exist_ok=True)
shutil.copy2(exe, dest / 'Nawam.exe')
archive = dest / 'Nawam-1.0.1-source.zip'
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for file in files:
        z.write(ROOT / file, 'Nawam/' + file)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert len(z.namelist()) == len(files)
    assert z.read('Nawam/src/rufus.c') == (ROOT / 'src/rufus.c').read_bytes()
hash_of = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
manifest = {'version':'1.0.1', 'available':True, 'architecture':'x64',
            'url':'https://github.com/shannacore/nawam-releases/releases/download/v1.0.1/Nawam.exe', 'sha256':hash_of(exe),
            'bytes':exe.stat().st_size, 'sourceUrl':'https://github.com/shannacore/nawam-releases/releases/download/v1.0.1/Nawam-1.0.1-source.zip',
            'sourceSha256':hash_of(archive), 'sourceFiles':len(files), 'signed':False}
(WEB / 'release.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
(dest / 'SHA256SUMS.txt').write_text(hash_of(exe)+'  Nawam.exe\n'+hash_of(archive)+'  Nawam-1.0.1-source.zip\n')
(ROOT / 'dist/SHA256SUMS.txt').write_text(hash_of(exe)+'  Nawam.exe\n')
print(json.dumps(manifest, indent=2))
