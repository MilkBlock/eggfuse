"""Post-hoc failure decomposition. No training, model execution, or output repair."""
import argparse,json
from pathlib import Path
import numpy as np
from spec import *
from semantics import cpu_unrotate,decode,targets,checker_eq


def support(train_truth,test_truth):
    result={};any_missing=np.zeros(test_truth['owner'].shape[1],bool)
    for k in SPECS:
        tr=train_truth[k].transpose((1,0)+tuple(range(2,train_truth[k].ndim))).reshape(train_truth[k].shape[1],-1)
        te=test_truth[k].transpose((1,0)+tuple(range(2,test_truth[k].ndim))).reshape(test_truth[k].shape[1],-1)
        missing=np.zeros(len(te),bool);atoms=[]
        for j in range(tr.shape[1]):
            absent=~np.isin(te[:,j],np.unique(tr[:,j]));missing|=absent
            if absent.any():atoms.append(dict(flat_field_position=j,unseen_values=np.unique(te[absent,j]).tolist(),cases=int(absent.sum())))
        result[k]=dict(cases_with_unseen_output_atom=int(missing.sum()),atoms=atoms)
        any_missing|=missing
    return result,any_missing


def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    seeds=[1703,1709,1721]
    with np.load(a.root/'seed-1703/inputs.npz') as data:
        train=data['train'];tt=targets(train);tests={g:data[g] for g in GROUPS}
    coverage={}
    for g,cases in tests.items():
        fields,missing=support(tt,targets(cases))
        coverage[g]=dict(cases=len(cases),all_output_atoms_seen=int((~missing).sum()),fields=fields)
    trainplans={tuple(np.array(SHAPES[i]).flatten()) for i in TRAIN_SHAPES}
    aliases={tuple(layout_for(MAPS[i]).index(r) for r in range(8)) for i in TRAIN_MAPS}
    all_runs={}
    for seed in seeds:
        base=a.root/f'seed-{seed}';saved=json.loads((base/'result.json').read_text());groups={}
        for g in GROUPS:
            with np.load(base/f'{g}-checkpoints.npz') as z:
                c=z['cases'];h=decode(cpu_unrotate(z['tokens'],z['locations'])@z['decoder_weight'].astype(np.float64).T+z['decoder_bias'].astype(np.float64))
            n=len(c);inputplan=np.array(SHAPES)[c[:,0]]
            produced=np.concatenate((h['ops'][0,:,:,None],h['args'][0]),axis=-1)
            sameplan=np.all(produced==inputplan,axis=(1,2))
            knownplan=np.array([tuple(x.flatten()) in trainplans for x in produced])
            on=c[:,3].astype(bool)
            closures=np.array([checker_eq(row,2) for row in c])
            wanted_eq=np.array([[eq[u,v] for u,v in PAIRS] for eq in closures])
            eq_ok=np.all(h['eq'][1]==wanted_eq,axis=-1)
            wanted_transfer=closures[np.arange(n),c[:,4],c[:,5]]
            requested=np.array(MAPS)[c[:,2]]
            commands_ok=np.all(h['commands'][2]==requested,axis=-1)
            expected_alias=np.array([[layout_for(MAPS[row[2]]).index(r) for r in range(8)] if wanted_transfer[i] else list(range(8)) for i,row in enumerate(c)])
            alias_ok=np.all(h['alias'][2]==expected_alias,axis=-1)
            alias_seen=np.array([tuple(x) in aliases for x in h['alias'][2]])
            pair_ok=np.all(h['union_witness'][1]==np.array(UNIONS)[c[:,1]],axis=-1)
            case_examples=[]
            bad=np.flatnonzero(~sameplan) if g in ('shape','joint') else np.flatnonzero(on&~eq_ok) if g=='union' else np.flatnonzero(wanted_transfer&~alias_ok)
            for i in bad[:2]:
                case_examples.append(dict(case=c[i].tolist(),input_shape=inputplan[i].tolist(),decoded_shape=produced[i].tolist(),
                    requested_union=UNIONS[c[i,1]],decoded_union=h['union_witness'][1,i].tolist(),
                    requested_commands=requested[i].tolist(),decoded_commands=h['commands'][2,i].tolist(),
                    expected_alias=expected_alias[i].tolist(),decoded_alias=h['alias'][2,i].tolist()))
            r=saved['groups'][g]
            groups[g]=dict(cases=n,strict_passed=r['passed'],shape_preserved_run1=int(sameplan.sum()),
                emitted_seen_training_shape=int(knownplan.sum()),
                union_enabled=int(on.sum()),union_enabled_eq_passed=int((on&eq_ok).sum()),
                union_enabled_witness_passed=int((on&pair_ok).sum()),
                expected_transfers=int(wanted_transfer.sum()),transfer_alias_passed=int((wanted_transfer&alias_ok).sum()),
                transfer_commands_preserved=int((wanted_transfer&commands_ok).sum()),
                transfer_commands_preserved_and_alias_passed=int((wanted_transfer&commands_ok&alias_ok).sum()),
                transfer_alias_matches_training_mapping=int((wanted_transfer&alias_seen).sum()),examples=case_examples)
        all_runs[str(seed)]=groups
    out=dict(coverage=coverage,runs=all_runs,
             interpretation='post-hoc diagnosis only; no changed split, training or corrected output')
    a.output.write_text(json.dumps(out,indent=2)+'\n')
    for seed,groups in all_runs.items():
        for g,r in groups.items():
            print(seed,g,'strict',r['strict_passed'],'/',r['cases'],'union-on eq',r['union_enabled_eq_passed'],'/',r['union_enabled'],
                  'transfer alias',r['transfer_alias_passed'],'/',r['expected_transfers'],'seen-shape',r['emitted_seen_training_shape'])
    print('output-atom support:',{g:v['all_output_atoms_seen'] for g,v in coverage.items()})

if __name__=='__main__':main()
