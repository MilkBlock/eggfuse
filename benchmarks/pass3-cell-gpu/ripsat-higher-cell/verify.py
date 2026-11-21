import hashlib,json
from pathlib import Path
from runpy import run_path
from statistics import median
HERE=Path(__file__).resolve().parent
study=run_path(str(HERE/'study.py'));read=lambda p:json.loads(p.read_bytes())
m=read(HERE/'manifest.json');faults=read(HERE/'faults.json')
for k,h in m['sources'].items():assert hashlib.sha256((HERE.parent/k).read_bytes()).hexdigest()==h,k
for case,arms in read(HERE/'results.json').items():
    assert hashlib.sha256((HERE.parent/'ripsat-publication-chain'/(case+'.json')).read_bytes()).hexdigest()==m['authorization'][case]
    a,b=arms['direct'],arms['higher'];study['verify'](a,b)
    c=b['higher']['counts']; assert c['requests']==c['retired_no_result']+c['retired_stale']+c['transferred']
    assert c['request_reads']>=c['prepared']==c['middles']==c['operand_guard_reads']==c['operand_transfers']
    assert c['operand_fallbacks']==0 and c['no_first_replies']>0 and c['retired_stale']>0
    assert c['request_batches'] and c['peak_batch']>1 and c['lookup_checks']==a['set']['opened']
    assert all(arms['faults'][k]['stale'] for k in ('stale-generation','stale-epoch','only-stale'))
    assert arms['faults']['duplicate']['duplicate'] and arms['faults']['alias-mismatch']['operand_fallback']
    assert all(faults[case][n]==faults[case]['direct'] for n in ('duplicate','stale-generation','stale-epoch'))
    assert faults[case]['only-stale']==faults[case]['alias-mismatch']==faults[case]['let']
    for q in (a,b):
        assert len(q['ms'])==len(q['wall'])==4 and q['median_ms']==median(q['ms'])
        assert q['median_profiled_protocol_ms']==median(sum(t) for t in q['phase_samples_ms'])
        assert all(q['higher']['counts'][k]==0 for k in study['CLOCKS'])
    print(case,c['requests'],c['transferred'],c['terminal_commits'],a['median_profiled_protocol_ms'],b['median_profiled_protocol_ms'])
