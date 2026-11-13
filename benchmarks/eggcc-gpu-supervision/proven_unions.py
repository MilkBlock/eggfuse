"""Derive conservative input-port union wiring from full Cell definitions.

Query constructor witnesses may discharge identical RHS constructions. Mutable
reads and effects that can fail or alter visibility are barriers. This is an
offline proof-coverage audit; it does not replace runtime checks or execute GPU
graph mutation. Post-Run observations are validation targets, never premises.
"""
import argparse
from collections import Counter
import json
import time
from pathlib import Path


def compile_unions(rule, constructors):
    env={i:('input',i) for i,s in enumerate(rule['slots']) if s['definition']=='query'}

    def arg(a):
        if 'slot' in a:return env.get(a['slot'])
        if 'literal' in a:return ('literal',json.dumps(a,sort_keys=True))
        return None

    facts={}
    for atom in rule['query']:
        table=atom['call'].get('table')
        if table not in constructors:continue
        operands=[arg(a) for a in atom['args']]
        if all(a is not None for a in operands):facts[table,tuple(operands[:-1])]=operands[-1]
    barrier=None;unions=[];uncovered=[]
    for index,op in enumerate(rule['effects']):
        kind=op['kind']
        if kind=='copy':env[op['dst']]=arg(op['arg'])
        elif kind=='construct':
            table=op['call']['table'];operands=tuple(arg(a) for a in op['args'])
            if table not in constructors:barrier=barrier or 'mutable table read'
            env[op['dst']]=facts.get((table,operands)) if None not in operands else None
        elif kind=='union':
            operands=[arg(a) for a in op['args']]
            if barrier is None and all(a is not None and a[0]=='input' for a in operands):
                a,b=[a[1] for a in operands]
                if rule['slots'][a]['sort']!=rule['slots'][b]['sort']:raise ValueError('union sort mismatch')
                unions.append(dict(operation=index,slots=[a,b]))
            else:uncovered.append(dict(operation=index,reason=barrier or 'unresolved returned constructor port'))
        else:
            # Primitive evaluation can fail; set can invoke an ordered merge.
            # Do not move a later union in front of either operation.
            barrier=barrier or kind
            if 'dst' in op:env[op['dst']]=None
    return dict(unions=unions,uncovered=uncovered)


class Closure:
    def __init__(self):self.parent={}
    def find(self,x):
        while x in self.parent:x=self.parent[x]
        return x
    def union(self,a,b):
        a,b=self.find(a),self.find(b)
        if a==b:return False
        self.parent[b]=a
        return True


def constructor_facts(recipe, rows, constructors):
    facts=set()
    for binding in rows:
        ports={p['slot']:p for p in binding['eq_ports']}
        values={v['slot']:v['value'] for v in binding['values']}
        def value(arg):
            if 'slot' in arg:
                slot=arg['slot']
                if slot in ports:
                    p=ports[slot];return ('eq',p['sort'],p['before'])
                raw=values[slot]
            else:raw=dict(sort=arg['sort']['name'],value=arg['literal'])
            # Nested collections may themselves contain Eq references. They
            # need typed recursive canonicalization, not a JSON identity guess.
            if not isinstance(raw.get('value'),(int,float,bool,str)):
                return None
            return ('scalar',json.dumps(raw,sort_keys=True))
        for atom in recipe['rules'][binding['rule']]['query']:
            table=atom['call'].get('table')
            if table not in constructors:continue
            args=tuple(value(a) for a in atom['args'])
            if None not in args and args[-1][0]=='eq':facts.add((table,args[:-1],args[-1]))
    return sorted(facts)


def complete_known_congruence(closure,facts):
    passes=checks=merges=0
    while True:
        passes+=1;index={};changed=False
        for table,args,result in facts:
            key=(table,tuple(('eq',)+closure.find((a[1],a[2])) if a[0]=='eq' else a for a in args))
            checks+=1
            result=(result[1],result[2])
            if key in index:
                if closure.union(index[key],result):merges+=1;changed=True
            else:index[key]=result
        if not changed:return dict(congruence_passes=passes,constructor_key_checks=checks,constructor_result_merges=merges)


def symbolic_prefix(recipe, rows, constructors, closure, run_ordinal=0):
    facts=[];counts=Counter()
    for instance,binding in enumerate(rows):
        ports={p['slot']:p for p in binding['eq_ports']}
        env={v['slot']:('scalar',json.dumps(v['value'],sort_keys=True)) for v in binding['values'] if 'eq' not in v['value']}
        env.update({slot:('eq',p['sort'],p['before']) for slot,p in ports.items()})
        def arg(a):
            if 'slot' in a:return env[a['slot']]
            return ('scalar',json.dumps(dict(sort=a['sort']['name'],value=a['literal']),sort_keys=True))
        for index,op in enumerate(recipe['rules'][binding['rule']]['effects']):
            kind=op['kind']
            if kind=='copy':env[op['dst']]=arg(op['arg'])
            elif kind=='construct' and op['call']['table'] in constructors:
                result=('eq',op['sort']['name'],('rhs',run_ordinal,instance,index))
                facts.append((op['call']['table'],tuple(arg(a) for a in op['args']),result))
                env[op['dst']]=result;counts['symbolic_constructor_operations']+=1
            elif kind=='set' and op['call']['table'] in constructors:
                result=arg(op['value'])
                if result[0]!='eq':raise ValueError('constructor assignment must return Eq')
                facts.append((op['call']['table'],tuple(arg(a) for a in op['args']),result))
                counts['symbolic_constructor_assignments']+=1
            elif kind=='union':
                a,b=[arg(a) for a in op['args']]
                if a[0]!='eq' or b[0]!='eq' or a[1]!=b[1]:raise ValueError('invalid symbolic union')
                closure.union((a[1],a[2]),(b[1],b[2]));counts['symbolic_union_operations']+=1
            else:
                counts['prefix_barrier_'+kind]+=1;break
    return facts,counts


