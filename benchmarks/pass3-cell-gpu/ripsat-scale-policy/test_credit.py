"""Credit arithmetic over a long prefix, independently of receiver depth support."""
import unittest
from pathlib import Path
from runpy import run_path

returns = run_path(str(Path(__file__).with_name("study.py")))["returns"]


class PrefixCredit(unittest.TestCase):
    def test_long_prefix_and_interleaved_stopped_root(self):
        path = list(range(64))
        trace = [(100,0,[],True),(101,0,[],False)]
        trace.extend((100,i,[],True) for i in range(1,len(path)))
        won = [(200+i,100,path[:i+1]) for i in path]
        sig = dict(signed_commits=won,receipt_scan=dict(row_reads=64),
                   set_publication=dict(admissions=1),
                   scale_policy=dict(trace=trace,admitted=[100],receiver_reads=[(100,i,1) for i in path]))
        data, value = returns(dict(strict_named=sig), [2]*64, 0)
        self.assertEqual(value, 64*3-1)
        self.assertEqual(data[0][-1], 3)
        self.assertEqual(data[-2][-1], 0)
        self.assertEqual(data[-1][-1], value)
        sig["signed_commits"] += [won[-1]]
        with self.assertRaises(AssertionError):
            returns(dict(strict_named=sig), [2]*64, 0)


if __name__ == "__main__":
    unittest.main()
