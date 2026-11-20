"""Time the verified overlap-replacing native branch, rotate comparator order by trial."""
import argparse
from pathlib import Path
from statistics import median
from study import read,save,run


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('runtime','corpus','ref','matrix','out'):p.add_argument(k,type=Path)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False);results={}
    for key,v in read(a.matrix/'results.json').items():
        case,seed=key.split('/');anchor=case in ('sum-bits','dot-product')
        program=a.ref/case/'program.json' if anchor else a.corpus/case/'program.json'
        gold=a.ref/f'events-{case}' if anchor else a.corpus/case/'observation'
        action=a.matrix/f'{case}-{seed}-action.json'
        no=a.out/f'{case}-{seed}-none.json';c=read(a.matrix/f'{case}-{seed}-one-shot.json');c['mode']='null';save(no,c)
        arms=('none','one-shot','high-repeat','all-repeat');stats={n:dict(ms=[],cli=[]) for n in arms}
        for trial in range(8):
            order=arms[trial%4:]+arms[:trial%4]
            for name in order if trial<4 else order[::-1]:
                dest=a.out/f'{case}-{seed}-{trial}-{name}';path=no if name=='none' else a.matrix/f'{case}-{seed}-{name}.json'
                wall=run(a,program,dest,path,action,False);rep=read(dest/'report.json')
                assert read(dest/'state.json')==read(gold/'state.json')
                count=sum(len(q['wins']) for q in rep['late_merge_ports']['records'])
                assert count==(0 if name=='none' else v['arms'][name]['actual_children'])
                stats[name]['ms'].append(1000*rep['inference_seconds']);stats[name]['cli'].append(wall)
        for item in stats.values():item['median_ms']=median(item['ms']);item['median_cli_ms']=median(item['cli'])
        results[key]=stats;save(a.out/'results.json',results);print(key,{n:round(t['median_ms'],2) for n,t in stats.items()},flush=True)
