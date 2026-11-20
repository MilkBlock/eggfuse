"""Fresh-process resident memory and request-to-exit wall time for transaction variants on Darwin."""
import argparse
import json
from pathlib import Path
import re
from statistics import median
import subprocess
import sys
from time import perf_counter_ns

from measure import ARMS, make_request, read


def sample(command, request):
    start = perf_counter_ns()
    proc = subprocess.run(['/usr/bin/time', '-l', *command], input=json.dumps(request)+'\n',
                          text=True, capture_output=True, check=True)
    wall = (perf_counter_ns()-start)/1e6
    rss = re.search(r'^\s*(\d+)\s+maximum resident set size\s*$',proc.stderr,re.MULTILINE)
    if not rss:
        raise ValueError(proc.stderr[-1200:])
    return json.loads(proc.stdout), int(rss.group(1)), wall


def study(case, args):
    req, program, bundle = make_request(case, 1703, args)
    gold = read(args.evidence)[case+'/1703']
    result = {k: {'rss_bytes': [], 'wall_ms': []} for k in ('vanilla','immediate','stream-8','parents-8','parents-32')}
    order = list(result)
    for i in range(3):
        seq = order[i:]+order[:i]
        for name in seq if i%2==0 else reversed(seq):
            if name == 'vanilla':
                out, rss, wall = sample([args.vanilla/'vanilla', program], {})
            else:
                out, rss, wall = sample([args.native, program, bundle/'plans.json'], dict(req,**ARMS[name],audit=False))
                assert out['multi']['transactions'] == gold[name]['requests']
            assert out['state_sha'] == gold['immediate']['state_sha'] and out['runs'] == gold['vanilla']['runs']
            result[name]['rss_bytes'].append(rss)
            result[name]['wall_ms'].append(wall)
    for vals in result.values():
        vals['median_rss_bytes'] = median(vals['rss_bytes'])
        vals['median_wall_ms'] = median(vals['wall_ms'])
    return result


if __name__ == '__main__':
    if sys.platform != 'darwin':
        raise SystemExit('measurement requires the Darwin peak-RSS units from /usr/bin/time -l')
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('native','vanilla','bundles','tables','evidence','out'):p.add_argument(key,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','jacobi-1d'])
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    report={}
    for case in a.cases:
        report[case]=study(case,a)
        (a.out/'footprint.json').write_text(json.dumps(report,indent=1)+'\n')
