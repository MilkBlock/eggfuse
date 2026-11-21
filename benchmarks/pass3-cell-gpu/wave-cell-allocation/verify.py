from pathlib import Path
import json,sys
from statistics import median
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'pair-source-frontier'))
from evidence import checked

def verify(folder):
    read=lambda f:json.loads((folder/f).read_bytes())
    data=checked(folder,('results.json',),('conjugate-gradient','3mm'))
    for name,arms in data.items():
        ref=arms['wave']
        for k,v in arms.items():
            if k in ('off','vanilla'):continue
            assert v['model_scores']==ref['model_scores']
            assert v['wave']['peak_tuples']==ref['wave']['peak_tuples'] and v['wave']['mixed_waves']>0
            if k=='wave':continue
            s=v['staging']
            assert s['offers_after_first_verify']==s['slots_after_first_verify']==0
            assert s['offers_before_first_verify']==ref['wave']['sealed_multi']+ref['wave']['sealed_single']
            assert s['complete_before_verify_runs']==s['nonempty_wave_runs']>0
            assert s['granted']==s['slots_before_first_verify']==s['used']+s['unused']
            if k!='reserve':assert s['used']==s['payload_identity'] and s['preconstructed']==s['granted']
        s=arms['all-lanes']['staging']
        assert s['fallback']==0 and s['granted']==s['offers_before_first_verify'] and s['used']==s['fresh']==ref['root_allocated']
        assert s['granted']==s['names_attached']
        for x in read('rss.json')[name].values():assert median(x['bytes'])==x['median'] and len(x['bytes'])==3
    extra=checked(folder,('batch-verifier.json',),('3mm',))['3mm']
    for k in ('block','named-block','eager-block'):assert extra[k]['block']['completed']>0
    a,b=extra['eager-block']['staging'],extra['all-lanes']['staging']
    for f in ('used','unused','granted','fresh','payload_identity'):assert a[f]==b[f]
    x=read('example.json');assert x['source_offers']==data['3mm']['wave']['wave']['peak_tuples'] and x['checked_vectors']>0
    return data
if __name__=='__main__':print('Verified on-device-independent native whole-Run issuance, private backing identity and both frozen source executions on',len(verify(HERE)),'programs')
