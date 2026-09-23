"""Package actual verified application/source. Never include credentials/toolchains."""
from pathlib import Path
import json
import os
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / 'website/public'
sys.path.insert(0, str(ROOT / 'scripts'))
from release_support import require, sha256, validate_pe, verify_provenance

exe = ROOT / 'dist/Nawam.exe'
data = exe.read_bytes()
info = validate_pe(ROOT, data)
provenance = verify_provenance(ROOT, data)
version = info['FileVersion']
files = dict(provenance['sources'])
provenance_bytes = (json.dumps(provenance, indent=2) + '\n').encode('utf-8')
files['docs/build-provenance.json'] = sha256(provenance_bytes)
dest = WEB / 'downloads'
dest.mkdir(exist_ok=True)
archive_name = f'Nawam-{version}-source.zip'
base_url = f'https://github.com/shannacore/nawam/releases/download/v{version}'
# Invalid or changing inputs must never replace previously published metadata.
with tempfile.TemporaryDirectory(prefix='.release-', dir=dest) as scratch:
    stage = Path(scratch)
    archive = stage / archive_name
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, digest in sorted(files.items()):
            content = provenance_bytes if name == 'docs/build-provenance.json' else (ROOT / name).read_bytes()
            require(sha256(content) == digest, f'Source changed while packaging: {name}')
            z.writestr('Nawam/' + name, content)
    with zipfile.ZipFile(archive) as z:
        require(z.testzip() is None, 'Corrupt source ZIP')
        require(sorted(z.namelist()) == sorted('Nawam/' + name for name in files), 'Source ZIP members mismatch')
        for name, digest in files.items():
            require(sha256(z.read('Nawam/' + name)) == digest, f'Source ZIP SHA256 mismatch: {name}')
    (stage / 'Nawam.exe').write_bytes(data)
    require(sha256((stage / 'Nawam.exe').read_bytes()) == provenance['sha256'], 'Download SHA256 mismatch')
    verify_provenance(ROOT, exe.read_bytes())
    require(exe.read_bytes() == data, 'Executable changed while packaging')
    distribution = data
    compact = ROOT / 'dist/compact/Nawam.exe'
    report_path = ROOT / 'docs/compact-validation.json'
    if compact.exists() or report_path.exists():
        require(compact.is_file() and report_path.is_file(), 'Incomplete compact verification')
        report = json.loads(report_path.read_text())
        distribution = compact.read_bytes()
        require(report.get('originalSha256') == sha256(data) and
                report.get('compressedSha256') == sha256(distribution) and
                report.get('version') == version and report.get('resourceContentsIdentical') is True and
                report.get('importsIdentical') is True and report.get('peHardeningPreserved') is True,
                'Compact verification does not match current executable')
        validate_pe(ROOT, distribution)
    (stage / 'Nawam-unpacked.exe').write_bytes(data)
    (stage / 'Nawam.exe').write_bytes(distribution)
    manifest = dict(version=version, available=True, architecture='x64',
                    url=base_url + '/Nawam.exe', sha256=sha256(distribution), bytes=len(distribution),
                    sourceUrl=base_url + '/' + archive_name, sourceSha256=sha256(archive.read_bytes()),
                    sourceFiles=len(files), signed=False)
    sums = f"{manifest['sha256']}  Nawam.exe\n{sha256(data)}  Nawam-unpacked.exe\n{manifest['sourceSha256']}  {archive_name}\n"
    (stage / 'SHA256SUMS.txt').write_text(sums, encoding='ascii')
    (stage / 'release.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    for name in ('Nawam.exe', 'Nawam-unpacked.exe', archive_name, 'SHA256SUMS.txt'):
        os.replace(stage / name, dest / name)
    require(sha256((dest / 'Nawam.exe').read_bytes()) == manifest['sha256'], 'Published executable SHA256 mismatch')
    require(sha256((dest / archive_name).read_bytes()) == manifest['sourceSha256'], 'Published ZIP SHA256 mismatch')
    os.replace(stage / 'release.json', WEB / 'release.json')
print(json.dumps(manifest, indent=2))
