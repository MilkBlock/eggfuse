"""Generate and independently check equality proof macros over a frozen Cell plan."""
from collections import deque
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
PLANS=HERE.parent/'union_ablation/plan.json'
REFL,LOCAL,EDGE,FLIP,JOIN,CONG=range(6)
BASE=256


def path(edges,a,b):
    if a==b:return (REFL*BASE+a,)
    queue=deque([(a,())]);seen={a}
    while queue:
        x,prefix=queue.popleft()
        for y,step in edges[x]:
            if y in seen:continue
            proof=prefix+step+((JOIN*BASE,) if prefix else ())
            if y==b:return proof
            seen.add(y);queue.append((y,proof))
    return None


def endpoints(p,op,arg):
    if op==LOCAL:return tuple(p['public'][arg][j] for j in p['local_pair'])
    a,b=divmod(arg,3)
    return p['public'][0][a],p['public'][1][b]


def derive(p,mask,bridge):
    edges=[[] for _ in range(p['vertices'])]
    def link(a,b,step):
        edges[a].append((b,step));edges[b].append((a,step+(FLIP*BASE,)))
    for owner in range(2):
        if mask&(1<<owner):link(*endpoints(p,LOCAL,owner),(LOCAL*BASE+owner,))
    if bridge:link(*endpoints(p,EDGE,bridge-1),(EDGE*BASE+bridge-1,))
    changed=True
    while changed:
        changed=False
        for i,r in enumerate(p['implications']):
            a,b=r['unifies']
            if path(edges,a,b) is not None:continue
            args=[path(edges,*guard) for guard in r['requires']]
            if all(v is not None for v in args):
                link(a,b,sum(args,())+(CONG*BASE+i,));changed=True
    return edges


def prove(p,program):
    """Check stack types and ordered constructor operands, extract minimal event premises."""
    stack=[];mask=bridge=peak=0
    for word in program:
        op,arg=divmod(word,BASE)
        if op==REFL and arg<p['vertices']:stack.append((arg,arg))
        elif op==LOCAL and arg<2:
            mask|=1<<arg;stack.append(endpoints(p,op,arg))
        elif op==EDGE and arg<9:
            if bridge not in (0,arg+1):raise ValueError('two external premises')
            bridge=arg+1;stack.append(endpoints(p,op,arg))
        elif op==FLIP and not arg:stack.append(stack.pop()[::-1])
        elif op==JOIN and not arg:
            c,d=stack.pop();a,b=stack.pop()
            if b!=c:raise ValueError('path ports do not compose')
            stack.append((a,d))
        elif op==CONG and arg<len(p['implications']):
            rule=p['implications'][arg]
            for guard in reversed(rule['requires']):
                if tuple(guard)!=stack.pop():raise ValueError('unproved constructor operand')
            stack.append(tuple(rule['unifies']))
        else:raise ValueError('unknown or out-of-range instruction')
        peak=max(peak,len(stack))
    if len(stack)!=1 or peak>32:raise ValueError('invalid final proof stack')
    return (*stack[0],mask,bridge)


def bake(p):
    public=sum(p['public'],[]);routes=[];macros=[];code=[];ids={}
    for mask in range(4):
        for bridge in range(10):
            edges=derive(p,mask,bridge)
            for a in public:
                for b in public:
                    program=path(edges,a,b)
                    if program is None:routes.append(-1);continue
                    if program not in ids:
                        x,y,needs,event=prove(p,program)
                        if (x,y)!=(a,b) or needs&~mask or event not in (0,bridge):
                            raise ValueError('proof admission does not cover the route')
                        ids[program]=len(macros)
                        macros.append([x,y,needs,event,len(code),len(program)])
                        code.extend(program)
                    routes.append(ids[program])
    return dict(public=public,routes=routes,macros=macros,code=code)


def plans():return json.loads(PLANS.read_text())['plans']
