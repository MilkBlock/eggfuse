"""Test existing GPU cross-port messages on audited identical-input conflicts."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
from calibrate_semantic_family import load
from condition_boundary import captured_bridges
from audit_enumerated_features import feature_key


def main():
    p=argparse.ArgumentParser();p.add_argument('audit',type=Path);p.add_argument('manifest',type=Path);p.add_argument('output',type=Path);p.add_argument('--shared-context',action='store_true');a=p.parse_args()
    audit=json.loads(a.audit.read_text());manifest=json.loads(a.manifest.read_text());index={}
    for row in manifest['records']:
        path=Path(row['path']);m=json.loads(path.with_suffix('.json').read_text());index[m['capture']['case']]=path
    cache={};results=[];error=0.
    for rid,rule in audit['rules'].items():
        if len(rule['conflict_examples'])!=rule['conflicting_input_groups']:raise ValueError('truncated conflict groups')
        for group in rule['conflict_examples']:
            values=[]
            for row in group:
                case=row['case']
                if case not in cache:
                    _,m=load(index[case],'train');x,e=captured_bridges(index[case],m,shared_context=a.shared_context);cache[case]=x;error=max(error,e)
                values.append(cache[case][row['sample']])
            remaining=False;dist=[]
            for i in range(len(group)):
                for j in range(i):
                    if group[i]['target']==group[j]['target']:continue
                    equal=feature_key(values[i],[])==feature_key(values[j],[])
                    remaining|=equal;dist.append(float(np.linalg.norm(values[i]-values[j])))
            results.append(dict(rule=int(rid),examples=group,remaining_collision=remaining,opposing_target_l2=dist))
    out=dict(shared_context=a.shared_context,scope='boundary encoder on synthetic collision counterexamples; no training or rollout',audit_sha256=hashlib.sha256(a.audit.read_bytes()).hexdigest(),groups=len(results),remaining_collisions=sum(r['remaining_collision'] for r in results),maximum_gpu_error=error,results=results)
    a.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k!='results'}))
if __name__=='__main__':main()
