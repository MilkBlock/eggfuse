"""Check all published examples from the immutable source evidence and independent donor observation."""
from argparse import ArgumentParser
from pathlib import Path
from authorize import HERE,V2,load_checked,read
def main():
    p=ArgumentParser(description=__doc__);p.add_argument('exp',type=Path);a=p.parse_args();small=a.exp/'compact-holdouts-20261121-v1'
    donors={n:small/(n+'-1703')/'program.json' for n in ('dot-product','jacobi-1d')}
    controls=read(HERE/'controls.json');assert len(controls)==12
    for n in ('dot-product','sum-bits','3mm'):
        program=(a.exp/'extra-pass3-transfer-v1' if n=='3mm' else small)/(n+'-1703')/'program.json'
        c=load_checked(HERE/(n+'.json'),V2/'evidence.json',donors,program)
        assert c['strict_named']['library']==[[[143,1,55]]]
        t=c['strict_named']['set_publication'];assert t['target_sha256']==c['target_sha256']
        assert t['path']==[[143,1,55],[55,1,143]] and t['kinds']==['fresh_constructor_let','fresh_constructor_set']
        s=c['support'][0]
        assert s['native']['local_record_ids']==[0,8,12] and s['native']['tokens']==[6,10]
        assert s['native']['terminal_parent_port']==[0,4]
        assert s['source']['serials']==[1737,1822,2625] and s['source']['runs']==[131,135,139]
        assert s['source']['first_port']==[3835405795329,131] and s['source']['second_port']==[4170413244417,135]
        assert c['excluded']==[dict(donor='jacobi-1d',reason='no_observed_paid_terminal_consuming_this_middle',middle=5598)]
    print('Verified three static target bindings from one exact donor middle, the separate fresh-constructor Set contract and the pinned native causal chain.')
if __name__=='__main__':main()
