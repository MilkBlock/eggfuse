"""Find possible scalar or unique-table chains from one parent into another parent's existing field."""
import argparse,json
from pathlib import Path

def scan(program,plans):
    result={}
    for rid,(rule,plan) in enumerate(zip(program['recipe']['rules'],plans,strict=True)):
        if not plan:continue
        def slots(args):return {arg['slot'] for arg in args if 'slot' in arg}
        picks=[atom for atom,independent,_ in plan['ins'] if independent]
        fields=[slots(rule['query'][atom]['args']) for atom in picks]
        paths=[]
        for origin,own in enumerate(fields):
            known={field:() for field in own}
            for atom,independent,_ in plan['ins']:
                if independent:continue
                q=rule['query'][atom];args=q['args']
                used=slots(args[:-1]);target=args[-1].get('slot')
                if not used or target is None or target in known or not used<=known.keys():continue
                path=tuple(sorted({pos for field in used for pos in known[field]}|{atom}))
                known[target]=path
                consumers=[i for i,fields_i in enumerate(fields) if i!=origin and target in fields_i]
                if consumers:paths.append(dict(producer=origin,consumers=consumers,atoms=path,
                      final_call=q['call'].get('table',q['call'].get('primitive')),output=target))
        if paths:result[str(rid)]=dict(picks=len(picks),paths=paths)
    return result

def main(a):
    read=lambda path:json.loads(path.read_bytes())
    rules=scan(read(a.bundle/'program.json'),read(a.bundle/'plans.json'))
    sources={}
    for case,profile in read(a.profile).items():
        active={rid:profile['rules'][rid]['raw'] for rid in rules if rid in profile['rules']}
        sources[case]=dict(active=active,raw_parent_tuples=sum(active.values()))
    a.out.write_text(json.dumps(dict(interfaces=rules,profiles=sources),indent=1)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('bundle','profile','out'):p.add_argument(k,type=Path)
    main(p.parse_args())
