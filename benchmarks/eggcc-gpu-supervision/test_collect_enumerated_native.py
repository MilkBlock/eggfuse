import hashlib,tarfile,tempfile,unittest,subprocess,sys
from pathlib import Path
from collect_enumerated_native import archive_case,execute

class Archive(unittest.TestCase):
    def test_timeout_is_explicit_and_process_is_reaped(self):
        with tempfile.TemporaryDirectory() as d:
            with (Path(d)/'log').open('w') as log:
                with self.assertRaises(subprocess.TimeoutExpired):
                    execute([sys.executable,'-c','import time; time.sleep(10)'],log,.05)

    def test_archive_preserves_exact_case_files(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);case=root/'working';case.mkdir();(case/'compiled').mkdir()
            (case/'input.egg').write_text('(sort E)\n');(case/'compiled'/'program.json').write_bytes(b'{}')
            target=root/'case.tar.gz';digest=archive_case(case,target)
            self.assertEqual(digest,hashlib.sha256(target.read_bytes()).hexdigest())
            with tarfile.open(target) as t:
                self.assertEqual(t.extractfile('case/input.egg').read(),b'(sort E)\n')
                self.assertEqual(t.extractfile('case/compiled/program.json').read(),b'{}')

if __name__=='__main__':unittest.main()
