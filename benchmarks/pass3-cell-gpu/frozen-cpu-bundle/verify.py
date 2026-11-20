import json
from pathlib import Path


def verify(folder):
    d=json.loads((folder/'relocation.json').read_bytes())
    assert set(d)=={'sum-bits','pair'}
    for name,v in d.items():
        assert v['profile']=='frozen-ports/v1' and 100*v['directly_allocated']>=98*v['all_fresh']
        assert len(v['state'])==len(v['compiled_plan'])==64 and v['sealed']>0 and v['files']==8
    assert d['sum-bits']['rhs']==7265 and d['pair']['rhs']==2 and d['pair']['foreign_image_rejected']
    assert set(d['sum-bits']['corruptions_rejected'])=={'ports.bin','plans.json','request.json','incompatible_settings'}
    assert all(d['sum-bits']['corruptions_rejected'].values())
    return d

if __name__=='__main__':print('Verified relocated one-shot and full audit entry points on',len(verify(Path(__file__).parent)),'CPU programs')
