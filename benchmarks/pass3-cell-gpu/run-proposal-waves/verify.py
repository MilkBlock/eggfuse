from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'pair-source-frontier'))
from evidence import checked
def verify(folder):
    groups=checked(folder,('results.json',),('sum-bits','conjugate-gradient','3mm'))
    for name,r in groups.items():
        assert set(r)=={'vanilla','off','one','eight','run'}
        for k in ('one','eight','run'):
            s=r[k]['wave']
            assert s['single_sets']==s['verified_single_sets']>0 and s['multi_sets']==s['validated_multi_sets']>0
            assert s['sealed_multi']==r[k]['counts']['raw_tuples']
            assert r[k]['model_scores']==r['off']['model_scores']
        assert r['one']['wave']['peak_rules']==1 and r['run']['wave']['peak_rules']>8
        assert r['run']['wave']['mixed_waves']>0
    return groups
if __name__=='__main__':print('Verified true issue-before-validation waves and exact source/physical identity on',len(verify(HERE)),'programs')
