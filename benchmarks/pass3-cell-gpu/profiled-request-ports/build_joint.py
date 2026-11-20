"""Train and apply a fresh native profile with the actual incremental provider enabled."""
import argparse,importlib.util,json
from pathlib import Path
from joint_common import HERE,DONORS,file_digest,routes
spec=importlib.util.spec_from_file_location('pgo_builder',HERE.parent/'native-backend-pgo/build.py')
native=importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


def build(a):
    a.out.mkdir(parents=True,exist_ok=False)
    a.profdata=native.capture(['xcrun','--find','llvm-profdata'])
    orig=json.loads((a.reference/'build.json').read_bytes())
    src=a.exp/'incremental-request-ports-v1'
    extensions=json.loads((src/'build.json').read_bytes())['extensions']
    assert {'changed-request-roots','incremental-request-ports','connected-request-plans'}<=set(extensions)
    entry=(src/'tree',['-p','eggfuse-cell-runtime','--features','precomputed-forest,slot-transfer-audit','--example','joint_witness_session'],'examples/joint_witness_session')
    data={}
    for n in DONORS:
        p,plan,_,active=routes(a,n)
        data[n]=p,plan,active
    evidence=dict(base=native.BASE_REV,learned_recipe_sha256=file_digest(src/'build.json'),
                  original_release_sha256=file_digest(src/'session'),binaries={},donors={})
    evidence['source_donors']={k:{'program_sha256':file_digest(p),'plan_sha256':file_digest(plans)} for k,(p,plans,_) in data.items()}
    original_donors=json.loads((HERE.parent/'native-backend-pgo/build-evidence.json').read_bytes())['source_donors']
    assert evidence['source_donors']==original_donors
    for mode in ('plain','generate','use'):
        if mode=='use':
            cohort=native.train(a,'learned',data)
            assert cohort['profile_sha256']!=orig['donors']['learned']['profile_sha256']
            assert set(cohort['programs'])==set(DONORS)
            for name,row in cohort['programs'].items():
                assert row['union_aware']['union_repairs']>0 and row['union_aware']['transferred']>0
                ref=orig['donors']['learned']['programs'][name]
                for field in ('runs','rhs','state','repetitions'):assert row[field]==ref[field]
            evidence['donors']['learned']=cohort
        info=native.compile_one(a,'learned',mode,entry)
        if mode=='use':
            assert any(info['ir']['accounts'].get(k,{}).get('max_entry_count',0)>0 for k in ('activation','subscriptions','connected'))
        evidence['binaries'][mode]=info
        (a.out/'joint-build.json').write_text(json.dumps(evidence,indent=1)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','reference','out'):p.add_argument(k,type=Path)
    a=p.parse_args();a.seed=1703;build(a)
