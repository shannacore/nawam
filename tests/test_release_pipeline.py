"""Release regression tests use disposable trees and never execute the PE."""
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/python'))
import pefile


class ReleasePipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='nawam-release-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        paths = ['src/rufus.rc', 'src/rufus.c', 'src/license.h',
                 'README.upstream.md', 'src/nawam_policy.h', 'res/nawam.ico',
                 'res/nawam.png', 'res/nawam.svg', 'res/nawam.ini',
                 'res/hogger/nawam-hogger.exe', 'docs/CHANGE-REPORT.md',
                 'scripts/build.py', 'scripts/verify_about_build.py',
                 'website/scripts/package_release.py', 'dist/Nawam.exe']
        if (ROOT / 'scripts/release_support.py').exists():
            paths.append('scripts/release_support.py')
        for name in paths:
            dest = self.root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, dest)
        (self.root / 'website/public').mkdir()
        baseline = {name: hashlib.sha256((self.root / name).read_bytes()).hexdigest()
                    for name in ('src/rufus.c', 'src/rufus.rc', 'src/license.h')}
        self.write_json('docs/upstream-sha256.json', baseline)
        # The parent may bump its resource before rebuilding; fixtures describe
        # the existing real PE, not an assumed current release number.
        with pefile.PE(str(self.root / 'dist/Nawam.exe')) as pe:
            info = {k.decode(): v.decode() for g in pe.FileInfo for i in g
                    if hasattr(i, 'StringTable') for t in i.StringTable
                    for k, v in t.entries.items()}
        self.version = info['FileVersion']
        resource = self.root / 'src/rufus.rc'
        text = resource.read_text(encoding='utf-8-sig')
        for key in ('FileVersion', 'ProductVersion'):
            text = re.sub(r'(VALUE "' + key + r'", ")[^"]+',
                          lambda m: m[1] + info[key], text)
        numeric = ','.join((self.version.split('.') + ['0'])[:4])
        text = re.sub(r'((?:FILE|PRODUCT)VERSION )[^\n]+',
                      lambda m: m[1] + numeric, text)
        resource.write_text(text, encoding='utf-8')

    def write_json(self, name, value):
        (self.root / name).write_text(json.dumps(value), encoding='utf-8')

    def run_script(self, name, optimized=True):
        env = dict(os.environ, PYTHONPATH=str(ROOT / 'tools/python'))
        return subprocess.run([sys.executable, *(['-O'] if optimized else []),
                               str(self.root / name)], cwd=self.root, env=env,
                              capture_output=True, text=True)

    def support(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('release_fixture_support',
                                                    self.root / 'scripts/release_support.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(callable(getattr(module, 'make_provenance', None)),
                        'Missing builder provenance writer')
        return module

    def test_provenance_binds_binary_and_all_current_sources(self):
        support = self.support()
        header = self.root / 'src/new_safety.h'
        header.write_text('/* fixture source */', encoding='utf-8')
        data = (self.root / 'dist/Nawam.exe').read_bytes()
        snapshot = support.source_snapshot(self.root)
        record = support.make_provenance(self.root, data, snapshot)
        self.write_json('docs/build-provenance.json', record)
        self.assertEqual(support.verify_provenance(self.root, data), record)
        for name in ('src/rufus.rc', 'src/new_safety.h', 'scripts/build.py',
                     'scripts/release_support.py', 'website/scripts/package_release.py'):
            self.assertIn(name, record['sources'])
        with self.assertRaisesRegex(ValueError, 'SHA256'):
            support.verify_provenance(self.root, data + b'changed')
        header.write_text('/* changed after build */', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'source'):
            support.verify_provenance(self.root, data)
        with self.assertRaisesRegex(ValueError, 'source'):
            support.make_provenance(self.root, data, snapshot)

    def test_future_version_zip_contains_exact_provenance_sources(self):
        import zipfile
        exe = self.root / 'dist/Nawam.exe'
        data = bytearray(exe.read_bytes())
        with pefile.PE(data=data) as pe:
            for g in pe.FileInfo:
                for item in g:
                    for table in getattr(item, 'StringTable', []):
                        for key in (b'FileVersion', b'ProductVersion'):
                            offset = table.entries_offsets[key][1]
                            self.assertEqual(len(table.entries[key]), 5)
                            data[offset:offset + 10] = '9.8.7'.encode('utf-16le')
            for field, value in [('FileVersionMS', 0x90008), ('FileVersionLS', 0x70000),
                                 ('ProductVersionMS', 0x90008), ('ProductVersionLS', 0x70000)]:
                struct.pack_into('<I', data, pe.VS_FIXEDFILEINFO[0].get_field_absolute_offset(field), value)
        exe.write_bytes(data)
        rc = self.root / 'src/rufus.rc'
        text = rc.read_text().replace(self.version, '9.8.7')
        text = re.sub(r'((?:FILE|PRODUCT)VERSION )[^\n]+', r'\g<1>9,8,7,0', text)
        rc.write_text(text, encoding='utf-8')
        (self.root / 'src/new_safety.h').write_text('/* new header */', encoding='utf-8')
        support = self.support()
        record = support.make_provenance(self.root, data, support.source_snapshot(self.root))
        self.write_json('docs/build-provenance.json', record)
        result = self.run_script('website/scripts/package_release.py')
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((self.root / 'website/public/release.json').read_text())
        self.assertEqual(manifest['version'], '9.8.7')
        self.assertIn('/v9.8.7/', manifest['url'])
        dest = self.root / 'website/public/downloads'
        self.assertEqual(support.sha256((dest / 'Nawam.exe').read_bytes()), record['sha256'])
        with zipfile.ZipFile(dest / 'Nawam-9.8.7-source.zip') as archive:
            for name, digest in record['sources'].items():
                self.assertEqual(support.sha256(archive.read('Nawam/' + name)), digest, name)
            self.assertEqual(json.loads(archive.read('Nawam/docs/build-provenance.json')), record)
            self.assertEqual(manifest['sourceFiles'], len(archive.namelist()))

    def test_optimized_about_rejects_missing_legal_text(self):
        header = self.root / 'src/license.h'
        header.write_text(header.read_text(encoding='utf-8').replace('Nawam', 'MissingFixtureText'), encoding='utf-8')
        support = self.support()
        data = (self.root / 'dist/Nawam.exe').read_bytes()
        self.write_json('docs/build-provenance.json',
                        support.make_provenance(self.root, data, support.source_snapshot(self.root)))
        result = self.run_script('scripts/verify_about_build.py')
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('missing or truncated', result.stderr)

    def test_build_checks_are_explicit_and_record_provenance(self):
        import ast
        tree = ast.parse((ROOT / 'scripts/build.py').read_text())
        self.assertFalse(any(isinstance(n, ast.Assert) for n in ast.walk(tree)))
        calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertTrue({'validate_pe', 'make_provenance', 'source_snapshot'} <= calls)
        invalidations = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                         and isinstance(n.func, ast.Attribute) and n.func.attr == 'unlink']
        self.assertTrue(any('res/loc/embedded.loc' in ast.unparse(n) for n in invalidations),
                        'Generated localization must not survive a changed embedded.sed')

    def test_stale_source_does_not_replace_existing_release(self):
        support = self.support()
        data = (self.root / 'dist/Nawam.exe').read_bytes()
        self.write_json('docs/build-provenance.json',
                        support.make_provenance(self.root, data, support.source_snapshot(self.root)))
        public = self.root / 'website/public/release.json'
        public.write_text('previous release', encoding='utf-8')
        (self.root / 'scripts/build.py').write_text('# changed after build', encoding='utf-8')
        result = self.run_script('website/scripts/package_release.py')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('source mismatch', result.stderr)
        self.assertEqual(public.read_text(), 'previous release')

    def test_source_paths_fail_closed(self):
        support = self.support()
        for name in ('../escape', 'C:/escape', 'src/../../escape', 'tools/key.py',
                     '.env', 'docs/service-account.json', 'src/session.log'):
            with self.subTest(name=name):
                self.write_json('docs/upstream-sha256.json', {name: '0' * 64})
                with self.assertRaisesRegex(ValueError, 'source path'):
                    support.source_snapshot(self.root)

    def test_packager_requires_builder_provenance(self):
        result = self.run_script('website/scripts/package_release.py')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('provenance', result.stderr.lower())
        self.assertFalse((self.root / 'website/public/release.json').exists())

    def test_optimized_packager_rejects_invalid_runtime_contract(self):
        exe = self.root / 'dist/Nawam.exe'
        original = exe.read_bytes()
        mutations = []
        with pefile.PE(data=original) as pe:
            mutations.extend([
                ('GUI', pe.OPTIONAL_HEADER.get_field_absolute_offset('Subsystem'), '<H', 3),
                ('DEP/ASLR', pe.OPTIONAL_HEADER.get_field_absolute_offset('DllCharacteristics'), '<H', 0),
                ('DependentLoadFlags', pe.DIRECTORY_ENTRY_LOAD_CONFIG.struct.get_field_absolute_offset('DependentLoadFlags'), '<H', 0),
                ('fixed', pe.VS_FIXEDFILEINFO[0].get_field_absolute_offset('ProductVersionLS'), '<I', 0),
            ])
        for message, offset, fmt, value in mutations:
            with self.subTest(message=message):
                data = bytearray(original)
                struct.pack_into(fmt, data, offset, value)
                exe.write_bytes(data)
                result = self.run_script('website/scripts/package_release.py')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
        for key, value in [('CompanyName', 'Shanna Studio'),
                           ('Comments', 'https://nawam.shanna.id'),
                           ('ProductVersion', self.version)]:
            with self.subTest(key=key):
                data = bytearray(original)
                with pefile.PE(data=original) as pe:
                    table = next(t for g in pe.FileInfo for i in g
                                 if hasattr(i, 'StringTable') for t in i.StringTable)
                    offset = table.entries_offsets[key.encode()][1]
                data[offset] = ord('X')
                exe.write_bytes(data)
                result = self.run_script('website/scripts/package_release.py')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(key, result.stderr)
        exe.write_bytes(original)
        resource = self.root / 'src/rufus.rc'
        resource.write_text(resource.read_text().replace(self.version, '9.8.7'), encoding='utf-8')
        result = self.run_script('website/scripts/package_release.py')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('version', result.stderr.lower())

    def test_optimized_packager_rejects_non_x64_pe(self):
        exe = self.root / 'dist/Nawam.exe'
        data = bytearray(exe.read_bytes())
        with pefile.PE(data=data) as pe:
            offset = pe.FILE_HEADER.get_field_absolute_offset('Machine')
        struct.pack_into('<H', data, offset, 0x14c)
        exe.write_bytes(data)
        result = self.run_script('website/scripts/package_release.py')
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('x64', result.stderr)
        self.assertFalse((self.root / 'website/public/release.json').exists())


if __name__ == '__main__':
    unittest.main()
