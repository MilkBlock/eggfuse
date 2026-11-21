"""Run bounded native scopes. All canonical states and all local applications are emitted by Rust."""
import argparse,json,os,subprocess
from hashlib import sha256
from pathlib import Path
from region import Source,INPUT,tokens
from links import extend
from capture import digest,rule_sig
HERE=Path(__file__).resolve().parent
def load(p):return json.loads(p.read_bytes())
def write(p,x):p.write_text(json.dumps(x,indent=1,ensure_ascii=False)+'\n')
def extras(src,program,s):
    rs=program['recipe']['rules'];p=s['producer']['rule'];c=s['consumer']['rule']
    def effects(i):
        lhs=set(tokens(rs[i]['metadata']['name']))
        return {e['call']['table'] for e in rs[i]['effects'] if e.get('op')=='let' and 'table' in e.get('call',{}) and e['call']['table'] in lhs}
    produced=effects(p)|effects(c)
    candidates=[]
    for i,r in enumerate(rs):
        if i in (p,c) or len(r['query'])!=1:continue
        t=r['query'][0]['call'].get('table');m=r['metadata']
        if t not in produced or not src.rule(m['name']):continue
        # Static one-hop rule environment, independent of actual later donor applications.
        # Prefer rules from the named rulesets, involving existing reachable constructor operators.
        ops=effects(i);score=(m['source_set'] not in (s['producer']['ruleset'],s['consumer']['ruleset']),len(ops-produced),len(r['effects']),rule_sig(r))
        candidates.append((score,dict(rule=i,source_name=m['name'],ruleset=m['source_set'])))
    return [v for _,v in sorted(candidates,key=lambda x:x[0])[:1]]


def record_classes(history,graph):
    rows={(row['op'],tuple(row['args']),row['result']):i for i,row in enumerate(graph['rows'])}
    out=[]
    for ordinal,rec in enumerate(history['records']):
        rule=history['rules'][rec['rule']];sites={s['span']:s for s in rule.get('sites',[])};cols={}
        written={c['Row']:v for c,v in zip(rec['outputs'],rec['values']) if 'Row' in c and v in rec['produced']}
        for coord,token in zip(rec['outputs'],rec['values']):
            if 'Column' in coord:
                span,col=coord['Column'];cols.setdefault(span,{})[col]=history['tokens'][token].get('final_class')
        for span,vs in cols.items():
            if span not in sites or None in vs.values() or span not in written:continue
            vals=[vs[n] for n in range(max(vs)+1)];expr=tokens(sites[span]['expression'])
            if len(expr)<2:continue
            idx=rows.get((expr[1],tuple(vals[:-1]),vals[-1]))
            if idx is not None:out.append(dict(record=rec['id'],record_index=ordinal,write_token=written[span],rule=rec['rule'],span=span,path=sites[span]['path'],row=idx))
    return out


def operation(graph,root,rule,index):
    lookup={(r['op'],tuple(r['args'])):(i,r['result']) for i,r in enumerate(graph['rows']) if i not in graph.get('subsumed_rows',[])}
    slots={}
    def val(a):
        if 'slot' in a:return slots[a['slot']]
        sort=a['sort']['name'];label=json.dumps(a['literal'],separators=(',',':'),ensure_ascii=False)
        idx=next((i for i,v in enumerate(graph['values']) if v['sort']==sort and v.get('literal')==label),None)
        if idx is None:raise ValueError(f'missing native literal {sort}: {label}')
        return idx
    for row in root['rows']:
        j=row['atom'];vs=[graph['ports'][f'input_{j}_c{k}'] for k in range(len(row['values'])-1)]+[graph['ports'][f'input_{j}']]
        if lookup.get((row['table'],tuple(vs[:-1])),(None,None))[1]!=vs[-1]:raise ValueError('root row is not visible at its named ports')
        for a,v in zip(rule['query'][j]['args'],vs):
            if 'slot' in a and slots.setdefault(a['slot'],v)!=v:raise ValueError('inconsistent root aliases')
    for j,e in enumerate(rule['effects'][:index+1]):
        if e['op']=='copy':slots[e['dst']]=val(e['arg']);continue
        if e['op'] not in ('let','set') or 'table' not in e.get('call',{}):raise ValueError('unsupported source op sequence')
        rr,ret=lookup[e['call']['table'],tuple(val(a) for a in e['args'])]
        if e['op']=='let':slots[e['dst']]=ret
        if j==index:return rr
    raise ValueError('missing constructor output')

