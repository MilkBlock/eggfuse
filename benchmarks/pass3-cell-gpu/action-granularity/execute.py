"""One-emission specialization of the checked device root verifier and original cross-Run resume logic."""
import inspect
from pathlib import Path
import sys
import numpy as np

HERE=Path(__file__).resolve().parent;GPU=HERE.parent
sys.path.insert(0,str(GPU))
import run


def replace(source,anchor,value):
    if source.count(anchor)!=1:raise ValueError(f'shared executor changed at {anchor}')
    return source.replace(anchor,value)


def executor(arm,corrupt=False):
    kind=['raw','leaf','macro'].index(arm)
    src=inspect.getsource(run.execute)
    src=replace(src,'(waves,nr,hidden,ranks)!=(2,2,8,8)','(waves,nr,hidden,ranks)!=(1,2,8,8)')
    src=replace(src,"if len(compound['child'])!=24*len(joins)+18:","if len(compound['child'])!=19*len(joins)+2+64+2048:")
    s=(GPU/'executor.metal').read_text()
    for marker in ('\n    if(state[76])','\n            device const int *index','\n            state[76]=0','\n                    state[76]=n+1'):
        s=s.replace('#if COMPOUND'+marker,'#if COMPOUND && ACTION_KIND==2'+marker)
    src=replace(src,"    shader=(HERE/'executor.metal').read_text()", "    shader=granular_shader\n    constants+=f'\\n#define ACTION_KIND {kind}\\n#define ACTION_CORRUPT {int(corrupt)}'")
    src=replace(src,"if compound is not None:kernels+='\\n'+(module/'compound.metal').read_text()",
                "if compound is not None:kernels+='\\n'+(module/'compound.metal').read_text()+'\\n'+granular_issue")
    src=replace(src,"if compound is not None:child_weights=torch.tensor(compound['child'],device=dev,dtype=torch.float32)",
    """if compound is not None:
                child_weights=torch.tensor(compound['child'],device=dev,dtype=torch.float32)
                headers=zeros((steps,2,2))
                payload=zeros((steps,2,layout['NINPUT']+2) if kind==0 else 1,torch.int64)""")
    a=src.index('                    if compound is not None:\n',src.index('    def infer():'))
    b=src.index('                    elif fusion:',a)
    src=src[:a]+'''                    if compound is not None:
                        prev=frontier[iteration%2];nxt=frontier[1-iteration%2]
                        lib.issue_unit(prog,literal,state,meta,dyn,head,feats,policy,child_weights,prev,nxt,raw_trace,
                                       verdict,headers,payload,threads=2)
                        lib.verify_unit(prog,literal,state,meta,dyn,head,wm,count,tokens,headers,payload,verdict,threads=1)
                        if kind==2:lib.compound_resume(prog,literal,state,meta,dyn,head,wm,count,tokens,threads=1)
'''+src[b:]
    src=replace(src,"                np.savez_compressed(root/'compound-output.npz',claims=claims)", """                np.savez_compressed(root/'compound-output.npz',claims=claims)
                np.savez_compressed(root/'issued.npz',headers=headers[:st[11]].cpu().numpy(),
                                    raw=payload[:st[11]].cpu().numpy() if kind==0 else np.empty(0,dtype=np.int64))""")
    src=replace(src,"    (root/'run.json').write_text", """    record['execution_roles'].update(verification='one issued certificate per row, original source visibility',
                                   action_kind=['raw','leaf','macro'][kind],rows=2,waves=1)
    (root/'run.json').write_text""")
    env=dict(run.__dict__,kind=kind,corrupt=corrupt,granular_shader=s,granular_issue=(HERE/'issue.metal').read_text())
    exec(compile(src,str(__file__)+'::execute','exec'),env);return env['execute']


def config(model,entries,residual):
    return dict(catalog=entries,rows=2,ranks=8,hidden=8,waves=1,weights=model['root'],complete_residual=residual,
                compound=dict(joins=model['joins'],child=model['head'],batch=True))
