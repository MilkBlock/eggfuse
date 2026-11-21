"""Measure real native allocations released by the exact reverse fields after graph export."""
import argparse,json,re,subprocess
from pathlib import Path
from runpy import run_path
HERE=Path(__file__).resolve().parent
study=run_path(str(HERE/'study.py'));source=study['base'];settings=study['settings']


def measure(a):
    a.out.mkdir(parents=True,exist_ok=False);report={}
    data=json.loads(a.evidence.read_bytes())
    for name,arms in data.items():
        p,plan,req=source.common.config(a,name);a.arms=[n for n in arms if n not in ('off','vanilla')]
        cfg=settings(req,a);report[name]={}
        for arm,r in cfg.items():
            proc=subprocess.run(['/usr/bin/time','-l',a.heap,p,plan],input=json.dumps(dict(r,release_directory=True))+'\n',
                                capture_output=True,text=True,check=True)
            v=json.loads(proc.stdout);g=arms[arm];t=v['owner_directory']
            assert v['state_sha']==g['state_sha'] and v['multi']['total_rhs']==g['rhs'] and v['root_recipe']['allocated']==g['root_allocated']
            assert t['mode']==g['directory']['mode'] and t['logical_edges']==g['directory']['logical_edges'] and t['work']['domain_audits']==0
            for field in ('tree_edges','tree_headers','implicit_self','inline_single','forward_derived','pages'):
                assert t[field]==g['directory'][field]
            parts=v['reverse_drop_bytes'];remaining=v['graph_remainder_drop_bytes']
            rss=int(re.search(r'^\s*(\d+)\s+maximum resident set size',proc.stderr,re.M)[1])
            assert len(parts)==3 and min(parts)>=0 and remaining>0
            report[name][arm]=dict(tree=parts[0],masks=parts[1],inline=parts[2],total=sum(parts),remainder=remaining,
                                   graph=sum(parts)+remaining,peak_rss=rss,state=v['state_sha'],root_allocated=v['root_recipe']['allocated'])
        (a.out/'heap.json').write_text(json.dumps(report,indent=1)+'\n')
        print(name,[(k,v['total'],v['graph']) for k,v in report[name].items()],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','heap','evidence','out'):p.add_argument(k,type=Path)
    a=p.parse_args();a.seed=1703;measure(a)
