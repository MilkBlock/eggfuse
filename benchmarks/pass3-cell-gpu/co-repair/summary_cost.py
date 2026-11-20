"""Census additional summary accesses without putting counters into timing measurements."""
import argparse
from pathlib import Path
from collect import read
from device import execute_case
from experiment import write

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('corpus','ref','weights','catalog','paired','out'):p.add_argument(k,type=Path)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    f=read(a.catalog);library=f['catalogs'][f['chosen']];report={}
    for case,modes in read(a.paired).items():
        report[case]={}
        for label,mode in [('row-sparse',4),('mask-sparse',3)]:
            actual=execute_case(a.corpus,a.ref,a.weights,case,a.out/f'{case}-{label}',library,mode,3,sparse_words=True)
            stats=actual['co_repair']
            assert (actual['state'][74],stats['counters'][2])==(modes[label]['notification_word_tests'],modes[label]['notifications'])
            report[case][label]=dict(summary_reads=stats['counters'][14],summary_updates=stats['counters'][15],
                                    summary_bytes=stats['extra_summary_bytes'])
        write(a.out/'results.json',report)
