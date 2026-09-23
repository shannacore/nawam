"""Fail-closed shared checks for Nawam builds and corresponding source releases."""
from pathlib import Path, PurePosixPath, PureWindowsPath
import hashlib
import json
import re
import sys


class ReleaseError(ValueError):
    """An artifact cannot be safely released."""


def require(condition, message):
    if not condition:
        raise ReleaseError(message)


def resource_metadata(root):
    text = (Path(root) / 'src/rufus.rc').read_text(encoding='utf-8-sig')
    expected = {'ProductName': 'Nawam', 'OriginalFilename': 'Nawam.exe',
                'CompanyName': 'Shanna Studio', 'Comments': 'https://nawam.shanna.id'}
    for key in (*expected, 'FileVersion', 'ProductVersion'):
        values = re.findall(r'VALUE\s+"' + key + r'"\s*,\s*"([^"\r\n]+)"', text)
        require(len(values) == 1, f'Missing/ambiguous resource {key}')
        if key in expected:
            require(values[0] == expected[key], f'Unexpected resource {key}')
        else:
            require(re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', values[0]),
                    f'Invalid resource {key}')
            expected[key] = values[0]
    require(expected['FileVersion'] == expected['ProductVersion'], 'Resource versions disagree')
    numeric = tuple(map(int, expected['FileVersion'].split('.'))) + (0,)
    require(all(n <= 65535 for n in numeric), 'Resource version exceeds WORD range')
    for key in ('FILEVERSION', 'PRODUCTVERSION'):
        values = re.findall(r'^\s*' + key + r'\s+(\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*\d+)\s*$', text, re.M)
        require(len(values) == 1 and tuple(map(int, values[0].split(','))) == numeric,
                f'Resource numeric {key} disagrees with string version')
    return expected, numeric


def validate_pe(root, data):
    sys.path.insert(0, str(Path(root) / 'tools/python'))
    import pefile
    expected, numeric = resource_metadata(root)
    with pefile.PE(data=data) as pe:
        require(pe.FILE_HEADER.Machine == 0x8664, 'Expected x64 PE')
        require(pe.OPTIONAL_HEADER.Magic == 0x20b, 'Expected PE32+ x64 image')
        require(pe.OPTIONAL_HEADER.Subsystem == 2, 'Expected Windows GUI application')
        require(pe.OPTIONAL_HEADER.DllCharacteristics & 0x140 == 0x140, 'DEP/ASLR missing')
        config = getattr(getattr(pe, 'DIRECTORY_ENTRY_LOAD_CONFIG', None), 'struct', None)
        require(getattr(config, 'DependentLoadFlags', None) == 0x800, 'DependentLoadFlags must be 0x800')
        tables = [table for group in getattr(pe, 'FileInfo', []) for item in group
                  if hasattr(item, 'StringTable') for table in item.StringTable]
        require(bool(tables), 'Missing PE version metadata')
        info = {}
        for table in tables:
            info = {k.decode(): v.decode() for k, v in table.entries.items()}
            for key, value in expected.items():
                require(info.get(key) == value, f'PE {key} does not match current resource: {value}')
        fixed = getattr(pe, 'VS_FIXEDFILEINFO', [])
        require(bool(fixed), 'Missing fixed PE versions')
        for entry in fixed:
            for prefix in ('File', 'Product'):
                ms, ls = getattr(entry, prefix + 'VersionMS'), getattr(entry, prefix + 'VersionLS')
                require((ms >> 16, ms & 65535, ls >> 16, ls & 65535) == numeric,
                        f'PE fixed {prefix}Version does not match current resource')
        return info


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def source_snapshot(root, include_generated=True):
    root = Path(root).resolve()
    baseline = json.loads((root / 'docs/upstream-sha256.json').read_text(encoding='utf-8'))
    require(isinstance(baseline, dict) and bool(baseline), 'Invalid upstream source manifest')
    renames = {'rufus.sln': 'Nawam.sln', '.vs/rufus.vcxproj': '.vs/Nawam.vcxproj',
               '.vs/rufus.vcxproj.filters': '.vs/Nawam.vcxproj.filters'}
    files = {renames.get(name, name) for name in baseline}
    for name in ('BUILD.md', 'NOTICE.md'):
        if (root / name).is_file():
            files.add(name)
    files.update(['README.upstream.md', 'src/rufus.rc', 'src/nawam_policy.h',
                  'res/nawam.ico', 'res/nawam.png', 'res/nawam.svg', 'res/nawam.ini',
                  'docs/upstream-sha256.json', 'docs/CHANGE-REPORT.md',
                  'scripts/build.py', 'scripts/verify_about_build.py',
                  'scripts/release_support.py', 'website/scripts/package_release.py'])
    if include_generated:
        files.add('res/hogger/nawam-hogger.exe')
    for directory in ('scripts', 'tests'):
        files.update(p.relative_to(root).as_posix() for p in (root / directory).glob('*.py'))
    # New source/header files must enter both provenance and corresponding ZIPs.
    for p in (root / 'src').rglob('*'):
        if p.is_file() and p.suffix.lower() in ('.c', '.h', '.rc', '.in', '.am', '.s', '.asm'):
            files.add(p.relative_to(root).as_posix())
    result = {}
    for name in sorted(files):
        posix, win = PurePosixPath(name), PureWindowsPath(name)
        require(name == posix.as_posix() and not posix.is_absolute() and not win.drive
                and '\\' not in name and ':' not in name and '..' not in posix.parts,
                f'Unsafe source path: {name}')
        parts = tuple(part.lower() for part in posix.parts)
        require(not any(part in ('tools', 'node_modules', '__pycache__', '.git')
                        or part.startswith('.env') or 'service-account' in part
                        or 'credential' in part for part in parts)
                and posix.suffix.lower() not in ('.log', '.pyc', '.pyo'),
                f'Excluded source path: {name}')
        path = root / name
        require(path.resolve().is_relative_to(root) and path.is_file()
                and not any(p.is_symlink() for p in (path, *path.parents)),
                f'Missing/unsafe source file: {name}')
        result[name] = sha256(path.read_bytes())
    return result


def make_provenance(root, data, sources):
    require(sources == source_snapshot(root), 'Build source changed; rebuild before release')
    info = validate_pe(root, data)
    return dict(schema=1, version=info['FileVersion'], publisher=info['CompanyName'],
                appUrl=info['Comments'], sha256=sha256(data), bytes=len(data),
                metadata=info, sources=sources)


def verify_provenance(root, data, path=None):
    path = Path(path) if path is not None else Path(root) / 'docs/build-provenance.json'
    require(path.is_file(), f'Missing build provenance: {path}; rebuild with scripts/build.py')
    record = json.loads(path.read_text(encoding='utf-8'))
    require(isinstance(record, dict) and record.get('schema') == 1, 'Unsupported build provenance schema')
    require(record.get('sha256') == sha256(data) and record.get('bytes') == len(data),
            'Build provenance SHA256/size mismatch; stale executable')
    require(record.get('sources') == source_snapshot(root), 'Build provenance source mismatch; rebuild')
    require(record == make_provenance(root, data, record['sources']), 'Build provenance metadata mismatch')
    return record
