"""Exhaustive bounded two-Cell constructor interfaces, independent of labels.

One completed producer, one consumer, at least one shared constructor fact.
Consumer atoms may have explicit boundary support or omit that support.
Omitted support is not a negative label: other facts may still satisfy the query.
No source-program reachability or whole-family closure claim.
"""
import argparse,itertools,json
from pathlib import Path
from synthetic_cell_inputs import select_recipe,canonical_seed,digest
from typed_literal import value as literal


def partitions(n):
    if n==0:
        yield ();return
    def go(prefix):
        if len(prefix)==n:yield tuple(prefix);return
        for x in range(max(prefix,default=-1)+2):yield from go(prefix+[x])
    yield from go([0])


class Interface:
    def __init__(self,recipe,producer,consumer):
        self.recipe=recipe;self.parent={};self.sorts={};self.constants={};self.facts=[];self.exports=[];self.inputs=[]
        def arg(side,rule,a):
            if 'slot' in a:
                key=(side,a['slot']);sort=rule['slots'][a['slot']]['sort']
            else:
                v=literal(a);key=('literal',v['sort'],v['value']);sort=dict(kind='i64',name=v['sort']);self.constants[key]=v['value']
            self.parent.setdefault(key,key);self.sorts[key]=(sort['kind'],sort['name'])
            return key
        p=recipe['rules'][producer];c=recipe['rules'][consumer]
        for atom in p['query']:
            fact=(atom['call']['table'],tuple(arg('p',p,a) for a in atom['args']))
            self.exports.append(fact);self.facts.append(fact)
        for op in p['effects']:
            kind=op['kind']
            if kind=='copy':self.union(arg('p',p,dict(slot=op['dst'])),arg('p',p,op['arg']))
            elif kind=='union':self.union(*(arg('p',p,a) for a in op['args']))
            elif kind in ('construct','set'):
                result=dict(slot=op['dst']) if kind=='construct' else op['value']
                fact=(op['call']['table'],tuple(arg('p',p,a) for a in [*op['args'],result]))
                self.exports.append(fact);self.facts.append(fact)
            else:raise ValueError('unsupported producer effect: '+kind)
        for atom in c['query']:
            fact=(atom['call']['table'],tuple(arg('c',c,a) for a in atom['args']))
            self.inputs.append(fact);self.facts.append(fact)
        if any(s[0] not in ('eq','i64') for s in self.sorts.values()):raise ValueError('unsupported interface sort')

    def root(self,x):
        while self.parent[x]!=x:x=self.parent[x]
        return x

    def union(self,a,b):
        a,b=self.root(a),self.root(b)
        if a==b:return
        if self.sorts[a]!=self.sorts[b]:raise ValueError('type contradiction')
        ca={v for k,v in self.constants.items() if self.root(k) in (a,b)}
        if len(ca)>1:raise ValueError('literal contradiction')
        self.parent[b]=a

    def connect(self,wiring):
        # -2 omits boundary support; it does not assert semantic absence.
        self.facts=list(self.exports)+[fact for fact,j in zip(self.inputs,wiring) if j!=-2]
        for i,j in enumerate(wiring):
            if j<0:continue
            name,values=self.inputs[i];other,args=self.exports[j]
            if name!=other or len(values)!=len(args):raise ValueError('invalid connection')
            for a,b in zip(values,args):self.union(a,b)

    def close(self):
        while True:
            changed=False;keys={}
            for name,args in self.facts:
                key=(name,tuple(self.root(a) for a in args[:-1]));result=self.root(args[-1])
                if key in keys and self.root(keys[key])!=result:
                    self.union(keys[key],result);changed=True
                else:keys[key]=result
            if not changed:return

    def snapshot(self):
        self.close();values={};serial=0
        used_constants=set(self.constants.values());next_scalar=0
        for key in self.parent:
            root=self.root(key)
            if root in values:continue
            kind,name=self.sorts[root];constants=[v for k,v in self.constants.items() if self.root(k)==root]
            if kind=='eq':value=dict(sort=name,eq=str(serial));serial+=1
            else:
                while next_scalar in used_constants:next_scalar+=1
                number=constants[0] if constants else next_scalar
                if not constants:used_constants.add(number);next_scalar+=1
                value=dict(sort=name,value=number)
            values[root]=value
        rows=[dict(table=name,values=[values[self.root(a)] for a in args],subsumed=False) for name,args in self.facts]
        return canonical_seed(self.recipe,rows)


