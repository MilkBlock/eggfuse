"""Check source family separation, per-run acceptance and actual native repair savings."""
import json
from pathlib import Path


def check(path):
    read=lambda n:json.loads((path/n).read_bytes())
    training=read('training.json');captures=read('capture.json')
    main=read('results.json');gate=read('result-gate.json');boundary=read('counterexamples.json')
    assert len([c for c in captures.values() if c['split']=='train'])==4
    assert len([c for c in captures.values() if c['split']=='development'])==2
    assert len([c for c in captures.values() if c['split']=='heldout'])==2
    assert len([c for c in captures.values() if c['split']=='anchor'])==2
    assert set(training['training']).isdisjoint(main)
    assert training['examples']==2400 and training['updates']==400 and training['batch']==64
    assert training['bake']['pool']>=len(training['bake']['selected'])==8
    for k,v in training['styles'].items():
        assert v['examples']==training['examples']
        if k.startswith('paired'):assert v['pairs']=={'reader':200,'collision':200,'prior':200}
        assert (path/'weights'/f'{k}.json').is_file()
    for study in (main,gate):
        for n,arms in study.items():
            source=captures[n]
            baseline=arms['generic']
            for label,x in arms.items():
                assert x['state_sha']==baseline['state_sha'] and x['exact_deliveries']
                assert x['runs']==source['runs'] and x['unions']==source['unions']
                assert x['all_recipients']==baseline['all_recipients']
                assert x['neural_rhs']==source['source_neural_rhs'] and x['total_rhs']==source['source_total_rhs']
                if 'median_whole_ms' in x:assert len(x['whole_ms'])==(18 if study is main else 8)
                if 'common' in x:
                    assert x['rust_torch_shadow_decisions_equal']
                    assert x['common']['all']['candidates']==source['events']
                    assert x['common']['held_template_family']['candidates']>0
                    assert x['common']['long_union_history']['candidates']>0
            assert arms['every']['counts']['applied']>0 and arms['every']['repair_key_probes']<baseline['repair_key_probes']
            if study is gate:
                assert arms['gate']['counts']['applied']==arms['every']['counts']['applied']
            else:
                assert arms['stale']['counts']['stale']>0 and arms['unsafe']['counts']['unsafe_external_rejected']>0
    test=main['gemm-bias-relu']
    assert test['synthetic-1703']['common']['all']['wrong_omitted_external']==404
    assert test['real-1703']['common']['all']['wrong_omitted_external']==10
    assert test['paired-1703']['common']['toggle_reader']['both_correct']==319
    a,b,c=[boundary[n] for n in ('0-0','1-0','1-1')]
    p,q=[s['arms']['capture']['opportunities'][0] for s in (a,b)]
    assert [p[k] for k in ('cell','op','template','fast')]==[q[k] for k in ('cell','op','template','fast')]
    assert not p['external'] and q['external'] and b['arms']['unsafe']['counts']['unsafe_external_rejected']>0
    assert c['collisions']==1 and b['collisions']==0
    for s in (a,b,c):
        ref=s['arms']['generic']
        assert all(x['state_sha']==ref['state_sha'] and x['ordered_unions']==ref['ordered_unions'] and x['recipients']==ref['recipients'] for x in s['arms'].values())
    print('Verified native CPU corpus ablation, real recipient order and stale/external/collision controls.')


if __name__=='__main__':check(Path(__file__).resolve().parent)
