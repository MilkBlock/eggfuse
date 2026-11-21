"""Re-derive a strict returned-port program from the authoritative compiled Cell recipe."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path

class Refusal(ValueError):
    """This candidate's evidence or executable contract could not be established."""

def require(condition,reason):
    if not condition:raise Refusal(reason)

def sha(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

def integer(n):
    return type(n) is int and n>=0

def sort_key(s):
    require(isinstance(s,dict) and isinstance(s.get('name'),str) and isinstance(s.get('kind'),str),'invalid_sort')
    return s['name'],s['kind']

def checked_i(i,seq,why):
    require(integer(i) and i<len(seq),why)
    return seq[i]

class Recipe:
    def __init__(self,path):
        self.path=Path(path)
        data=self.path.read_bytes();self.file_sha=hashlib.sha256(data).hexdigest()
        obj=json.loads(data);ir=obj.get('recipe',{})
        require(obj.get('schema')=='eggfuse-cell-runtime/v1' and ir.get('schema')=='eggfuse-recipe/v1','unsupported_recipe')
        self.rules=ir['rules'];self.tables={t['name']:t for t in ir['tables']};self.templates=obj['templates']
        require(len(self.tables)==len(ir['tables']) and len(self.templates)==len(self.rules),'invalid_recipe_index')
        self.identities=[];self.index=defaultdict(list)
        for rid,r in enumerate(self.rules):
            # Source-local variable spellings are irrelevant; slot indices, data
            # dependencies, table declarations, sorts, and effects are semantic.
            names=set()
            for atom in [*r['query'],*r['effects']]:
                if 'table' in atom.get('call',{}):names.add(atom['call']['table'])
                if isinstance(atom.get('table'),str):names.add(atom['table'])
            declarations=[self.tables[n] for n in sorted(names)]
            key=sha([r['metadata'].get('source_set'),r['metadata'].get('seminaive'),
                     [(s['sort'],s['definition']) for s in r['slots']],r['query'],r['effects'],r['interface'],declarations])
            self.identities.append(key);self.index[key].append(rid)

    def rule(self,i):
        return checked_i(i,self.rules,'unknown_rule')

    def resolve(self,key):
        found=self.index.get(key,[])
        require(bool(found),'target_schema_absent')
        require(len(found)==1,'target_schema_ambiguous')
        return found[0]

    def actual_sort(self,arg,slots):
        if isinstance(arg,dict) and set(arg)=={'slot'}:
            return sort_key(checked_i(arg['slot'],slots,'invalid_source_slot')['sort'])
        if isinstance(arg,dict) and 'literal' in arg:
            return sort_key(arg.get('sort'))
        raise Refusal('unsupported_source_operand')

    def certify(self,producer,op,consumer,pivot):
        p,c=self.rule(producer),self.rule(consumer)
        require(integer(pivot) and pivot<len(c['query']),'unknown_lhs_pivot')
        effect=checked_i(op,p['effects'],'wrong_producer_operation')
        require(effect.get('kind')=='construct' and effect.get('op')=='let','not_a_returning_constructor')
        table=effect.get('call',{}).get('table');decl=self.tables.get(table)
        require(decl is not None and decl.get('kind')=='constructor','not_a_constructor_table')
        schema=decl.get('schema',[]);require(len(schema)>0,'empty_constructor_schema')
        actual=[*effect['args'],{'slot':effect.get('dst')}]
        require(len(actual)==len(schema) and all(self.actual_sort(a,p['slots'])==sort_key(s) for a,s in zip(actual,schema)),'producer_return_sort_mismatch')
        require(sort_key(effect.get('sort'))==sort_key(schema[-1]),'producer_result_sort_mismatch')
        frame=checked_i(producer,self.templates,'missing_frame_layout')
        require(frame['rule']==producer and op in frame['fact_operations'],'operation_has_no_physical_fact_port')
        atom=c['query'][pivot]
        require(atom.get('call')=={'table':table},'producer_consumer_table_mismatch')
        require(c['metadata'].get('seminaive') is True,'unsupported_nonseminaive_consumer')
        require(len(c['query'])==1 and pivot==0,'external_lhs_or_guard_not_implemented')
        args=atom.get('args',[])
        require(len(args)==len(schema),'consumer_port_arity_mismatch')
        require(all(isinstance(a,dict) and set(a)=={'slot'} and integer(a['slot']) for a in args),'literal_or_non_slot_guard')
        ordered=[a['slot'] for a in args]
        require(len(ordered)==len(set(ordered)),'alias_guard_requires_runtime_equality')
        require(all(self.actual_sort(a,c['slots'])==sort_key(s) for a,s in zip(args,schema)),'consumer_port_sort_mismatch')
        inputs=[i for i,s in enumerate(c['slots']) if s['definition']=='query']
        require(set(inputs)<=set(ordered),'independent_rhs_input')
        interface=c['interface']['rows']
        require(len(interface)==1 and interface[0]['atom']==pivot and interface[0]['table']==table and interface[0]['columns']==args,'consumer_interface_disagrees')
        # Native graph completion, union, merge and visibility remain source
        # effects. This proof licenses exactly a source binding at release.
        return dict(producer_rule=producer,producer_op=op,consumer_rule=consumer,pivot=pivot,
                    producer_schema=self.identities[producer],consumer_schema=self.identities[consumer],
                    source_set=c['metadata']['source_set'],table=table,sorts=[list(sort_key(s)) for s in schema],
                    producer_columns=actual,consumer_slots=ordered,
                    rhs_projections=[[slot,ordered.index(slot)] for slot in inputs])

def capture_fingerprint(rule):
    # This is the capture ledger's exact identity, distinct from the portable
    # names-independent schema used for donor→target compilation.
    raw=[rule[k] for k in ('metadata','query','effects','slots','interface')]
    return hashlib.sha256(json.dumps(raw,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def verify_producer_inputs(rule,observed):
    roles=set();bound=set()
    for row in observed:
        atom=row.get('atom');a=checked_i(atom,rule['query'],'unknown_named_parent_role')
        require(atom not in roles and a['call']=={'table':row.get('table')},'named_parent_role_mismatch')
        named=row.get('named')
        if named is None:continue
        require(isinstance(named,dict) and named.get('atom')==atom and isinstance(named.get('row'),dict) and integer(named.get('version')),'unnamed_parent')
        w=named['row']
        if set(w)=={'Fact'}:require(all(integer(w['Fact'].get(k)) for k in ('cell','op')),'invalid_named_parent_reference')
        elif set(w)=={'Function'}:require(integer(w['Function']),'invalid_named_parent_reference')
        else:raise Refusal('invalid_named_parent_reference')
        require(len(row.get('values',[]))==len(a['args']),'incomplete_named_parent')
        bound.update(x['slot'] for x in a['args'] if 'slot' in x);roles.add(atom)
    require(bool(roles),'no_explicit_root_parent')
    done=set(roles);steps=[]
    while len(done)<len(rule['query']):
        take=None
        for i,a in enumerate(rule['query']):
            args=a.get('args',[])
            if i not in done and args and all('literal' in x or x.get('slot') in bound for x in args[:-1]):
                take=i;break
        require(take is not None,'producer_needs_another_independent_parent')
        a=rule['query'][take];answer=a['args'][-1]
        if 'slot' in answer:bound.add(answer['slot'])
        steps.append([take,a['call']]);done.add(take)
    return dict(explicit_roles=sorted(roles),deterministic_checks=steps)

def verify_origin(recipe,o):
    require(isinstance(o,dict),'missing_donor_origin')
    producer=o['producer'];consumer=o['consumer'];pi=producer['rule'];ci=consumer['rule'];op=o['producer_op'];atom=o['consumer_atom'];f=o['original_fact']
    for event in (producer,consumer):
        rule=recipe.rule(event['rule']);meta=rule['metadata']
        require(event.get('fingerprint')==capture_fingerprint(rule) and event.get('source_name')==meta['name'] and event.get('ruleset')==meta['source_set'],'foreign_donor_rule')
        require(all(integer(event.get(k)) for k in ('serial','ordinal','epoch')),'invalid_donor_coordinates')
    require(producer['ordinal']<consumer['ordinal'] and producer['serial']!=consumer['serial'] and producer['epoch']<consumer['epoch'] and o.get('relative_runs')==consumer['epoch']-producer['epoch'],'invalid_run_order')
    proof=recipe.certify(pi,op,ci,atom)
    require(integer(f) and f&0xffffffff==op,'wrong_producer_operation')
    birth=o['birth_event']
    require(len(birth)>=6 and birth[0]=='birth' and birth[4]==f and len(birth[5])==2 and birth[5][1]==pi,'foreign_birth')
    tables=list(recipe.tables);require(checked_i(birth[1],tables,'unknown_birth_table')==proof['table'],'foreign_birth_table')
    require(isinstance(birth[2],list) and len(birth[2])+1==len(proof['consumer_slots']),'wrong_birth_arity')
    ref={'Fact':{'cell':f>>32,'op':f&0xffffffff}}
    rows=[r for r in consumer['rows'] if r['atom']==atom]
    require(len(rows)==1 and rows[0].get('table')==proof['table'] and rows[0].get('named')=={'atom':atom,'row':ref,'version':o['original_version']},'consumer_did_not_read_named_return')
    require(o['original_version']==producer['epoch'],'producer_return_version_mismatch')
    root=verify_producer_inputs(recipe.rule(pi),producer['rows'])
    return proof,root
