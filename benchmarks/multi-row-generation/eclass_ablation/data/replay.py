"""Read actual saved output tensors, verify their ancestry and score paired interventions."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
import numpy as np
from runtime import CORPUS
from source import STATES, dataset
from check import audit
from paired import paired_controls


def verify_tokens(d,first,second,tok):
    if not np.isfinite(tok).all():raise ValueError('nonfinite retained producer token')
    g=np.arange(len(tok))[:,None];li,ri=first['pointers'].transpose(2,0,1)
    for offset,width,values in [(32,2,first['active']),(34,8,li),(42,8,ri)]:
        np.testing.assert_array_equal(tok[...,offset:offset+width],np.eye(width)[values])
    expected1=np.concatenate((d['a'][g,li],d['b'][g,ri,1,None]),-1)
    np.testing.assert_array_equal(first['rows'],expected1)
    np.testing.assert_array_equal(tok[...,50:55],expected1)
    np.testing.assert_array_equal(tok[...,-1],d['a_port'][g,li])
    pi,qi=second['pointers'].transpose(2,0,1);selected=tok[g,pi,50:55]
    expected2=np.concatenate((selected[...,:2],d['requests'][g,qi,4,None],selected[...,3:]),-1)
    np.testing.assert_array_equal(second['rows'],expected2)
    grouped=tok.reshape((-1,8,*tok.shape[1:]));np.testing.assert_array_equal(grouped,np.broadcast_to(grouped[:,:1],grouped.shape))


def check_groups(d,actual,pred,stored):
    rows=actual['run2']['per_graph'];truth=np.asarray(actual['request_legal'],dtype=bool)
    assert stored['complete']==[int(r['complete']) for r in rows]
    assert stored['first_complete']==actual['run1']['complete_graphs']
    assert (truth==d['request_legal']).all()
    mask={'all':np.ones(len(rows),bool),'blind':d['blind'].astype(bool),'targeted':d['blind']==0}
    for index,state in enumerate(STATES):
        mask[state]=d['state']==index;mask['blind_'+state]=mask[state]&mask['blind']
    assert set(mask)==set(stored['groups'])
    for group,chosen in mask.items():
        records=[r for r,ok in zip(rows,chosen) if ok];report=stored['groups'][group]
        assert len(records)==report['graphs']
        assert sum(r['complete'] and r['nonempty'] for r in records)==report['nonempty_complete']
        assert sum(r['complete'] and r['nonempty'] and r['parent_ready'] for r in records)==report['complete_when_ready']
        for k in records[0]:
            if sum(int(r[k]) for r in records)!=report[k]:raise ValueError(f'{group}/{k} differs')
        for desc,bits in [('all',np.ones_like(truth,bool)),
                          ('different_origins',(d['requests'][...,:2]!=d['requests'][...,2:4]).any(-1)),
                          ('cross_owner',d['requests'][...,0]!=d['requests'][...,2]),('local_probe',d['probe_kind']==1)]:
            check=report['relation_'+desc];keep=chosen[:,None]&bits
            assert int(keep.sum())==check['tests'] and int((keep&(pred==truth)).sum())==check['correct']
            assert int((keep&truth).sum())==check['positive']
            assert int((keep&~pred&truth).sum())==check['false_negative']
            assert int((keep&pred&~truth).sum())==check['false_positive']


def main():
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);args=parser.parse_args()
    out=args.root/'paired-controls.json';result_path=args.root/'results.json';reports=json.loads(result_path.read_text());manifest=json.loads((CORPUS/'manifest.json').read_text());panels={};aggregate={};traces={};support={}
    for t in manifest['templates']:
        if t['split']!='heldout':continue
        tid=t['id'];d=dataset('test',t);panels[tid]={};support[tid]={}
        non_reflexive=(d['requests'][...,:2]!=d['requests'][...,2:4]).any(-1)
        needs_proof=(d['request_legal'].astype(bool)&non_reflexive).any(1)
        for state_index,state in enumerate(STATES):
            for group,select in [('all',d['state']==state_index),('blind',(d['state']==state_index)&(d['blind']==1))]:
                support[tid][f'{group}/{state}']=dict(graphs=int(select.sum()),
                    requires_nonreflexive_semantic_read=int((select&needs_proof).sum()),
                    all_legal_requests_are_self_reads=int((select&~needs_proof).sum()))
        for name,recorded in reports['reports'][tid].items():
            path=args.root/'traces'/f'{tid}-{name}.npz'
            with np.load(path,allow_pickle=False) as z:
                stages=[{k:z[f'{i}_{k}'] for k in ('active','pointers','rows')} for i in range(2)]
                tok=z['token'];rel=z['rel'];assert np.isfinite(rel).all();pred=rel.argmax(-1).astype(bool)
                verify_tokens(d,*stages,tok);actual=audit(d,*stages);check_groups(d,actual,pred,recorded)
                controls=paired_controls(d,*stages,pred);panels[tid][name]=controls
                assert controls['all']['pre_to_post']['probes']==recorded['switches']['changed']
                assert controls['all']['pre_to_post']['both_semantic_correct']==recorded['switches']['both_correct']
                for group,items in controls.items():
                    arm=aggregate.setdefault(name,{}).setdefault(group,{})
                    for intervention,counts in items.items():
                        row=arm.setdefault(intervention,{})
                        for key,val in counts.items():row[key]=row.get(key,0)+val
            traces[path.name]=sha256(path.read_bytes()).hexdigest()
    if 'torch' in sys.modules or 'mlx.core' in sys.modules:raise RuntimeError('CPU audit imported device model')
    if len(traces)!=24:raise ValueError(f'expected 3 held-out templates x 4 arms x 2 seeds, got {len(traces)}')
    r=dict(scope='CPU replay of saved two-Run outputs and signed pre/post/receipt/external interventions; no model execution',
           test_graphs_per_model=sum(len(dataset('test',t)['a']) for t in manifest['templates'] if t['split']=='heldout'),
           verified_traces=len(traces),data_manifest_sha256=sha256((Path(__file__).parent/'manifest.json').read_bytes()).hexdigest(),
           results_sha256=sha256(result_path.read_bytes()).hexdigest(),trace_hashes=traces,source_support=support,controls=panels,aggregate=aggregate)
    tmp=out.with_suffix('.tmp');tmp.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');tmp.replace(out)
    print('verified',len(traces),'traces; all saved per-graph and group decisions agree')
    for name,group in aggregate.items():
        print(name,'blind changed legal pairs', {k:(v['both_semantic_correct'],v['probes']) for k,v in group['blind'].items() if 'to_' in k})

if __name__=='__main__':main()
