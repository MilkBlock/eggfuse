"""Check saved complete-runtime audits, address conservation, samples and executable receipts."""
import importlib.util
import json
import hashlib
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('lane_study', HERE/'study.py')
study = importlib.util.module_from_spec(spec)
spec.loader.exec_module(study)

def main():
    manifest = json.loads((HERE/'manifest.json').read_text())
    for name,sha in manifest['source_overlays'].items():
        assert hashlib.sha256((HERE.parent/name).read_bytes()).hexdigest()==sha,name
    assert hashlib.sha256((HERE.parent/'speculative-allocation-policy/policy.json').read_bytes()).hexdigest()==manifest['policy']
    results=json.loads((HERE/'results.json').read_text())
    rss=json.loads((HERE/'rss.json').read_text())
    assert results.keys()==rss.keys()==manifest['inputs'].keys()
    for case,rows in results.items():
        assert set(rows)=={'vanilla',*study.configurations({})}
        for name,q in rows.items():
            assert len(q['ms'])==len(q['wall_ms'])==4
            assert median(q['ms'])==q['median_ms'] and median(q['wall_ms'])==q['median_wall_ms']
            if name=='vanilla':continue
            study.check(case,name,q,rows)
            for k in ('rhs','writes','resumes','unions','state_sha','schedule','runs'):
                assert q['checks'][k]
            l=q['layout']
            assert l['heap_buffers']<=l['cells'] and l['empty']<=l['cells']
            if l['lanes']==0:assert l['inline']==0
            else:assert l['inline']+l['heap_buffers']==l['cells']
        assert set(rss[case])==set(rows)-{'vanilla'}
        for name,q in rss[case].items():
            assert name in rows and len(q['peak_rss_bytes'])==3 and min(q['peak_rss_bytes'])>0
            assert median(q['peak_rss_bytes'])==q['median_peak_rss_bytes']
        print(case,[(k,round(v['median_ms'],1)) for k,v in rows.items()])

if __name__=='__main__':
    main()
