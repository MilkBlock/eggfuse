"""Read-only stratification by the preceding observed subscriber fanout per physical region."""
from collections import Counter,defaultdict
from pathlib import Path
import argparse,json
import numpy as np
from fit import Trace
from collect import read


def summarize(capture,study,profiles):
    result={}
    for n,r in read(study/'results.json').items():
        t=Trace(capture/n);bins=defaultdict(dict)
        with np.load(profiles/n/'co-repair.npz') as detail,np.load(profiles/n/'output.npz') as data:
            unions=data['unions'];fanout=Counter()
            for u,row,_ in detail['events']:
                fanout[int(u),int(row)//32]+=1
            for (u,w),cnt in fanout.items():
                window=(int(unions[u,0])-1)//32+1
                item=bins[window].setdefault(w,[0,0]);item[0]+=cnt;item[1]+=1
        by_arm={}
        for k in ('static','learned','hindsight'):
            with np.load(study/f'{n}-{k}-counts/selected.npz') as f:
                words=f['words']
            strata=defaultdict(Counter)
            for window,live in enumerate(t.live):
                for w in np.flatnonzero(live):
                    w=int(w);work,events=bins[window].get(w,[0,0])
                    bucket='no previous wake' if not events else 'one per union' if work==events else 'up to two' if work<=2*events else 'over two'
                    selected=int(words[window,w//32])&(1<<(w%32))!=0
                    st=strata[bucket]
                    st['eligible_region_windows']+=1;st['selected']+=int(selected)
                    st['potential_clean_rows']+=int(t.samples[window,w,6])
                    st['saved_clean_rows']+=int(selected)*int(t.samples[window,w,6])
            assert sum(s['saved_clean_rows'] for s in strata.values())==r['arms'][k]['price']['clean_rows_saved']
            by_arm[k]={b:dict(v) for b,v in strata.items()}
        result[n]=by_arm
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for f in ('capture','study','profiles','out'):p.add_argument(f,type=Path)
    a=p.parse_args();a.out.write_text(json.dumps(summarize(a.capture,a.study,a.profiles),indent=1)+'\n')
