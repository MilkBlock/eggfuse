"""Sample the exact private Graph after every post-placement Run for a prespecified held-out subset."""
import argparse,json
from pathlib import Path
from study import CASES,READ,references,run_native


def curve(a):
    a.reference=references()
    evidence={}
    for name in CASES[2:]:
        rows=READ(a.out/(name+'-episodes.json'))['episodes']
        # Use only observable width and pending stock occupancy to pick a representative paired state.
        which=next((e for e in rows if e['x'][0]>1 and e['x'][3]>0),rows[0])
        keep,priv=run_native(a,name,dict(focus=which['id'],paired=True,private=True,graph_curve=True))
        anchor=keep['focus'];area=[]
        for x in (keep,priv):
            assert len(x['graph_curve'])==x['port_runs']>0
            assert x['graph_curve'][-1]==x['final_probe'][0] and x['final_probe'][1]>0
            assert (x['focus']['members'],x['focus']['features'],x['later_ports'])==(anchor['members'],anchor['features'],keep['later_ports'])
            area.append(sum(x['graph_curve']))
        assert keep['final_probe'][1:]==priv['final_probe'][1:]
        delta=keep['terminal_graph_bytes']-priv['terminal_graph_bytes']
        assert delta==keep['graph_curve'][-1]-priv['graph_curve'][-1]
        evidence[name]=dict(id=which['id'],members=anchor['members'],x=anchor['features'],run=anchor['run'],
            old_ports=keep['later_ports'],post_action_runs=keep['port_runs'],source=keep['source'],graph=keep['graph'],
            graph_byte_runs_saving=area[0]-area[1],owner_byte_runs_saving=keep['owner_byte_runs']-priv['owner_byte_runs'],
            terminal_saving=delta,dynamic_curves=[keep['graph_curve'],priv['graph_curve']],
            static_program_bytes=keep['final_probe'][1])
        (a.out/'curves.json').write_text(json.dumps(evidence,separators=(',',':'))+'\n')
        print(name,anchor['run'],(area[0]-area[1]),delta,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','engine','out'):p.add_argument(k,type=Path)
    curve(p.parse_args())
