"""Learn request scheduling only from four training programs, then execute the frozen library."""
import argparse
from collections import defaultdict
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
from statistics import median
import subprocess
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'request-transactions'))
from measure import ARMS, compare, read, session

TRAIN=('affine-twins','clamped-ramp','segmented-prefix','window-laplacian')
EVAL=('sum-bits','dot-product','jacobi-1d','conjugate-gradient')
MODES=('immediate','stream-8','parents-8')


def outputs(path,data):
    path.write_text(json.dumps(data,indent=1)+'\n')


def eligible(rule,plan):
    if plan is None:return False
    suffix=[rule['query'][i]['call'] for i,pick,_ in plan['ins'] if not pick]
    def safe(c):
        return ('table' in c or (c.get('output')=='i64' and c.get('primitive') in ('+','-','*','min','max'))
                or (c.get('output')=='Unit' and c.get('primitive') in ('<','>','<=','>=','=','!=','value-eq')))
    return bool(suffix) and all(safe(c) for c in suffix)


def fingerprint(rule,plan):
    if not eligible(rule,plan):return None
    # Query/effects use logical relation names and typed slots. The independent parent
    # order and typed suffix of the deployed compiler must match the training template.
    key=[rule['query'],rule['effects'],rule['metadata']['seminaive'],plan['ins']]
    return hashlib.sha256(json.dumps(key,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def request(a,case,training):
    if training:
        src=a.train_root/case
        b=a.out/(case+'-bundle')
        subprocess.run([sys.executable,HERE.parent/'joint-witness/prepare.py',src/'program.json',src/'input',b,
                        '--policy','certified','--seed',str(a.seed)],check=True)
    else:
        b=a.bundles/f'{case}-{a.seed}'
    p=b/'program.json'
    req=read(b/'request.json')
    assert hashlib.sha256(p.read_bytes()).hexdigest()==req['source_sha256']
    for field in ('single_config','merge_config'):req[field]=str(b/req[field])
    cfg=a.out/(case+'-root.json');outputs(cfg,dict(read(b/'root.json'),encoding='checked_slots',forbid_fallback=True))
    header=a.tables/f'sum-bits-{a.seed}-tied'
    req.update(root_config=str(cfg),multi_weights=str(header.with_suffix('.json')),baked_codes=str(header.with_suffix('.bin')),
               radius=0,baked_row_index=False,packed_lookup=True,multi_mode='rowdeltapairguardstackseallearned',
               rows=dict(action=4,max_rows=1,workers=1,batch=True,verify=2))
    assert not req['multi_residual'] and not read(Path(req['single_config']))['residual']
    rules=read(p)['recipe']['rules']
    signatures=[fingerprint(r,plan) for r,plan in zip(rules,read(b/'plans.json'),strict=True)]
    return b,p,req,signatures


def train(a):
    evidence=defaultdict(list)
    for case in TRAIN:
        b,p,req,signatures=request(a,case,True)
        timed={k:defaultdict(list) for k in MODES};state=None
        with session(a.native,p,b/'plans.json') as infer:
            for lap in range(8):
                start=lap%3;order=MODES[start:]+MODES[:start]
                for arm in order if lap%2==0 else reversed(order):
                    result=infer(dict(req,**ARMS[arm],audit=False,multi_mode='profile'+req['multi_mode']))
                    if state is None:state=result['state_sha']
                    assert result['state_sha']==state and result['multi']['transactions']['eligible_rules']==sum(k is not None for k in signatures)
                    if lap:
                        for rid,profile in enumerate(result['multi']['rule_profile']):
                            if signatures[rid] and profile['raw']>0:
                                timed[arm][rid].append(profile['validation_ms'])
        for rid,samples in timed['immediate'].items():
            ms=[median(timed[arm][rid]) for arm in MODES]
            evidence[signatures[rid]].append(dict(case=case,rule=rid,ms=ms))
    # A reusable schedule must replicate in different programs. Thresholds fixed before
    # reading any holdout measurements. Each training family receives one vote per mode.
    library={}
    for sig,rows in evidence.items():
        choice=[]
        for aidx in (1,2):
            gains=defaultdict(list)
            for v in rows:
                base,amt=v['ms'][0],v['ms'][aidx]
                if base>=0.02:gains[v['case']].append((base-amt)/base)
            g=[median(vals) for vals in gains.values()]
            if len(g)>=3 and sum(x>0.03 for x in g)>=3 and median(g)>0.08:
                choice.append((median(g),aidx))
        if choice:library[sig]=max(choice)[1]
    out={'training_programs':TRAIN,'seed':a.seed,'library':library,'measurements':evidence}
    outputs(a.out/'training.json',out);print('selected',len(library),'of',len(evidence),'seen templates',flush=True)
    return library


def evaluate(a,library):
    report={}
    for case in a.cases:
        b,p,req,signatures=request(a,case,False)
        actions=[library.get(sig,0) for sig in signatures]
        controls={k:ARMS[k] for k in MODES}
        controls['baked']=dict(ARMS['parents-8'],request_policy=dict(program_sha256=req['source_sha256'],actions=actions))
        with session(a.vanilla/'vanilla-audit',p) as audit:gold=audit(dict(audit=True))
        result={'vanilla':{'ms':[]}}
        with ExitStack() as stack:
            native=stack.enter_context(session(a.native,p,b/'plans.json'))
            vanilla=stack.enter_context(session(a.vanilla/'vanilla',p))
            for name,ctl in controls.items():
                v=native(dict(req,**ctl,audit=True));row=compare(v,gold)
                assert row['aligned'] and row['neural_rhs']==row['rhs']==gold['rhs_count'] and 100*row['direct_cells']>=98*row['fresh']
                row.update(request_digest=v['multi']['request_digest'],requests=v['multi']['transactions'],ms=[])
                if name!='immediate':
                    for field in ('raw','commits','multi','physical','children','cells','request_digest'):
                        assert row[field]==result['immediate'][field],(case,name,field)
                result[name]=row
            order=list(result)
            for lap in range(1+a.repeats):
                k=lap%len(order);seq=order[k:]+order[:k]
                for arm in seq if lap%2==0 else reversed(seq):
                    v=vanilla({}) if arm=='vanilla' else native(dict(req,**controls[arm],audit=False))
                    assert v['state_sha']==gold['state_sha'] and v['runs']==gold['runs']
                    if arm!='vanilla':assert v['root_recipe']['allocated']==result[arm]['root_allocated']
                    if lap:result[arm]['ms'].append(v['ms'])
        for arm in result:result[arm]['median_ms']=median(result[arm]['ms'])
        negative={}
        if case == 'sum-bits':
            for fault in ('source','width','unproved'):
                policy=dict(program_sha256=req['source_sha256'],actions=actions.copy())
                if fault=='source':policy['program_sha256']='0'*64
                elif fault=='width':policy['actions']=actions[:-1]
                else:policy['actions'][signatures.index(None)]=2
                invalid=dict(req,**ARMS['parents-8'],request_policy=policy)
                proc=subprocess.run([a.native,p,b/'plans.json'],input=json.dumps(invalid)+'\n',text=True,capture_output=True)
                expected={'source':'source mismatch','width':'scheduling contract','unproved':'unproved request'}[fault]
                assert proc.returncode and expected in proc.stderr and not proc.stdout.strip(), (fault,proc.stderr)
                negative[fault]=True
        report[case]=dict(actions=actions,arms=result,negative=negative)
        outputs(a.out/'heldout.json',report)
        print(case, {k:round(v['median_ms'],2) for k,v in result.items()},flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for k in ('native','vanilla','bundles','tables','train_root','out'):parser.add_argument(k,type=Path)
    parser.add_argument('--seed',type=int,default=1703);parser.add_argument('--repeats',type=int,default=6)
    parser.add_argument('--cases',nargs='+',choices=EVAL,default=EVAL);a=parser.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    evaluate(a,train(a))
