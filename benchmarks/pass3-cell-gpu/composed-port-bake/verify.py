"""Validate conservation of actual source work on the archived ablations."""
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent


def check(path):
    rows=json.loads(path.read_bytes())
    assert set(rows)=={f'{w}/{s}' for w in ('sum-bits','dot-product') for s in (1703,1709)}
    for _,arms in rows.items():
        ref=arms['leaf']
        for name,arm in arms.items():
            assert ref['identity']==arm['identity'] and arm['source_exact']
            assert ref['rhs']==arm['rhs'] and ref['graph']==arm['graph'] and ref['runs']==arm['runs']
            assert ref['winners']==arm['winners'] and ref['root_wire_bytes']==arm['root_wire_bytes']
            assert arm['direct']*100>=arm['fresh']*98 and len(arm['ms'])==8
            rebuilds,visited,visible,entries,owned,residual,sealed,fields,removed=arm['boundary']
            assert entries==owned+residual
            assert arm['initial_row_decodes_saved']+residual==visible
            assert arm['net_entry_after_rebuild']==visible-entries-visited
            assert sealed<=owned and removed<=sealed
            if name in ('inline','delta','mixed','delta-mixed'):
                assert 0<removed==sealed==owned
            if name.startswith('delta'):
                assert arm['delta'] is not None
    print('Checked',path.name,'two sources, both seeds, ordered receipts and conservation of entry work.')


if __name__=='__main__':
    check(HERE/'receipts.json')
    check(HERE/'incremental.json')
