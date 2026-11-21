"""Compare one-key and compiler-certified two-key family packets inside the same native executor."""
import argparse,json,struct
from pathlib import Path
from runpy import run_path
from statistics import median
HERE=Path(__file__).resolve().parent
family=run_path(str(HERE.parent/'generative-pair-families/study.py'));wave=family['wave'];source=family['source']
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['3mm']);p.add_argument('--smoke',action='store_true')
    a=p.parse_args();a.seed=1703;a.cap=8192;a.out.mkdir(parents=True,exist_ok=False)
    a.policy=json.loads((HERE.parent/'speculative-allocation-policy/policy.json').read_bytes());a.fraction=json.loads((HERE.parent/'wave-demand-policy/policy.json').read_bytes())['models']['fraction']
    data={}
    for case in a.cases:
        prog,plan,req=source.common.config(a,case);cfg=wave['settings'](req,a)['packed']
        with source.base.session(a.exp/'compact-vanilla-20261121/vanilla-audit',prog) as ref:gold=ref({'audit':True})
        rows={}
        with source.base.session(a.native,prog,plan) as run:
            arms={'ordinary':dict(mode=0),'wide':dict(mode=2),'compound':dict(mode=2,compound=True)}
            for name,options in arms.items():
                v=run(dict(cfg,audit=True,birth_ledger=True,pair_family=dict(options,trace=True)))
                q=family['observe'](v,gold);q['scalar']=v['multi']['compound_work'];q['examples']=[]
                for bs in v['multi']['family_examples']:
                    b=bytes(bs);head=list(struct.unpack('<9Q',b[:72]));compound=head[-1]>>63;head[-1]&=(1<<63)-1
                    width,fmt=(8,'Q') if compound else (4,'I');keys=struct.unpack('<'+fmt*((len(b)-72)//width),b[72:])
                    q['examples'].append(dict(header=head,compound=bool(compound),keys=keys))
                rows[name]=q
                for k in (*family['KEYS'],'visible','births','birth_digest','visible_digest','expanded','raw_issue_sha','child_selected','child_decisions','checked_parents'):
                    assert q[k]==rows['ordinary'][k],(name,k)
                if name=='compound':
                    assert q['scalar']['admitted']>0 and q['stats']['receiver_pairs']<rows['wide']['stats']['receiver_pairs']
                    assert q['stats']['private_rows']==rows['wide']['stats']['private_rows']
                print(case,name,q['scalar'],q['stats']['actions'],q['stats']['receiver_pairs'],q['fept'],flush=True);del v
            bad=run(dict(cfg,pair_family=dict(mode=2,compound=True,bad_scalar=True)))
            assert 'family' in str(bad.get('source_error','')),(case,bad.keys());rows['fault']=bad['source_error']
            if not a.smoke:
                for i in range(5):
                    seq=list(arms);seq=seq[i%3:]+seq[:i%3]
                    for name in seq if i%2 else reversed(seq):
                        v=run(dict(cfg,pair_family=arms[name]));assert v['runs']==gold['runs'] and v['state_sha']==gold['state_sha']
                        if i:rows[name].setdefault('ms',[]).append(v['ms'])
                for name,opt in arms.items():
                    rows[name]['median_ms']=median(rows[name]['ms'])
                    q=run(dict(cfg,pair_family=dict(opt,phase=True)))
                    rows[name]['phase']={k:q['multi']['family_work'][k] for k in ('source_pair_ms','issue_ms','receiver_ms')}
        data[case]=rows;(a.out/'results.json').write_text(json.dumps(data,indent=1)+'\n')
if __name__=='__main__':main()
