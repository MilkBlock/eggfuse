"""Validate native positive exports and re-identify an observed returned constructor in them."""
import json
import re
from pathlib import Path
from runpy import run_path
s=run_path(str(Path(__file__).with_name('source_proof.py')))
require=s['require'];Refusal=s['Refusal'];integer=s['integer'];checked_i=s['checked_i']

def forms(text):
    # Preserve string literal syntax; egglog rule names may contain newlines.
    tok=re.compile(r'\s+|;[^\n]*|"(?:\\.|[^"\\])*"|[()]|[^()\s;" ]+')
    stack=[[]];pos=0
    for m in tok.finditer(text):
        require(m.start()==pos,'unsupported_native_source_token');pos=m.end();v=m.group()
        if v.isspace() or v.startswith(';'):continue
        if v=='(':
            group=[];stack[-1].append(group);stack.append(group)
        elif v==')':
            require(len(stack)>1,'unbalanced_native_source');stack.pop()
        else:stack[-1].append(v)
    require(pos==len(text) and len(stack)==1,'unbalanced_native_source')
    return stack[0]

def one(text):
    f=forms(text);require(len(f)==1,'expected_one_source_form');return f[0]

def rule_ast(form):
    require(isinstance(form,list) and form and form[0]=='rule','unsupported_source_rule_form')
    out=[];i=0
    while i<len(form):
        if form[i]==':name':i+=2
        else:out.append(form[i]);i+=1
    return out

def equivalent(expected,body):
    if expected[0]=='rule':return rule_ast(expected)==rule_ast(body)
    if expected[0]!='rewrite' or len(expected)!=5 or expected[3]!=':ruleset':return False
    v=rule_ast(body)
    if len(v)!=5 or v[3:]!=expected[3:] or len(v[1])!=1 or len(v[2])!=1:return False
    lhs,rhs=v[1][0],v[2][0]
    return len(lhs)==3 and len(rhs)==3 and lhs[0]=='=' and rhs[0]=='union' and lhs[1]==rhs[1] and lhs[2]==expected[1] and rhs[2]==expected[2]

class Graph:
    def __init__(self,value):
        require(value.get('version')==2 and isinstance(value.get('scope'),dict),'unsupported_native_graph')
        self.scope=value['scope'];require(self.scope.get('observation_only') is not True and value.get('observation_only') is not True,'observation_only_graph');require(self.scope.get('semantics')=='positive-constructor-equality/v1','uncertified_native_semantics')
        self.values=value['values'];self.ports=value['ports'];self.raw=value['rows'];self.rows={}
        self.tables={c['name']:c for c in self.scope['constructors']}
        for row in self.raw:
            key=(row['op'],tuple(row['args']));out=row['result']
            require(all(integer(x) and x<len(self.values) for x in [*row['args'],out]),'invalid_graph_class')
            require(key not in self.rows or self.rows[key]==out,'nonfunctional_native_graph')
            self.rows[key]=out
            if row['op'] in self.tables:
                decl=self.tables[row['op']]
                require(len(row['args'])==len(decl['types']) and all(self.values[x]['sort']==t for x,t in zip(row['args'],decl['types'])),'ill_typed_native_row')
                if 'output' in decl:require(self.values[out]['sort']==decl['output'],'ill_typed_native_result')
        require(all(integer(v) and v<len(self.values) for v in self.ports.values()),'invalid_named_class')
    def literal(self,term,sort):
        found=[i for i,v in enumerate(self.values) if v['sort']==sort and v.get('literal')==term]
        require(len(found)==1,'native_literal_not_unique');return found[0]
    def term(self,term,sort):
        if isinstance(term,str):return self.literal(term,sort)
        require(isinstance(term,list) and term and isinstance(term[0],str),'invalid_ground_term')
        decl=self.tables.get(term[0]);require(decl is not None and len(term)==len(decl['types'])+1,'ground_term_foreign_constructor')
        args=tuple(self.term(x,t) for x,t in zip(term[1:],decl['types']))
        result=self.rows.get((term[0],args));require(result is not None and self.values[result]['sort']==sort,'ground_term_absent_from_native_graph')
        return result