def replay_case(recipe,case):
    """Validate a recorded representative without trusting its snapshot."""
    p,c=case['producer'],case['consumer']
    if type(p)is not int or type(c)is not int or not 0<=p<len(recipe['rules']) or not 0<=c<len(recipe['rules']):raise ValueError('invalid rule index')
    bound=Interface(recipe,p,c);wiring=case['wiring']
    if len(wiring)!=len(bound.inputs) or all(j<0 for j in wiring):raise ValueError('invalid wiring arity')
    if any(type(j)is not int or j < -2 or j>=len(bound.exports) for j in wiring):raise ValueError('invalid export index')
    bound.connect(wiring);bound.close();groups={}
    for key in bound.parent:
        root=bound.root(key);group=groups.setdefault(bound.sorts[root],[])
        if root not in group:group.append(root)
    parts=case['partition']
    if len(parts)!=len(groups):raise ValueError('partition sort count')
    for group,part in zip(groups.values(),parts):
        if len(part)!=len(group):raise ValueError('partition width')
        first={};largest=-1
        for var,label in zip(group,part):
            if type(label)is not int or not 0<=label<=largest+1:raise ValueError('invalid restricted growth partition')
            largest=max(largest,label)
            if label in first:bound.union(first[label],var)
            else:first[label]=var
    result=bound.snapshot()
    if result!=case['snapshot'] or digest(result)!=case['input_sha256']:raise ValueError('enumerated snapshot replay mismatch')
    return result


def enumerate_interfaces(recipe,max_classes=7,include_missing=False):
    from copy import deepcopy
    report=dict(wirings=0,contradictory_wirings=0,budget_exclusions=0,partitions=0,contradictory_partitions=0,unique_cases=0)
    cases=[]
    for p,c in itertools.product(range(len(recipe['rules'])),repeat=2):
        base=Interface(recipe,p,c)
        choices=[([-2,-1] if include_missing else [-1])+[j for j,(t,_) in enumerate(base.exports) if t==name] for name,_ in base.inputs]
        for wiring in itertools.product(*choices):
            if all(j<0 for j in wiring):continue
            report['wirings']+=1;bound=deepcopy(base)
            try:bound.connect(wiring);bound.close()
            except ValueError:report['contradictory_wirings']+=1;continue
            groups={}
            for key in bound.parent:
                root=bound.root(key)
                group=groups.setdefault(bound.sorts[root],[])
                if root not in group:group.append(root)
            if sum(map(len,groups.values()))>max_classes:
                report['budget_exclusions']+=1;continue
            roots=list(groups.values());seen=set()
            for parts in itertools.product(*(partitions(len(group)) for group in roots)):
                report['partitions']+=1;candidate=deepcopy(bound)
                try:
                    for group,part in zip(roots,parts):
                        first={}
                        for var,label in zip(group,part):
                            if label in first:candidate.union(first[label],var)
                            else:first[label]=var
                    snapshot=candidate.snapshot()
                except ValueError:report['contradictory_partitions']+=1;continue
                key=digest(snapshot)
                if key in seen:continue
                seen.add(key);cases.append(dict(producer=p,consumer=c,wiring=list(wiring),partition=[list(x) for x in parts],snapshot=snapshot,input_sha256=key))
    report['unique_cases']=len(cases)
    report['within_bound_complete']=report['budget_exclusions']==0
    return cases,report


def main():
    p=argparse.ArgumentParser();p.add_argument('recipe',type=Path);p.add_argument('output',type=Path);p.add_argument('--rules',default='0,1,2');p.add_argument('--max-classes',type=int,default=7);p.add_argument('--include-missing',action='store_true');a=p.parse_args()
    if a.max_classes<1:raise ValueError('positive bound required')
    source=json.loads(a.recipe.read_text());recipe=select_recipe(source.get('recipe',source),list(map(int,a.rules.split(','))))
    cases,report=enumerate_interfaces(recipe,a.max_classes,a.include_missing)
    a.output.mkdir(parents=True,exist_ok=False)
    (a.output/'cases.jsonl').write_text(''.join(json.dumps(c)+'\n' for c in cases))
    result=dict(scope='one completed producer / one consumer; consumer boundary support controlled by includes_missing_support; i64 equality only',max_classes=a.max_classes,includes_missing_support=a.include_missing,recipe=recipe,recipe_sha256=digest(recipe),counts=report,obligations=['No three-Cell or iterative interaction closure','No scalar arithmetic/ordering partition proof','No stage schedule or source-program reachability proof','Snapshots are completed-producer boundaries, not pre-RHS inputs','No ownership-retirement proof'])
    (a.output/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
