"""Run a compiled two-key, two-primitive writer across a later source union."""
import argparse,importlib.util,json,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('cpu_ref',HERE.parent/'compact-recipes/study.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)


def prepare(a,source,folder,training=None):
    folder.mkdir(parents=True,exist_ok=False)
    p=folder/'compiled/program.json';b=folder/'bundle'
    subprocess.run(['cargo','cell-compile','--source',source,'--output',p.parent,*(['--bake-source',training] if training else [])],check=True)
    subprocess.run([sys.executable,HERE.parent/'codec.py',p,folder/'image'],check=True)
    subprocess.run([sys.executable,HERE.parent/'joint-witness/prepare.py',p,folder/'image',b],check=True)
    req=base.read(b/'request.json');req.pop('merge_config')
    w=a.exp/'baked-port-packed-study-v1'
    (b/'root.json').write_text(json.dumps(dict(control='use',encoding='checked_slots',forbid_fallback=True)))
    req.update(single_config=str(b/'single.json'),root_config=str(b/'root.json'),radius=0,multi_mode='rowdeltapairguardstackseal2xlearned',
               baked_codes=str(w/'sum-bits-1703-tied.bin'),multi_weights=str(w/'sum-bits-1703-tied.json'),packed_lookup=True,
               multi_root_pages=True,rows=dict(action=4,max_rows=1,workers=1,batch=True,verify=2,prefilter=0),audit=True)
    return p,b,req


def run(a):
    p,b,req=prepare(a,HERE/'multi-key.egg',a.out)
    with base.session(a.exp/'compact-vanilla-20261121/vanilla-audit',p) as cpu: gold=cpu(dict(audit=True))
    result={}
    with base.session(a.native,p,b/'plans.json') as infer:
        for name,mode in [('off',0),('writer',3),('both',4),('reuse',5),('absorbed',6)]:
            out=infer(dict(req,**({'ordered_effect_blocks':mode} if mode else {})))
            assert 'source_error' not in out,out.get('source_error')
            assert all(out[k]==gold[k] for k in ('rhs','writes','resumes','state_sha','runs','schedule'))
            assert [[e for e in step if e[0]=='union'] for step in out['events']]==gold['unions'] and any(gold['unions'])
            row=dict(winner=out['single']['committed'],cells=out['cell_ids'],graph=out['state_sha'],source=gold['rhs'],writes=gold['writes'],
                     unions=gold['unions'],work=out['ordered_effect_blocks']['writer'])
            if name!='off':
                assert all(row[k]==result['off'][k] for k in row if k!='work')
                s=row['work'];assert s['audited']==s['calls']==s['multi_key']>0 and s['prefix_ops']==s['calls']*2
                assert s['changed']>0 and s['unchanged']>0
                if name in ('reuse','absorbed'):assert s['reused_key']>0
                if name=='absorbed':assert s['proved_absorbed']>0
            result[name]=row
    (a.out/'fixture.json').write_text(json.dumps(result,separators=(',',':'))+'\n')
    print(result['reuse']['work'],flush=True)


def overflow(a):
    # Preserve preceding writes when a later winning row's first primitive overflows.
    bad_source=a.out/'overflow.egg'
    txt=(HERE/'multi-key.egg').read_text()
    marker='(run scoring 1)'
    txt=txt.replace(marker,'(Value (Id 9) 4 9223372036854775807)\n'+marker,1)
    bad_source.write_text(txt)
    p,b,req=prepare(a,bad_source,a.out/'overflow-heldout',a.out/'compiled/source_sk.egg');negative={}
    with base.session(a.native,p,b/'plans.json') as infer:
        for name,mode in [('off',0),('writer',3),('both',4),('absorbed',6)]:
            out=infer(dict(req,**({'ordered_effect_blocks':mode} if mode else {})))
            assert out.get('source_error')=='RHS primitive failed: +',out.get('source_error')
            row={k:out[k] for k in ('source_error','runs','partial_rhs','rhs')}
            assert row['partial_rhs']>0
            if name!='off':assert row==negative['off']
            negative[name]=row
    (a.out/'overflow.json').write_text(json.dumps(negative,separators=(',',':'))+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--overflow-only',action='store_true')
    a=p.parse_args()
    if a.overflow_only:overflow(a)
    else:run(a)
