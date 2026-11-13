"""Ordered slot copies over Cell instances; no new identities or float equality."""


def compile_copies(recipe):
    sites=[];marks=[]
    for rid,rule in enumerate(recipe['rules']):
        for oi,op in enumerate(rule['effects']):
            if op['kind']!='copy':continue
            if 'slot' not in op['arg']:
                marks.append(dict(rule=rid,operation=oi,reason='literal_copy'));continue
            src,dst=op['arg']['slot'],op['dst']
            if not all(0<=s<len(rule['slots']) for s in (src,dst)):raise ValueError('invalid copy slot')
            if rule['slots'][src]['sort']!=rule['slots'][dst]['sort']:raise ValueError('copy sort mismatch')
            sites.append(dict(rule=rid,operation=oi,src=src,dst=dst,last_effect=oi==len(rule['effects'])-1))
    return dict(sites=sites,marks=marks)


def execute_copy(state,site,xp):
    width=state['slots'].shape[1];src,dst=site['src'],site['dst']
    if not all(0<=s<width for s in (src,dst)):raise ValueError('copy slot outside instance')
    selected=state['present']&state['active']&state['visible']&~state['settled']&(state['keys'][:,0]==site['rule'])&(state['effect_pc']==site['operation'])
    ready=selected&state['slot_valid'][:,src]
    write=ready[:,None]&(xp.arange(width)[None,:]==dst)
    out=dict(state)
    for column in ('slots','slot_roots','scalar_numbers','scalar_numeric','scalar_codes','scalar_valid'):
        if column in state:
            value=state[column];mask=write[:,:,None] if value.ndim==3 else write
            out[column]=xp.where(mask,value[:,src:src+1],value)
    out['slot_valid']=state['slot_valid']|write
    out['effect_pc']=state['effect_pc']+ready.astype(xp.int32)
    out['settled']=state['settled']|(ready&site['last_effect'])
    if 'tokens' in state or 'token_dirty' in state:
        out['token_dirty']=state.get('token_dirty',xp.zeros_like(ready))|ready
    return out,dict(ready=ready,missing_source=selected&~state['slot_valid'][:,src],needs_attention=xp.any(selected&~ready))


def main():
    import argparse,json,hashlib
    from pathlib import Path
    from collections import Counter
    from collect_observed_corpus import read_bytes
    from device_constructor_completion import compile_completion
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('entry_audit',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    raw=read_bytes(a.trace);recipe=json.loads(raw)['recipe'];audit=json.loads(a.entry_audit.read_text())
    digest=hashlib.sha256(raw).hexdigest()
    if audit['trace_sha256']!=digest:raise ValueError('entry audit uses another trace')
    copies=compile_copies(recipe);plan=compile_completion(recipe,max(len(r['slots']) for r in recipe['rules']))
    covered={(s['rule'],s['operation']) for _,s in plan['operations']};prefix=[];full=[]
    for rid,rule in enumerate(recipe['rules']):
        count=0
        while (rid,count) in covered:count+=1
        prefix.append(count)
        if count and count==len(rule['effects']):full.append(rid)
    rows=audit['records']
    result=dict(scope='Static recipe coverage, not executed real-workload completion',trace_sha256=digest,
        compiled_copy_sites=len(copies['sites']),copy_boundaries=dict(Counter(m['reason'] for m in copies['marks'])),
        compiled_effect_sites=len(plan['operations']),fully_supported_rules=len(full),probed_entries=len(rows),
        probed_entries_with_supported_prefix=sum(prefix[r['consumer']]>0 for r in rows),
        probed_fully_supported_entries=sum(r['consumer'] in full for r in rows),boundary_counts=dict(Counter(m['reason'] for m in plan['marks'])))
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
