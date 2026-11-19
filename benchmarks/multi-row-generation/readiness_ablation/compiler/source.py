"""Offline source scheduling and real Cell CPU boundary audit for release/readiness."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
PRODUCERS = ('P0', 'P1', 'U')
SCHEDULE = ('wave0', 'wave1', 'wave2', 'finish')
INPUTS = tuple('In' + relation for relation in PRODUCERS)
TABLES = INPUTS + PRODUCERS + ('C', 'V')


def check(ok, reason):
    if not ok:
        raise ValueError(reason)


def digest(data):
    return sha256(data).hexdigest()


def canonical_hash(value):
    return digest(json.dumps(value, sort_keys=True, separators=(',', ':')).encode())


def normalize(events):
    entries = []
    for wave, table, key, value in events:
        if wave not in range(3) or table not in PRODUCERS or any(type(v) is not int for v in (wave,key,value)):
            raise ValueError('expected (0..2, P0|P1|U, integer key, integer value)')
        entries.append((wave,table,key,value))
    return sorted(set(entries))


def request(name, events):
    # Only the real offline compiler receives In* facts from future waves.
    schedule = '(run-schedule (seq ' + ' '.join(f'(run {s})' for s in SCHEDULE) + '))'
    initial = [f'(In{table} {wave} {key} {value})' for wave,table,key,value in normalize(events)]
    body = (HERE/'rules.egg').read_text().rstrip()
    return dict(id=name,source='\n'.join([body,*initial,schedule,'']),include_program=True, include_bindings=True)


def read_graph(export):
    tables = {name: {} for name in TABLES}
    for row in export['rows']:
        name = row['table']
        check(name in tables and not row['subsumed'], 'unsupported relation or hidden row')
        *args,result = row['values']
        check(all(v['sort']=='i64' and type(v['value']) is int for v in args) and 'eq' in result,
              'malformed typed relation record')
        fields = tuple(v['value'] for v in args)
        check(fields not in tables[name], 'duplicate physical fact key')
        tables[name][fields] = (result['sort'],result['eq'])
    return tables


def lower(recipe):
    """Use compiled slot identities for equality and output order; preserve literal-wave guards."""
    result = []
    for rid,rule in enumerate(recipe['rules']):
        check(len(rule['effects'])==1, 'only a single relation publication is supported')
        effect, = rule['effects']
        check(effect['op']=='let' and effect['kind']=='construct', 'unsupported source effect')
        lhs=[]; known={}; guards=[]
        for index,atom in enumerate(rule['query']):
            lhs.append(atom['call']['table'])
            for column,arg in enumerate(atom['args'][:-1]):
                pos=[index,column]
                if 'literal' in arg:
                    check(arg['sort']['kind']=='i64','unsupported guard')
                    guards.append([pos,['literal',arg['literal']]])
                else:
                    slot=arg['slot'];check(rule['slots'][slot]['sort']['kind']=='i64','invalid slot type')
                    if slot in known:guards.append([known[slot],pos])
                    else:known[slot]=pos
        routes=[known[arg['slot']] for arg in effect['args']]
        result.append(dict(rule=rid,ruleset=rule['metadata']['source_set'],inputs=lhs,checks=guards,
                           table=effect['call']['table'],outputs=routes))
    return result


def expected_outputs(tables):
    c={(k,x,y) for k,x in tables['P0'] for l,y in tables['P1'] if k==l}
    return dict(C=c,V=set(tables['U']))


def active_inputs(rule,vals,before):
    source_rows=[]
    for atom in rule['query']:
        table=atom['call']['table'];*args,ret=atom['args']
        row=tuple(a['literal'] if 'literal' in a else vals[a['slot']]['value'] for a in args)
        physical=vals[ret['slot']]
        check(before[table].get(row)==(physical['sort'],physical['eq']),'binding used an invisible or foreign source fact')
        source_rows.append(row)
    return source_rows


def verify(record,events,keep_rows=False):
    events=normalize(events);recipe=record['compiled_program']['recipe'];plans=lower(recipe)
    check(len(record['steps'])==len(record['boundaries'])==len(record['binding_audit'])==4,'unexpected number of source Runs')
    before=read_graph(record['initial']);published={k:set() for k in PRODUCERS+('C','V')}
    for name in PRODUCERS:
        check(set(before['In'+name])=={(w,k,v) for w,t,k,v in events if t==name},'initial input differs')
    check(all(not before[name] for name in published),'early source publication')
    def anchors(graph):return sorted((a['sort'],a['old'],a['now']) for a in graph['anchors'])
    initial_anchors=anchors(record['initial'])
    logs=[];first_publication={};final_witnesses={'C':{},'V':{}}
    for wave,name in enumerate(SCHEDULE):
        ordinal=wave+1;step=record['steps'][wave];boundary=record['boundaries'][wave];audit=record['binding_audit'][wave]
        check((step['ruleset'],audit['ruleset'],step['ordinal'],boundary['ordinal'])==(name,name,ordinal,ordinal),'unexpected source schedule')
        after=read_graph(boundary['graph']);action_rows=[];bindings=[]
        check(anchors(boundary['graph'])==initial_anchors,'source anchor was changed')
        for b in audit['bindings']:
            i=b['rule'];rule=recipe['rules'][i];plan=plans[i];check(plan['ruleset']==name,'wrong scheduled RHS')
            vals={e['slot']:e['value'] for e in b['values']};args=active_inputs(rule,vals,before)
            row=tuple(args[at][col] for at,col in plan['outputs'])
            action_rows.append((plan['table'],row));bindings.append([i,args,[plan['table'],row]])
            if name=='finish':
                provenance=[(PRODUCERS.index(table)+1,*arg,first_publication[table,arg]) for table,arg in zip(plan['inputs'],args)]
                check(row[0] not in final_witnesses[plan['table']], 'single-valued panel repeated a result key')
                final_witnesses[plan['table']][row[0]]=provenance
        if wave<3:
            wanted=[(t,(k,v)) for w,t,k,v in events if w==wave]
            for table,row in wanted:published[table].add(row)
        else:
            out=expected_outputs(published);wanted=[(table,row) for table,rows in out.items() for row in rows];published.update(out)
        check(Counter(wanted)==Counter(action_rows), 'RHS inputs or projected outputs disagree with source')
        check(step['logical_matches']==len(bindings) and step['executed_bindings']==len(bindings),'logical/executed count mismatch')
        delta=[]
        for table in TABLES:
            check(all(after[table].get(row)==ref for row,ref in before[table].items()),'previous record retired or changed')
            if table in published:check(set(after[table])==published[table],'published relation differs')
            else:check(after[table]==before[table],'unexpected modification of preloaded inputs')
            delta.extend((table,row) for row in after[table].keys()-before[table].keys())
        check(set(delta)=={(t,r) for t,r in wanted if r not in before[t]},'effective visible delta differs')
        if wave<3:
            for table,row in delta:first_publication[table,row]=wave
        observed=dict(ordinal=ordinal,ruleset=name,logical_matches=step['logical_matches'],executed_bindings=step['executed_bindings'],
                      actual_publications=len(delta),bindings_sha256=canonical_hash(sorted(bindings)),
                      rhs_outputs_sha256=canonical_hash(sorted(action_rows)),delta_sha256=canonical_hash(sorted(delta)),
                      visible_public_sha256=canonical_hash({table:sorted(after[table]) for table in published}))
        ready={k:sorted(v) for k,v in expected_outputs(published).items()}
        observed['ready_sha256']=canonical_hash(ready)
        if keep_rows:observed.update(actual_rhs=sorted(bindings),published=sorted(delta),ready=ready)
        logs.append(observed);before=after
    check(before==read_graph(record['final']) and anchors(record['final'])==initial_anchors,'final graph differs from final Run boundary')
    final={name:sorted(rows) for name,rows in published.items()};result=dict(id=record['id'],source_sha256=record['source_sha256'],
                  program_sha256=record['program_sha256'],runs=logs,final_semantic_sha256=canonical_hash(final),
                  finish_witnesses_sha256=canonical_hash(final_witnesses),
                  final_physical_sha256=canonical_hash([sorted((name, fields,*ref) for name,rows in before.items() for fields,ref in rows.items()),initial_anchors]))
    if keep_rows:result.update(final_relations=final,finish_witnesses=final_witnesses)
    return result,plans


def run_batch(binary, fixtures, keep_rows=False):
    """fixtures is a dict of case_id -> event tuples, including empty waves."""
    results=[];plan=None
    with tempfile.TemporaryDirectory() as work:
        work=Path(work);inp=work/'request.json';out=work/'runtime.json';names=list(fixtures)
        for start in range(0,len(names),16):
            chunk=names[start:start+16];inp.write_text(json.dumps({'cases':[request(name,fixtures[name]) for name in chunk]}))
            subprocess.run([binary,inp,out],check=True)
            records=json.loads(out.read_text())['cases'];check([c['id'] for c in records]==chunk,'missing or reordered runtime output')
            for c in records:
                report,compiled=verify(c,fixtures[c['id']],keep_rows)
                if plan is None:plan=compiled
                check(plan==compiled,'fixtures changed the executable recipes')
                results.append(report)
    return results,plan


def verify_examples(records):
    cases={r['id']:r for r in records}
    delayed,absent=cases['delayed'],cases['absent']
    for i in (0,1):
        check(delayed['runs'][i]['published']==absent['runs'][i]['published'], 'counterfactual prefix differs')
        check(delayed['runs'][i]['ready']==absent['runs'][i]['ready'], 'prefix already exposes delay')
    ckey=(0,5,5)
    check(ckey in delayed['final_relations']['C'] and ckey not in absent['final_relations']['C'], 'expected delayed conjunction')
    check(delayed['final_relations']['V']==absent['final_relations']['V'], 'unrelated consumer was changed')
    check((2,1) in delayed['runs'][0]['ready']['V'], 'early unrelated V obligation lost')
    reversed_arrival=cases['reversed-arrival']
    check(reversed_arrival['final_relations']==delayed['final_relations'],'arrival order changed final public relations')
    check(reversed_arrival['runs'][0]['published']!=delayed['runs'][0]['published'], 'missing arrival-order intervention')
    duplicate=cases['duplicate-publication']['runs'][1]
    check(duplicate['logical_matches']==duplicate['executed_bindings']==1 and duplicate['actual_publications']==0, 'duplicate publication mischarged as effective write')
    return dict(common_observable_prefix_waves=2, delayed_only_c=ckey, unchanged_v=delayed['final_relations']['V'],
                repeated_binding_count=duplicate['executed_bindings'], repeated_new_fact_count=duplicate['actual_publications'])


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('executable',type=Path);args=parser.parse_args()
    examples=json.loads((HERE/'witnesses.json').read_text());records,rules=run_batch(args.executable.resolve(),examples,True)
    paired=verify_examples(records)
    (HERE/'witness-audit.json').write_text(json.dumps(dict(cases=records,paired=paired),indent=2)+'\n')
    (HERE/'plan.json').write_text(json.dumps(dict(schema='eggfuse.readiness-wave/v1',schedule=SCHEDULE,rules=rules),indent=2)+'\n')
    print([(r['id'],[s['actual_publications'] for s in r['runs']]) for r in records])