def bind_seed(g,profile,origin,rule,declarations):
    env={}
    for row in profile['root_rows']:
        a=row['atom'];atom=checked_i(a,rule['query'],'invalid_seed_atom')
        require(atom.get('call')=={'table':row['table']} and row in origin['producer']['rows'],'foreign_donor_seed_row')
        args=atom['args'];require(len(row['values'])==len(args) and len(row['terms'])+1==len(args),'unsupported_native_seed_shape')
        ports=[]
        for i,arg in enumerate(args):
            label='input_'+str(a)+(('_c'+str(i)) if i<len(args)-1 else '')
            require(profile['root_ports'].get(label)==row['values'][i] and label in g.ports,'foreign_native_input_port')
            c=g.ports[label];ports.append(c)
            if i<len(args)-1:
                raw=one(row['terms'][i])
                require(declarations.get(label)==raw,'foreign_grounded_entry')
                require(g.term(raw,g.values[c]['sort'])==c,'foreign_grounded_class')
            if 'slot' in arg:
                require(env.get(arg['slot'],c)==c,'native_input_alias_mismatch');env[arg['slot']]=c
        require(declarations.get('input_'+str(a))==[row['table'],*['input_'+str(a)+'_c'+str(i)for i in range(len(args)-1)]],'foreign_native_input_row_source')
        require(g.rows.get((row['table'],tuple(ports[:-1])))==ports[-1],'foreign_native_input_row')
    return env

def operand(g,env,arg):
    if 'slot' in arg:return env.get(arg['slot'])
    if 'literal' in arg:
        raw=json.dumps(arg['literal'],ensure_ascii=False,separators=(',',':'))
        try:return g.literal(raw,arg['sort']['name'])
        except Refusal:return None
    return None

def native_return(g,env,rule,op):
    # Evaluate only deterministic equalities/constructor incidences. An opaque
    # unmatched premise cannot be supplied by a coincidental terminal class.
    for _ in range(len(rule['query'])+1):
        old=len(env)
        for a in rule['query']:
            if 'table' not in a['call'] or not a['args']:continue
            key=tuple(operand(g,env,x)for x in a['args'][:-1]);out=a['args'][-1]
            if None not in key and 'slot' in out:
                value=g.rows.get((a['call']['table'],key))
                if value is not None:
                    require(env.get(out['slot'],value)==value,'native_query_binding_conflict');env[out['slot']]=value
        if len(env)==old:break
    for i,e in enumerate(rule['effects'][:op+1]):
        if e['op']=='copy':
            v=operand(g,env,e['arg'])
            if v is not None:env[e['dst']]=v
        if e.get('op')!='let' or 'table' not in e.get('call',{}):continue
        t=e['call']['table'];args=tuple(operand(g,env,x)for x in e['args'])
        value=None if None in args else g.rows.get((t,args))
        if i==op:return t,args,value
        if value is not None:env[e['dst']]=value
    raise Refusal('unrecognized_producer_return')

