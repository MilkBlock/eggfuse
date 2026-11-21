"""Check whether old merge-function rows were in the original, paid pre-RHS root receipts."""
from pathlib import Path
from runpy import run_path
from collections import Counter
import argparse,json
HERE=Path(__file__).resolve().parent
filtered=run_path(str(HERE.parent/'filtered-explicit-parent/study.py'))
strict=filtered['strict'];src=strict.src

def run(a):
    a.out.mkdir(parents=True,exist_ok=True);res={}
    for case in ('sum-bits','3mm'):
        p,plans,req=src.config(a,case);cfg=filtered['filtered'](req,{'depth':0})
        with src.base.session(a.exp/'compact-vanilla-20261121/vanilla-audit',p) as run:gold=run({'audit':True})
        with src.base.session(a.native,p,plans) as run:v=run(dict(cfg,audit=True,birth_ledger=True))
        assert v['state_sha']==gold['state_sha'] and v['runs']==gold['runs']
        roots={r[0]:r for r in v['root_recipe']['commits']}
        program=json.loads(p.read_bytes())['recipe'];seen=Counter();by={};examples=[]
        assert len(roots)==gold['rhs_count']
        for child in v['merge_child']['issued']:
            ordinal=child['parent']['ordinal'];r=roots[ordinal];rid=r[3]
            old=child['old_reference'];version=child['old_epoch'];present=old is not None
            witnesses=r[6]
            exact=present and any(w['row']==old and w['version']==version for w in witnesses)
            function=program['tables'][child['function']]['name'];rule=program['rules'][rid]
            atom_ids=[i for i,q in enumerate(rule['query']) if q['call'].get('table')==function]
            selected=child['selected'];fresh=child['allocated'] is not None
            counts={'attempts':1,'old_exists':int(present),'selected':int(selected),'child_fresh':int(fresh),
                    'named_old':int(exact),'named_selected':int(exact and selected),'named_fresh':int(exact and fresh),
                    'old_table_in_lhs':int(bool(atom_ids)),'old_table_in_lhs_selected':int(bool(atom_ids) and selected)}
            seen.update(counts);by.setdefault(str(rid),Counter()).update(counts)
            if len(examples)<5 and selected:examples.append({'rule':rid,'old':old,'epoch':version,'root_refs':witnesses,'factory':child['candidate_site'],'effect':child['effect'],'function':function})
        res[case]={'counts':seen,'by_rule':by,'examples':examples,'state_sha':v['state_sha'],'runs':v['runs'],'rhs':len(roots)}
        (a.out/'opportunities.json').write_text(json.dumps(res,indent=1)+'\n')
        print(case,seen,flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ('exp','native','out'):p.add_argument(n,type=Path)
    a=p.parse_args();a.seed=1703;a.cap=8192;run(a)
