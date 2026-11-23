"""Append typed higher Cells mined from residual native commits of training programs only."""
import argparse
from pathlib import Path
import json
import shutil

import torch

from alternate_proofs import digest
from bake_ripsat import bake
from higher_cell import read
from residual_layouts import analyze
from ripsat_replay import unpack


def extend(root,donor,weights,base,traces,out):
    study=read(base/'study.json')
    original=unpack(read(base/'catalog.json'))
    catalog=set(original)
    program=read(donor/'program.json')
    training={r['directory'] for r in read(root/'manifest.json') if r['origin']=='eggcc' and r['split']=='train'}
    if training!=set(study['training']) or digest(weights)!=study['root_weights']:
        raise ValueError('incorrect parent training split or root Actor')
    additions=set()
    samples={}
    for name in sorted(training):
        trace=traces/name
        audit=read(trace/'opportunity.json')
        if (audit['native']['actor']!=digest(weights) or
            audit['catalog']!=digest(base/'catalog.json') or
            audit['native']['program']!=digest(root/name/'program.json') or
            digest(trace/'program.json')!=audit['native']['program'] or
            digest(root/name/'tape.json')!=study['training'][name]):
            raise ValueError('training trace does not belong to the parent experiment')
        diagnostics,targets=analyze(trace,program,catalog,max(map(len,original)))
        if diagnostics['reach']!=audit['reach']:
            raise ValueError('trace opportunities changed')
        additions.update(targets.keys()-catalog)
        samples[name]=dict(program=audit['native']['program'],tape=digest(trace/'tape.json'),
                           memory=digest(trace/'memory.jsonl'),policy=audit['native']['policy'],
                           added_candidates=diagnostics['new_layout_options'])
    if len({v['policy'] for v in samples.values()})!=1:
        raise ValueError('training traces used different deployed policies')
    if not additions:
        raise ValueError('no new ready layouts')
    out.mkdir(parents=True,exist_ok=True)
    def write(name,obj):
        (out/name).write_text(json.dumps(obj,separators=(',',':'))+'\n')
    additions=sorted(additions)
    write('appended.json',additions)
    write('catalog.json',original+additions)
    for file in ('shared.pt','boundary.pt'):
        shutil.copyfile(base/file,out/file)
    catalog_sha=digest(out/'catalog.json')
    write('study.json',dict(schema='eggfuse-frozen-bake-extension/v1',
          parent_catalog=digest(base/'catalog.json'),catalog_sha=catalog_sha,
          weights=study['weights'],root_weights=study['root_weights'],training=study['training'],
          training_traces=samples,original=len(original),added=len(additions)))
    write('boundary.json',dict(catalog=catalog_sha,scorer=study['weights'],weights=digest(base/'boundary.pt')))
    bake(program,weights,out)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('root','donor','weights','base','traces','out'):
        p.add_argument(key,type=Path)
    a=p.parse_args()
    torch.set_num_threads(1)
    extend(a.root,a.donor,a.weights,a.base,a.traces,a.out)