def check_native(recipe,origin,profile,entry,r,raw0,raw1,h,gate,proof, *, derived=False):
    require(profile.get('scope_mode') in (('full','augmented') if derived else ('full',)),'incomplete_native_pair_scope')
    require(gate.get('schema')=='eggfuse-ripsat-native-acceptance/v1' and gate.get('accepted') is True,'native_export_not_accepted')
    cut=r.get('ripen',{});state=r.get('saturated_rule_composition',{})
    require(cut.get('state')=='Saturated' and cut.get('updated') is False and r.get('native_stop_reason') is None and r.get('checks')=='passed','stopped_or_unchecked_native_run')
    require(state.get('status')=='exported' and gate.get('export_status')=='exported' and gate.get('ripen_state')=='Saturated','observation_only_export')
    require(r.get('source_text')==entry,'foreign_report_source')
    require(r.get('internal_history') is True and h.get('schema')=='eggfuse-ripsat-native-history/v1','missing_local_history')
    records=h['records'];require(len(records)>0 and gate.get('records')==len(records) and r.get('imported_applies')==len(records),'native_history_count_mismatch')
    require(h['boundaries'] and h['boundaries'][-1]['ripen']['state']=='Saturated' and h['boundaries'][-1]['end']==len(records),'unfinished_native_history')
    initial=Graph(raw0);final=Graph(raw1)
    require(state.get('facts')==len(final.raw) and state.get('values')==len(final.values),'foreign_graph_counts')
    require(initial.scope==final.scope,'foreign_graph_scope')
    code=forms(entry);decls={v[1]:v[2] for v in code if isinstance(v,list) and len(v)==3 and v[0]=='let'}
    rules=[rule_ast(v)for v in code if isinstance(v,list) and v and v[0]=='rule']
    for role in ('producer','consumer'):
        event=origin[role];expected=one(event['source_name'])
        bodies=[rule_ast(one(x['text']))for x in h['rules'] if x['name']==event['source_name'] and x['ruleset']==event['ruleset']]
        require(any(x in rules and equivalent(expected,x) for x in bodies),'foreign_local_history_rule')
    p=recipe.rule(proof['producer_rule']);c=recipe.rule(proof['consumer_rule']);t=proof['table']
    found=[]
    for i,rec in enumerate(records):
        require(integer(rec['id']) and (i==0 or rec['id']>records[i-1]['id']) and all(integer(j) and j<i for j in rec['parents']),'invalid_history_parent')
        hr=checked_i(rec['rule'],h['rules'],'unknown_history_rule')
        if hr['name']!=origin['producer']['source_name']:continue
        if any(checked_i(j,h['tokens'],'unknown_output_token').get('sort')=='Fact:'+t for j in rec['produced']):found.append(i)
    require(bool(found),'history_did_not_produce_return_table')
    e0=bind_seed(initial,profile,origin,p,decls);e1=bind_seed(final,profile,origin,p,decls)
    _,before,bval=native_return(initial,dict(e0),p,proof['producer_op']);_,args,val=native_return(final,dict(e1),p,proof['producer_op'])
    require(None not in args and val is not None,'return_incidence_missing')
    alternatives=[i for i,e in enumerate(p['effects']) if e.get('op')=='let' and e.get('call')=={'table':t}]
    exact_ops=[i for i in alternatives if native_return(final,dict(e1),p,i)==(t,args,val)]
    require(exact_ops==[proof['producer_op']],'ambiguous_history_producer_operation')
    transport={}
    for label,c0 in initial.ports.items():
        if label in final.ports:
            c1=final.ports[label]
            require(transport.get(c0,c1)==c1,'inconsistent_seed_transport')
            transport[c0]=c1
    distinct_initial=all(any(a in transport and transport[a]!=actual for a,actual in zip(row['args'],args)) for row in initial.raw if row['op']==t)
    # If an intermediate constructor itself appeared during saturation, the
    # full initial expression may not evaluate. Rule out each possible prior
    # row via a preserved, named coordinate in the final equivalence graph.
    require((None not in before and bval is None) or distinct_initial,'cannot_distinguish_new_native_return')
    if not derived:
        source=next(z for z in origin['consumer']['rows'] if z['atom']==proof['pivot'])
        require(len(source['terms'])==len(args),'unresolved_consumer_terms')
        for i,term in enumerate(source['terms']):
            require(final.term(one(term),proof['sorts'][i][0])==args[i],'native_return_not_observed_consumer_input')
    seed=[(z['table'],tuple(final.ports['input_'+str(z['atom'])+'_c'+str(j)]for j in range(len(z['values'])-1)),final.ports['input_'+str(z['atom'])]) for z in profile['root_rows']]
    exact=[];failures=[]
    for idx in found:
        try:exact.append(valid_history_record(h,records[idx],entry,final,t,[*args,val],seed))
        except Refusal as e:failures.append(str(e))
    require(bool(exact),failures[0] if failures else 'no_history_witness')
    linked=[]
    for e in exact:
        pi=next(i for i,rec in enumerate(records)if rec['id']==e['record'])
        for ci,rec in enumerate(records[pi+1:],pi+1):
            cr=h['rules'][rec['rule']]
            if cr['name']!=origin['consumer']['source_name'] or pi not in rec['parents']:continue
            try:checks=valid_history_record(h,rec,entry,final,t,None,[])
            except Refusal:continue
            for hit in checks['read_sites']:
                if hit['operator']!=t or hit['coordinates']!=[*args,val]:continue
                port=rec['ports'][hit['position']].get('Parent')
                if not isinstance(port,list) or len(port)!=2 or not all(integer(z)for z in port):continue
                pr=records[pi]
                if checked_i(port[0],rec['parents'],'foreign_parent_occurrence')!=pi or checked_i(port[1],pr['values'],'foreign_output_port')!=hit['token']:continue
                for birth in e['output_sites']:
                    if birth['token']==hit['token'] and pr['outputs'][port[1]]=={'Row':birth['span']}:
                        linked.append(dict(producer_record=e['record'],consumer_record=rec['id'],producer_index=pi,consumer_index=ci,
                                           write_read_token=hit['token'],read_site=hit['span'],source_parent_port=port))
    require(t in final.tables and final.tables[t]['types']==[v[0] for v in proof['sorts'][:-1]]
            and final.tables[t]['output']==proof['sorts'][-1][0],'foreign_native_table_schema')
    def logical(form):
        ast=rule_ast(form);return [*ast[:3]]
    in_scope=[logical(one(x)) for x in final.scope['rules']]
    for role in ('producer','consumer'):
        rs=[rule_ast(one(x['text']))for x in h['rules']if x['name']==origin[role]['source_name']]
        require(any(logical(v) in in_scope for v in rs),'foreign_native_scope_rule')
    return dict(history_producer_occurrences=[x['record']for x in exact],local_proof=exact,native_consumer_reads=linked,table=t,local_args=list(args),local_result=val,
                native_consumer_rule_present=True,local_ids='sample-local',checked_seed_ports=len(profile['root_ports']))