def audit(trace, history=False):
    started=time.perf_counter()
    recipe=trace['recipe'];rules=recipe['rules']
    constructors={t['name'] for t in recipe['tables'] if t['kind']=='constructor'}
    plans=[compile_unions(r,constructors) for r in rules]
    totals=Counter();uncovered=Counter();by_set={};examples=[]
    retained=[];prior=Closure()
    for r,plan in zip(rules,plans):
        for item in plan['uncovered']:uncovered[item['reason']]+=1
    for run in trace['runs']:
        rows=run['audit']['bindings'];closure=Closure();counts=Counter()
        # This initial proof contract excludes all visibility-changing Runs.
        unsafe=any(op['kind'] in ('subsume','delete') for b in rows for op in rules[b['rule']]['effects'])
        if unsafe:
            retained=[];prior=Closure()
        elif history:
            closure.parent=prior.parent.copy()
            for b in rows:
                for port in b['eq_ports']:
                    closure.union((port['sort'],port['identity']),(port['sort'],port['before']))
        for b in rows:
            ports={p['slot']:p for p in b['eq_ports']}
            for edge in plans[b['rule']]['unions']:
                counts['compiled_union_instances']+=1
                if unsafe:
                    counts['visibility_fenced_union_instances']+=1;continue
                a,c=[ports[s] for s in edge['slots']]
                if a['sort']!=c['sort']:raise ValueError('port sort mismatch')
                closure.union((a['sort'],a['before']),(c['sort'],c['before']))
                counts['admitted_union_instances']+=1
                if a['after']!=c['after']:
                    raise ValueError(f"compiled union absent after Run {run['ordinal']}")
        direct_parent=closure.parent.copy()
        current=[] if unsafe else constructor_facts(recipe,rows,constructors)
        counts['known_constructor_facts']=len(current)
        facts=retained+current if history else current
        counts['history_constructor_facts_read']=len(retained) if history else 0
        counts.update(complete_known_congruence(closure,facts))
        query_parent=closure.parent.copy()
        if not unsafe:
            generated,generated_counts=symbolic_prefix(recipe,rows,constructors,closure,run['ordinal'])
            counts.update(generated_counts)
            counts.update(complete_known_congruence(closure,facts+generated))
        if history and not unsafe:
            retained=list(dict.fromkeys(facts+generated));prior.parent=closure.parent.copy()
            counts['history_fact_peak']=len(retained)
        query_only=Closure();query_only.parent=query_parent
        direct=Closure();direct.parent=direct_parent
        for index,b in enumerate(rows):
            ports=b['eq_ports']
            for i,a in enumerate(ports):
                for c in ports[:i]:
                    if a['sort']!=c['sort'] or a['before']==c['before']:continue
                    counts['candidate_pairs']+=1
                    truth=a['after']==c['after']
                    known=closure.find((a['sort'],a['before']))==closure.find((c['sort'],c['before']))
                    counts['actual_new_eq_pairs']+=truth
                    counts['direct_union_closure_pairs']+=direct.find((a['sort'],a['before']))==direct.find((c['sort'],c['before']))
                    counts['query_congruence_pairs']+=query_only.find((a['sort'],a['before']))==query_only.find((c['sort'],c['before']))
                    counts['proven_new_eq_pairs']+=known
                    counts['false_proven_pairs']+=known and not truth
                    counts['residual_new_eq_pairs']+=truth and not known
                    if truth and not known and len(examples)<12:
                        examples.append(dict(run=run['ordinal'],binding=index,rule=b['rule'],slots=[a['slot'],c['slot']],visibility_fenced=unsafe))
        peak=max(totals.get('history_fact_peak',0),counts.pop('history_fact_peak',0))
        totals.update(counts)
        totals['history_fact_peak']=peak
        name=trace['steps'][run['ordinal']-1]['ruleset']
        by_set.setdefault(name,Counter()).update(counts)
    if totals['false_proven_pairs']:raise ValueError('proof contract contradicted by runtime')
    return dict(scope='Compiled constructor-witness and input-port union coverage; CPU closure audit, no GPU takeover',
        program_sha256=trace['program_sha256'],rules=len(plans),cross_run_history=history,
        cpu_audit_seconds=time.perf_counter()-started,
        static_union_edges=sum(len(p['unions']) for p in plans),
        static_uncovered_reasons=dict(uncovered),totals=dict(totals),
        per_ruleset={k:dict(v) for k,v in by_set.items()},residual_examples=examples,
        gpu_completed_bindings=0,runtime_operations_removed=0),plans


def main():
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    trace=json.loads(a.trace.read_text())
    if not trace.get('relations'):raise ValueError('requires actual pre/post Run relations')
    local,plans=audit(trace)
    report,_=audit(trace,history=True)
    report['without_history_totals']=local['totals']
    report['without_history_cpu_seconds']=local['cpu_audit_seconds']
    a.output.mkdir(parents=True,exist_ok=True)
    (a.output/'union-plans.json').write_text(json.dumps(plans,indent=2)+'\n')
    (a.output/'union-results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('per_ruleset','residual_examples')},indent=2))


if __name__=='__main__':main()
