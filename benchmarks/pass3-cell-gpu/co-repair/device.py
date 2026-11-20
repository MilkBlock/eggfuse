"""Evaluate causal subscription groups on the original device schedule and semantics."""
import sys
from pathlib import Path
import numpy as np
from collect import GPU,read,digest
from run import execute

def files(root,reference,case):
    anchor=case in ('sum-bits','dot-product')
    data=root/case
    return (reference/f'release-input-{case}' if anchor else data/'input',
            reference/f'oracle-{case}' if anchor else data/'reference',
            reference/f'release-{case}' if anchor else data/'device')

def execute_case(root,reference,weights,case,dest,edges=(),mode=1,members=1,trace=False,count=True,resident=None,sparse_words=False,nested=False,solo=False):
    image,oracle,gold=files(root,reference,case)
    tables=read(image/'ingress.json')['tables']
    by_name={t['name']:i for i,t in enumerate(tables)}
    repair=read(oracle/'report.json')['repair_cells']['catalog']
    layout=read(image/'device.json')['layout']
    shapes=[-1 if x is None else x for x in repair['tables']]
    ids=[]
    for producer,reader,column in edges:
        if producer not in by_name or reader not in by_name:continue
        p,t=by_name[producer],by_name[reader]
        if shapes[p]<0 or shapes[t]<0 or column>=len(tables[t]['schema'])-1:continue
        if tables[t]['schema'][column]!=tables[p]['schema'][-1]:
            raise ValueError('catalog edge does not typecheck')
        ids.append([p,t,column])
    blank=[-1]*(len(read(image/'ingress.json')['rules'])*layout['DEPTH'])
    policy=dict(ids=[],select=False,notify=True,entries=blank,pivots=blank,tables=[0]*len(tables),
                shapes=shapes,group=dict(edges=ids,mode=mode,members=members,trace=trace,sparse_words=sparse_words,nested=nested,solo=solo))
    execute(image/'device.json',weights,reference/'ports-1703.pt',2048,2,dest,
            block_study=policy,count_work=count,measure_resident=resident)
    # The independent ordered audit already aligned the gold trace to Rust.
    # Compare its physical source witnesses and full endpoint again here.
    with np.load(gold/'output.npz') as expected,np.load(dest/'output.npz') as actual:
        for k in ('runs','resumes','writes','unions','meta','parents','birth_runs'):
            np.testing.assert_array_equal(actual[k],expected[k],err_msg=k)
        np.testing.assert_array_equal(actual['rhs'][:,:2],expected['rhs'][:,:2])
        np.testing.assert_array_equal(actual['rhs'][:,4:],expected['rhs'][:,4:])
        for t,spec in enumerate(tables):
            at=expected['meta'][:,0]==t
            np.testing.assert_array_equal(actual['rows'][at,:len(spec['schema'])],
                                          expected['rows'][at,:len(spec['schema'])])
    report=read(dest/'run.json')
    assert report['finished'] and not report['fault']
    return report