def valid_history_record(h,rec,entry,graph,table,coords,seed):
    rule=h['rules'][rec['rule']]
    sites={z['span']:z for z in rule['sites']}
    tokens=h['tokens']
    def token(i):return checked_i(i,tokens,'unknown_history_token')
    def val(i):
        t=token(i);c=t.get('final_class')
        require(integer(c) and checked_i(c,graph.values,'history_class_out_of_range')['sort']==t['sort'],'history_class_sort_mismatch')
        return c
    def site(span,where):
        v=sites.get(span,{})
        require(v.get('path','').startswith(where+'/'),'incorrect_native_history_site')
        loc=re.search(r':(\d+):(\d+)$',span)
        require(loc is not None,'unbound_native_source_span')
        raw=entry.encode()[int(loc[1]):int(loc[2])].decode()
        require(one(raw)==one(v['expression']),'history_site_source_mismatch')
        return one(raw)
    require(len(rec['outputs'])==len(rec['values']) and len(rec['inputs'])==len(rec['wanted']),'ill_formed_history_arity')
    env={}
    for role,i in zip(rec['inputs'],rec['wanted']):
        if 'Var' in role:env[role['Var']]=val(i)
    for role,i in zip(rec['outputs'],rec['values']):
        if 'Var' in role:require(env.get(role['Var'],val(i))==val(i),'history_variable_conflict');env[role['Var']]=val(i)
    def expr(term,sort):
        if isinstance(term,str) and term in env:
            c=env[term];require(graph.values[c]['sort']==sort,'history_input_sort_conflict');return c
        if isinstance(term,str):return graph.literal(term,sort)
        decl=graph.tables.get(term[0]);require(decl is not None and len(term)==len(decl['types'])+1,'unsupported_native_history_read')
        v=graph.rows.get((term[0],tuple(expr(a,t) for a,t in zip(term[1:],decl['types']))))
        require(v is not None and graph.values[v]['sort']==sort,'native_history_term_missing');return v
    read_ids=[];reads=[];positions=[]; read_sites=[]
    for n,(role,i) in enumerate(zip(rec['inputs'],rec['wanted'])):
        if 'Read' not in role:continue
        source=site(role['Read'],'body');op=source[0];decl=graph.tables.get(op)
        require(decl is not None and len(decl['types'])+1==len(source),'unsupported_native_history_read')
        require(token(i)['sort']=='Fact:'+op,'history_required_fact_sort')
        result=val(checked_i(len(reads),rec['read_results'],'missing_history_read_result'))
        args=tuple(expr(a,t)for a,t in zip(source[1:],decl['types']))
        require(graph.rows.get((op,args))==result,'history_required_fact_not_in_graph')
        read_ids.append(i);reads.append((op,args,result,n));read_sites.append(dict(token=i,operator=op,coordinates=[*args,result],position=n,span=role['Read']))
    require(len(rec['read_results'])==len(reads) and set(read_ids)==set(rec['required']) and bool(read_ids),'history_required_facts_disagree')
    require(all(any(a==k and b==x and d==y for a,b,d,n in reads) for k,x,y in seed),'history_did_not_read_grounded_inputs')
    if coords is None:return dict(record=rec['id'],required=read_ids,read_sites=read_sites)
    columns={};produced_rows={}
    for role,i in zip(rec['outputs'],rec['values']):
        if 'Column' in role:
            span,col=role['Column']
            require(integer(col) and col not in columns.setdefault(span,{}),'invalid_history_column')
            columns[span][col]=val(i)
        if 'Row' in role:produced_rows[role['Row']]=i
    for span,i in produced_rows.items():
        if i not in rec['produced'] or token(i)['sort']!='Fact:'+table:continue
        text=site(span,'head')
        if text[0]!=table:continue
        if columns.get(span)==dict(enumerate(coords)):
            positions.append(dict(path=sites[span]['path'],span=span,token=i,columns=coords))
    require(bool(positions),'history_did_not_emit_exact_typed_row')
    return dict(record=rec['id'],required=read_ids,output_sites=positions)