def port_binding(path,s,meta,pr):
    if meta['scope_mode']=='consumer':
        return dict(status='consumer_root_was_seeded',eligible_full_edge=False)
    graph=load(path/'native/saturated-rule-composition.json');initial=load(path/'native/initial-state.json');h=load(path/'native/history.json')
    try:
        producer=s['producer'];rule=pr['recipe']['rules'][producer['rule']];op=s['producer_op']
        idx=operation(graph,producer,rule,op);row=graph['rows'][idx]
        try:ini=operation(initial,producer,rule,op)
        except (KeyError,StopIteration,ValueError):ini=None
        rule_by_name={r['name']:j for j,r in enumerate(h['rules'])};pi=rule_by_name.get(producer['source_name']);ci=rule_by_name.get(s['consumer']['source_name'])
        records=record_classes(h,graph)
        matching=[z for z in records if z['rule']==pi and z['row']==idx]
        childids=[r['id'] for r in h['records'] if r['rule']==ci]
        source_index={r['metadata']['name']:i for i,r in enumerate(pr['recipe']['rules'])}
        causal=[]
        for wr in records:
            for ri,rd in enumerate(h['records']):
                if wr['record_index'] not in rd['parents'] or ri<=wr['record_index']:continue
                reads=[x['Read'] for x in rd['inputs'] if 'Read' in x]
                for use,(span,required) in enumerate(zip(reads,rd['required'])):
                    if required!=wr['write_token']:continue
                    sites={site['span']:site for site in h['rules'][rd['rule']]['sites']}
                    if span not in sites:continue
                    causal.append(dict(producer_record=wr['record'],consumer_record=rd['id'],producer_index=wr['record_index'],consumer_index=ri,
                        producer_rule=source_index.get(h['rules'][wr['rule']]['name']),consumer_rule=source_index.get(h['rules'][rd['rule']]['name']),
                        output_site=wr['path'],read_site=sites[span]['path'],read_expression=sites[span]['expression'],
                        row=wr['row'],token=required,read_result_class=(h['tokens'][rd['read_results'][use]].get('final_class') if rd['read_results'][use] is not None else None)))
        directed=[edge for edge in causal if edge['producer_rule']==s['producer']['rule'] and edge['consumer_rule']==s['consumer']['rule'] and edge['row']==idx and edge['read_result_class']==row['result']]
        full=meta['scope_mode'] in ('full','augmented') and ci is not None and ini is None and bool(matching)
        eligible=full and bool(directed)
        return dict(status='derived' if eligible else 'seed_or_partial_or_unproved',eligible_full_edge=eligible,certified_producer_new_port=(ini is None and bool(matching)),full_scope_contains_consumer=full,
                    local_causal_edges=causal,directed_native_reads=directed,
                    final_row=idx,operator=row['op'],argument_classes=row['args'],result_class=row['result'],initial_output_row=ini,
                    producer_history_records=[z['record'] for z in matching],consumer_history_records=childids,
                    producer_native_rule=pi,consumer_native_rule=ci,output_history_sites=matching,
                    added_rule_history=[dict(rule=r['rule'],name=h['rules'][r['rule']]['name'],record=r['id'],parents=r['parents']) for r in h['records'] if r['rule'] not in {pi,ci}])
    except (KeyError,StopIteration,ValueError,IndexError) as error:
        return dict(status='unresolved_local_output',reason=str(error),eligible_full_edge=False)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','origins','binary','out'):p.add_argument(k,type=Path)
    p.add_argument('--resume',action='store_true');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=a.resume);(a.out/'samples').mkdir(exist_ok=a.resume)
    def files(folder):
        accepted={'entry.egg','origin.json','native/entry.egg','native/initial-state.json','native/trigger-state.json','native/history.json','native/ripen.json','native/acceptance.json','native/saturated-rule-composition.json','native/observed-saturated-state.json','native/ripened.egg'}
        return {n:dict(path=str((folder/n).relative_to(a.out)),sha256=sha256((folder/n).read_bytes()).hexdigest()) for n in sorted(accepted) if (folder/n).exists()}
    out=dict(schema='eggfuse-ripsat-donor-evidence/v1',donors={},binary_sha256=sha256(a.binary.read_bytes()).hexdigest())
    limits={'EGG_LAYOUT_RIPEN_SWEEP_STEPS':'4','EGG_LAYOUT_RIPEN_OBSERVE_FACTS':'300','EGG_LAYOUT_RIPEN_OBSERVE_MS':'900'}
    for donor in ('dot-product','jacobi-1d'):
        data=load(a.origins/(donor+'.json'));src=Source(donor)
        pr=load(a.exp/'compact-holdouts-20261121-v1'/(donor+'-1703')/'program.json');items=[]
        rec=out['donors'][donor]=dict(program_sha256=data['program_sha256'],recipe_sha256=data['recipe_sha256'],
            source_parts={n:sha256((INPUT/n).read_bytes()).hexdigest() for n in ('common-prefix.egg',donor+'.eggpart','common-suffix.egg')},
            reference=data['reference'],discovery=data['discovery'],counts=data['counts'],samples=items,limits=limits)
        for s in data['samples']:
            prod=s['producer'];child=s['consumer'];ex=extras(src,pr,s)
            modes=['full']
            if ex:modes.append('augmented')
            if s['selection']!='generic':modes+=['producer','consumer']
            for mode in modes:
                sid=f"{donor}-p{prod['rule']}-o{s['producer_op']}-c{child['rule']}-{mode}"
                folder=a.out/'samples'/sid;folder.mkdir(exist_ok=a.resume)
                item=dict(sample_id=sid,scope_mode=mode,producer_rule=prod['rule'],consumer_rule=child['rule'],producer_op=s['producer_op'],consumer_atom=s['consumer_atom'],
                    producer_fingerprint=prod['fingerprint'],consumer_fingerprint=child['fingerprint'],relative_runs=s['relative_runs'],selection=s['selection'],support=s['support'],
                    producer_serial=prod['serial'],consumer_serial=child['serial'],original_fact=s['original_fact'],original_version=s['original_version'],wires=[[s['consumer_atom'],'op',s['producer_op']]],
                    producer_all_tables_named=all(r['named'] is not None for r in prod['rows']),consumer_all_tables_named=all(r['named'] is not None for r in child['rows']),
                    other_consumer_table_atoms=[r['atom'] for r in child['rows'] if r['atom']!=s['consumer_atom']])
                try:
                    text,meta=src.entry(s,mode,ex if mode=='augmented' else None)
                    if (folder/'entry.egg').exists() and ((folder/'entry.egg').read_text()!=text or load(folder/'origin.json')!=dict(sample=s,profile=meta)):raise RuntimeError('resumed inputs changed')
                    write(folder/'origin.json',dict(sample=s,profile=meta));(folder/'entry.egg').write_text(text)
                    if not (folder/'native/acceptance.json').exists():
                        proc=subprocess.run([a.binary,folder/'entry.egg',folder/'native'],capture_output=True,text=True,timeout=8,env={**os.environ,**limits})
                        if proc.returncode or not (folder/'native/acceptance.json').exists():raise ValueError('native execution did not complete: '+proc.stderr[-500:])
                    native=load(folder/'native/acceptance.json');item['native_accepted']=native['accepted'];item['native_acceptance']=native
                    if native['accepted']:
                        item['port_binding']=port_binding(folder,s,meta,pr)
                        initial=load(folder/'native/initial-state.json') if (folder/'native/initial-state.json').exists() else None
                        extend(item,s,meta,pr,data,initial,load(folder/'native/saturated-rule-composition.json'),operation)
                    else:
                        rr=load(folder/'native/ripen.json');item['native_reason']=rr['saturated_rule_composition'].get('reason') or rr['saturated_rule_composition'].get('error') or str(rr['saturated_rule_composition'])
                except (ValueError,KeyError,subprocess.TimeoutExpired) as e:
                    item.update(native_accepted=False,rejection=str(e))
                    if 'port_binding' in item:item['port_binding']['eligible_full_edge']=False
                if not (folder/'origin.json').exists():
                    write(folder/'origin.json',dict(sample=s,profile=dict(scope_mode=mode,entry_unavailable=True)))
                item['artifacts']=files(folder);items.append(item)
                print(sid,item['native_accepted'],item.get('port_binding',{}).get('status',item.get('rejection',item.get('native_reason','')))[:130],flush=True)
        write(a.out/'evidence.json',out)
if __name__=='__main__':main()
