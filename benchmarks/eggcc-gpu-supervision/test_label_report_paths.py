import subprocess,sys,tempfile,unittest
from pathlib import Path

class LabelPaths(unittest.TestCase):
    def test_report_cannot_overwrite_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);output=p/'labels.npz';report=p/'labels.json'
            script=Path(__file__).with_name('label_composed_witnesses.py')
            result=subprocess.run([sys.executable,str(script),'missing-capture','missing-trace','missing-model','missing-corpus',str(output),str(report),'--snapshot-run','0'],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('label report must not overwrite training metadata',result.stderr)
            self.assertFalse(report.exists())

if __name__=='__main__':unittest.main()
