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
    held=json.loads((HERE/'jacobi.json').read_bytes())
    assert set(held)=={'jacobi-1d/1703','jacobi-1d/1709'}
    for arms in held.values():
        for mode in ('leaf','inline','delta'):
            arm=arms[mode]
            assert all(arm['checks'].values()) and arm['identity']==arms['leaf']['identity']
            assert arm['rhs']==arm['neural_rhs']==arms['vanilla']['rhs']==41319
            assert arm['direct']*100>=arm['fresh_cells']*98
            assert arm['wins']==413 and arm['max_chain']==11 and len(arm['ms'])==8
        assert arms['delta']['net_entry_after_rebuild']==22907

    retirement=json.loads((HERE/'retirement.json').read_bytes())
    assert len(retirement)==4
    for key,arms in retirement.items():
        leaf,delta=arms['leaf-retire'],arms['delta-retire']
        assert leaf['identity']==delta['identity'] and leaf['source_exact'] and delta['source_exact']
        assert leaf['winners']==delta['winners'] and delta['net_entry_after_rebuild']>0
        assert delta['initial_row_decodes_saved']>0 and len(delta['ms'])==4
        assert leaf['native_fact_decodes']==delta['native_fact_decodes']
    counters=json.loads((HERE/'native-decodes.json').read_bytes())
    assert counters.keys()==retirement.keys()
    for key,arms in counters.items():
        assert arms['delta']['entry_row_reads_saved']>0
        assert arms['leaf']['graph']==arms['delta']['graph']
        assert arms['leaf']['fact_decode_calls']==arms['delta']['fact_decode_calls']
