"""Recheck stable neural identities, complete source equality, strict rejection and timed counters."""
from pathlib import Path
import json
HERE=Path(__file__).resolve().parent


def check(path):
    data=json.loads(path.read_bytes())
    assert set(data)=={'sum-bits','dot-product','jacobi-1d','conjugate-gradient'}
    for case,row in data.items():
        arms=row['arms'];ref=arms['production']['identity']
        for name,arm in arms.items():
            assert len(arm['ms']) in (6,8)
            if name=='vanilla':
                assert arm['rhs']==ref['rhs'] and arm['graph']==ref['state_sha']
                continue
            assert arm['identity']==ref and arm['direct']*100>=98*arm['fresh'] and arm['aligned']
            assert arm['production_decodes']==arms['production']['production_decodes']
            stats=arm.get('production_page_reads',arm['page_reads'])
            if name in ('frame','frame-prefix','frame-tail-receipt'):
                assert stats['frame_rows']>0 and stats['union_source_rows']>0 and stats['offset_bytes']>=stats['parents']*4
            if name in ('prefix','frame-prefix'):assert stats['prefix_hits']>0
            if name in ('tail','tail-receipt','frame-tail-receipt','borrowed-receipt','issued-ports','compact','compact-issued'):assert stats['dead_port_calls']>0
            if name in ('receipt','tail-receipt','frame-tail-receipt','borrowed-receipt','issued-ports','compact','compact-issued'):assert all(x>0 for x in stats['seals'][:3])
            if name in ('borrowed-receipt','issued-ports','compact','compact-issued'):assert stats['seals'][3]>0
            if name in ('compact','compact-issued'):assert stats['audit_anchor_lists_omitted']>0 and not arm['page_reads']['audit_anchor_lists_omitted']
            if name in ('issued-ports','compact-issued'):assert stats['issue_frame_refs']+stats['issue_source_refs']==stats['parents']
        if case in ('sum-bits','dot-product'):
            for key,item in row['faults'].items():
                if key.startswith('root-'):assert 'no verified root recipe' in item['error']
                else:assert 'error' in item or item['graph']!=ref['state_sha']
    print('Verified',path.name)


if __name__=='__main__':
    for f in ('frames.json','seals.json','released.json','loans.json','compact.json'):check(HERE/f)

    profiles=json.loads((HERE/'phases.json').read_bytes())
    assert set(profiles)=={'jacobi-1d','conjugate-gradient'}
    for arms in profiles.values():
        for arm in arms.values():
            ms=arm['measured_ms'];assert len(arm['samples'])==3 and 0<sum(ms[1:])<ms[0]
