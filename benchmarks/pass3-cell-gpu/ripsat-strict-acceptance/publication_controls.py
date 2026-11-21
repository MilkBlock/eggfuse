"""Independent Set-ABI target and identity checks on actual native sessions; no timing runs."""
from pathlib import Path
from runpy import run_path
import argparse,copy,hashlib,json,subprocess
HERE=Path(__file__).resolve().parent
core=run_path(str(HERE/'chain_audit.py'))

def run(a):
    program,plans,req=core['src'].config(a,'dot-product')
    actual=hashlib.sha256(program.read_bytes()).hexdigest()
    data=json.loads(a.authorization.read_bytes())
    spec=dict(data['strict_named'],record_links=True)
    assert data['target_sha256']==spec['set_publication']['target_sha256']==actual
    b=core['bench']['bake'].settings(req,spec)
    b=dict(b,source_sha256=actual,rows=dict(b['rows'],scalar_certificates=True),audit=True,
           integral_root='off',integral_packets=False,birth_ledger=True)
    def execute(config):
        p=subprocess.run([a.native,program,plans],input=json.dumps(config)+'\n',text=True,capture_output=True)
        if p.returncode!=0:
            msg=p.stderr.strip().splitlines()[-1] if p.stderr.strip() else ''
            return None,msg
        v=json.loads(p.stdout)
        return (None,v['source_error']) if 'source_error' in v else (v,None)
    def trace(config,label):
        v,e=execute(config);assert v is not None,(label,e)
        s=v['strict_named'];sets=s['set_publication'];comm=s['set_commits']
        assert sets['confirmed']==len(comm)
        return {'state_sha':v['state_sha'],'runs':v['runs'],'source_rhs':core['sha'](v['rhs']),'writes':core['sha'](v['writes']),
                'resumes':core['sha'](v['resumes']), 'commits':comm,'set_counts':sets,'packets':sum(v['root_recipe']['emitted']),
                'paid_children':v['merge_child']['counts'][1]}
    saved=trace(b,'valid');assert saved['set_counts']['confirmed']>0
    companion=json.loads((HERE/"dot-product-same-middle.json").read_bytes())
    paid,=companion["companions"];wire,=[t for t in saved["commits"] if t["consumer"]==paid["consumer"]["serial"]]
    assert wire["middle"]==paid["producer"]["serial"] and wire["root"]==companion["first_origin_sample"]["producer"]["serial"]
    assert wire["fact"]==[paid["original_fact"]>>32,paid["producer_op"]] and wire["version"]==paid["original_version"]
    report={'nominated':wire,'binding': 'authorizer-output','source_sha':actual,
            'valid':{k:v for k,v in saved.items() if k!='commits'},'faults':{}}
    for name in ('wrong_kind','wrong_pivot','wrong_set_operation','one_wrong_target','both_wrong_target','wrong_fields','missing','stale'):
        cfg=copy.deepcopy(b);plan=cfg['strict_named']['set_publication']
        if name=='wrong_kind':plan['kinds'][1]='fresh_constructor_let'
        elif name=='wrong_pivot':plan['pivot']=1
        elif name=='wrong_set_operation':plan['path'][1][1]=0
        elif name in ('one_wrong_target','both_wrong_target'):
            plan['target_sha256']='0'*64
            if name=='both_wrong_target':cfg['source_sha256']='0'*64
        else:cfg['strict_named']['set_fault']=name
        if name in ('missing','stale'):
            r=trace(cfg,name)
            assert all(r[k]==saved[k] for k in ('state_sha','runs','source_rhs','writes','resumes','paid_children'))
            assert r['set_counts']['confirmed']==0 and r['packets']-saved['packets']==saved['set_counts']['confirmed']
            report['faults'][name]={'fell_back_to_paid':r['packets']-saved['packets'],'internal':0}
        else:
            v,msg=execute(cfg)
            report['faults'][name]={'rejected':v is None,'reason':msg,'internal_if_accepted':(v['strict_named']['set_publication']['confirmed'] if v else 0)}
    a.report.write_text(json.dumps(report,indent=2)+'\n')
    leaked=[n for n,q in report['faults'].items() if q.get('rejected') is False]
    if leaked:raise SystemExit('Accepted a malformed receipt: '+str(leaked))
    print('Set-ABI native counterexamples rejected; stale and withheld receipts returned to paid source proposals.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--authorization',type=Path,required=True)
    for n in ('exp','native','out'):p.add_argument(n,type=Path)
    a=p.parse_args();a.seed=1703;a.cap=8192
    # The standard source helper places a tiny request file in its output directory.
    a.report=a.out;a.out=a.report.parent
    a.out.mkdir(parents=True,exist_ok=True)
    run(a)
