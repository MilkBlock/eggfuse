"""Validate branch execution, source semantics, provenance and phase evidence."""
import json
import sys
from pathlib import Path
import argparse
from hashlib import sha256

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'pair-source-frontier'))
from evidence import checked


def verify(folder):
    primary=checked(folder,('results.json',),('sum-bits','conjugate-gradient','3mm'))
    writers=checked(folder,('writers.json',),('sum-bits','3mm'))
    for data,expected in [(primary,{'vanilla','off','positions','wires'}),(writers,{'vanilla','off','wires','write','both','reuse-key','absorbed'})]:
        for name,arms in data.items():
            assert set(arms)==expected
            for arm,r in arms.items():
                if arm=='vanilla':continue
                b=r['block']
                assert len(r['samples'])==len(r['ms'])==4
                assert all(0<x['rhs']<total for x,total in zip(r['samples'],r['ms']))
                if arm=='off':
                    assert b['plans']==b['group_rows']==b['dispatched']==0
                    continue
                assert 0<b['multirow_bindings']<=b['group_rows']==r['rhs'] and b['multirow_groups']<=b['groups']
                assert [sum(v[i] for v in b['by_rule'].values()) for i in range(4)]==[b[k] for k in ('dispatched','skipped_copies','static_skips','rewired_occurrences')]
                if arm!='write':assert b['dispatched']>0 and b['skipped_copies']>0
                if arm in ('wires','both','reuse-key','absorbed'):
                    assert 0<b['audited_fields']==b['rewired_occurrences']
                else:assert b['audited_fields']==0
                if arm in ('write','both','reuse-key','absorbed'):
                    w=b['writer']
                    assert w['calls']==w['full_key_probes']+w['reused_key']==w['changed']+w['unchanged']==w['audited']>0
                    assert [sum(v[i] for v in w['by_table'].values()) for i in range(4)]==[w[k] for k in ('calls','changed','prefix_ops','reused_key')]
                    assert arm in ('reuse-key','absorbed') or w['reused_key']==0
                    assert (w['proved_absorbed']>0)==(arm=='absorbed')
            if data is primary:
                for f in ('dispatched','skipped_copies','static_skips','group_rows'):
                    assert arms['positions']['block'][f]==arms['wires']['block'][f]
    assert primary['sum-bits']['wires']['wrong_operand_rejected']
    f=json.loads((folder/'fixture.json').read_bytes());assert set(f)=={'off','writer','both','reuse','absorbed'}
    assert any(f['off']['unions'])
    for arm in ('writer','both','reuse','absorbed'):
        v=f[arm]
        assert all(v[k]==f['off'][k] for k in ('winner','cells','graph','source','writes','unions'))
        w=v['work'];assert w['audited']==w['calls']==w['multi_key']>0
        assert w['prefix_ops']==w['calls']*2 and w['changed'] and w['unchanged']
    assert f['reuse']['work']['reused_key']>0
    if (folder/'overflow.json').is_file():
        failure=json.loads((folder/'overflow.json').read_bytes())
        assert set(failure)=={'off','writer','both','absorbed'}
        assert all(v==failure['off'] for v in failure.values())
        assert failure['off']['source_error']=='RHS primitive failed: +' and failure['off']['partial_rhs']>0
    manifest=json.loads((folder/'manifest.json').read_bytes())
    a,b=manifest['positions'],manifest['writers']
    assert a['pinned_source']==b['pinned_source'] and a['binary_sha256']!=b['binary_sha256']
    assert a['compiled']['src/ordered_effect_blocks.rs']==sha256((HERE/'block.rs').read_bytes()).hexdigest()
    assert b['compiled']['src/ordered_write_plan.rs']==sha256((HERE/'write_plan.rs').read_bytes()).hexdigest()
    assert a['compiled']['src/cell_prefix.rs']==b['compiled']['src/cell_prefix.rs']
    assert b['writer_overlay_sha256']==sha256((HERE/'writer.py').read_bytes()).hexdigest()
    return primary

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder',nargs='?',type=Path,default=HERE)
    print('Verified ordered effect programs on',len(verify(p.parse_args().folder)),'full Pass 3 sources, two writer comparisons and a late-union fixture')
