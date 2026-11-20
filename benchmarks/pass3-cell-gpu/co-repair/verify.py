"""Validate archive gates for the real corpus, the trained catalog and its tested layouts."""
from pathlib import Path
import hashlib,json
from statistics import median

def read(p):return json.loads(p.read_bytes())

def verify(d):
    corpus=read(d/'corpus.json');owners=read(d/'owner-census.json')
    assert len(corpus)==10 and sum(x['runs'] for x in corpus.values())==13339
    for n,c in corpus.items():
        assert owners[n]['counts']['effective_unions']==c['unions']
        assert owners[n]['counts']['subscriber_rows']==c['subscribers']
        for k in ('rhs','spine','writes','known_class_roots','schedule'): assert c['gpu_exact'][k]==c['runs']
    native=read(d/'native.json')
    assert set(native)=={n for n,c in corpus.items() if c['split']!='anchor'}
    assert all(m['status']=='pass' and all(t['status']=='pass' for t in m['checks'].values()) for m in native.values())
    f=read(d/'catalog.json');training=read(d/'training.json');selection=read(d/'selection.json')
    assert set(f['training'])==set(training)=={n for n,c in corpus.items() if c['split']=='train'}
    assert set(selection)==set(corpus)-set(training)
    assert f['chosen']==min(f['calibration'],key=f['calibration'].get)
    assert all(len(v)==f['budget'] for v in f['catalogs'].values())
    directory=read(d/'directory.json');summary=read(d/'summary-cost.json');growth=read(d/'nesting.json')
    for n,s in selection.items():
        assert s['catalog_sha256']==hashlib.sha256((d/'catalog.json').read_bytes()).hexdigest()
        for k,v in s['arms'].items():
            assert v['runs']==corpus[n]['runs'] and v['exact'] and len(v['samples_ms'])==12
            assert v['median_ms']==median(v['samples_ms'])
            assert v['trace_credit']['attached']==v['readers']
        for m in directory[n].values():
            assert all(m[k]==directory[n]['row'][k] for k in ('instances','readers','key_probes','collisions','collision_tests'))
            assert m['exact'] and len(m['samples_ms'])==10 and m['median_ms']==median(m['samples_ms'])
        for k in ('row','mask'):
            a,b=directory[n][k],directory[n][k+'-sparse']
            assert a['notifications']==b['notifications'] and a['repair_rows']==b['repair_rows']
            assert a['notification_word_tests']>b['notification_word_tests']
            assert all(summary[n][k+'-sparse'][x]>0 for x in ('summary_bytes','summary_reads','summary_updates'))
        g=growth[n]['nested-two']
        assert g['original_pairs']==g['retained_original_pairs']==growth[n]['one']['readers']
        assert growth[n]['producer']['result_only_masks']>0
        assert all(m['exact'] and len(m['samples_ms'])==8 for m in growth[n].values())
    cold,hot=(read(d/'external-control.json')[k]['arms']['two'] for k in ('demand-0','demand-1'))
    assert (cold['notifications'],hot['notifications'],cold['collisions'],hot['collisions'])==(3,4,2,2)

if __name__=='__main__':
    verify(Path(__file__).resolve().parent)
    print('Verified real family split, native semantics, ordered traces, frozen selection, overlap and directory controls.')
