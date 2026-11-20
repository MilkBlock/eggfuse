"""Independently reconstruct the frozen scheduler and check every held-out execution."""
from collections import defaultdict
import json
from pathlib import Path
from statistics import median


def verify(training_path,heldout_path):
    training=json.loads(training_path.read_bytes())
    assert set(training['training_programs'])=={'affine-twins','clamped-ramp','segmented-prefix','window-laplacian'}
    expected={}
    for sig,observations in training['measurements'].items():
        best=[]
        for mode in (1,2):
            gains=defaultdict(list)
            for o in observations:
                assert o['case'] in training['training_programs'] and len(o['ms'])==3
                base,arm=o['ms'][0],o['ms'][mode]
                if base>=0.02:gains[o['case']].append(1-arm/base)
            points=[median(values) for values in gains.values()]
            if len(points)>=3 and sum(x>0.03 for x in points)>=3 and median(points)>0.08:
                best.append((median(points),mode))
        if best:expected[sig]=max(best)[1]
    assert expected==training['library']
    heldout=json.loads(heldout_path.read_bytes())
    for case,report in heldout.items():
        assert case not in training['training_programs'] and set(report['actions'])<={0,1,2}
        if case=='sum-bits':assert report['negative']=={'source':True,'width':True,'unproved':True}
        arms=report['arms'];base=arms['immediate']
        for arm,v in arms.items():
            assert len(v['ms'])>=6 and median(v['ms'])==v['median_ms']
            if arm=='vanilla':continue
            assert v['aligned'] and all(v['checks'].values()) and v['rhs']==v['neural_rhs']
            assert v['direct_cells']*100>=98*v['fresh']
            for f in ('raw','commits','physical','multi','children','cells','request_digest'):assert v[f]==base[f]
        assert arms['baked']['requests']['lanes']<=arms['parents-8']['requests']['lanes']
    return len(expected),len(heldout)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder',type=Path)
    d=p.parse_args().folder;print('Accepted templates and checked held-out workloads:',verify(d/'training.json',d/'heldout.json'))
