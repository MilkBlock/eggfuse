"""Lower checked Cell catalog interfaces, never observed successful bindings."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import numpy as np
from cell_token_successors import compile_catalog, continuation_contract, complete_template
from collect_observed_corpus import read_bytes


def lower(recipe, catalog, source_slots=False, context_completion=False):
    if context_completion and not source_slots:raise ValueError('context completion requires source slots')
    rules=recipe['rules']
    inputs=[[i for i,s in enumerate(r['slots']) if s['definition']=='query'] for r in rules]
    positions=[{slot:i+1 for i,slot in enumerate(slots)} for slots in inputs]
    width=max(map(len,inputs),default=0)
    stages=sorted({r['metadata'].get('source_set') for r in rules},key=lambda x:json.dumps(x,sort_keys=True))
    entries=[];marks=[];context_proofs=[]
    tables={t['name']:t for t in recipe['tables']}
    facts=[complete_template(r,tables)[0] for r in rules]
    slot_width=max((len(r['slots']) for r in rules),default=0)
    for eid,edge in enumerate(catalog['edges']):
        source,target=edge['producer'],edge['consumer'];p,c=rules[source],rules[target]
        # Recheck rather than trusting a serialized flag or stale catalog.
        contract=continuation_contract(p,c,facts[source],edge)
        if contract!=edge.get('contract'):raise ValueError('catalog contract mismatch')
        reasons=[]
        if contract['boundary']!='same_ruleset':reasons.append('source_run_boundary')
        mapping=dict(edge['inputs']);projection=[]
        for slot in inputs[target]:
            ref=mapping[slot]
            if source_slots and ref[0]=='result':
                operation=ref[1]
                if not 0<=operation<len(p['effects']) or p['effects'][operation]['kind']!='construct':
                    raise ValueError('invalid result projection')
                origin=p['effects'][operation]['dst']
                if p['slots'][origin]['sort']!=c['slots'][slot]['sort']:reasons.append('sort_mismatch');continue
                projection.append(origin);continue
            if ref[0]!='input':
                reasons.append('actual_result_witness' if ref[0]=='result' else 'literal_key_encoding')
                continue
            origin=ref[1]
            if origin not in positions[source]:reasons.append('missing_source_input');continue
            if p['slots'][origin]['sort']!=c['slots'][slot]['sort']:reasons.append('sort_mismatch');continue
            projection.append(origin if source_slots else positions[source][origin])
        if reasons:
            marks.append(dict(entry=eid,producer=source,consumer=target,reasons=sorted(set(reasons))))
            continue
        # No effect operation is silently treated as completed by a query hit.
        # Even copy effects require the future authoritative slot executor.
        completed=not c['effects']
        context=None
        if context_completion:
            from context_effect_projection import compile_context
            context=compile_context(recipe,edge);context_proofs.append(dict(entry=eid,**context))
            completed=context['covered']
        entries.append(dict(entry=eid,producer=source,consumer=target,
            stage=stages.index(c['metadata'].get('source_set')),
            projection=projection+[0]*(width-len(projection)),
            projection_valid=[True]*len(projection)+[False]*(width-len(projection)),
            completed=completed,query_covered=True,transfer_covered=False,
            destination_projection=[inputs[target].index(i) if i in inputs[target] else 0 for i in range(slot_width)],
            destination_valid=[i in inputs[target] for i in range(slot_width)]))
        if context_completion:
            mapping=context['projection'] if context['covered'] else {}
            entries[-1]['completion_projection']=[mapping.get(i,0) for i in range(slot_width)]
            entries[-1]['completion_valid']=[i in mapping for i in range(slot_width)]
    return dict(schema='device-cell-entry-layout/v1',input_slots=inputs,key_width=width+1,stages=stages,
        entries=entries,marks=marks,context_completion=context_completion,context_proofs=context_proofs,source_slots=source_slots,slot_width=slot_width,
        uncovered_catalog_boundaries=catalog['boundaries'],
        missing_coverage='multi-source and late/union-enabled matches are not covered by this single-source catalog',
        closure_authorized=False,ownership_transfer_authorized=False)


def tensors(layout,weights,bias):
    entries=layout['entries'];count=len(entries)
    if count==0:raise ValueError('no lowered entries; caller must retain boundary work')
    weights=np.asarray(weights,np.float32);bias=np.asarray(bias,np.float32)
    if weights.ndim!=3 or weights.shape[0]!=count or weights.shape[1]!=weights.shape[2] or bias.shape!=(count,weights.shape[1]):
        raise ValueError('float transition layout mismatch')
    if not np.isfinite(weights).all() or not np.isfinite(bias).all():raise ValueError('nonfinite transition coefficients')
    out={k:np.array([e[k] for e in entries],dtype=np.int32) for k in ('producer','consumer','stage','projection')}
    out.update({k:np.array([e[k] for e in entries],dtype=bool) for k in ('projection_valid','completed','query_covered','transfer_covered')})
    if layout['source_slots']:
        out['destination_projection']=np.array([e['destination_projection'] for e in entries],np.int32)
        out['destination_valid']=np.array([e['destination_valid'] for e in entries],bool)
    if layout['context_completion']:
        out['completion_projection']=np.array([e['completion_projection'] for e in entries],np.int32)
        out['completion_valid']=np.array([e['completion_valid'] for e in entries],bool)
    out.update(weights=weights,bias=bias)
    return out


def main():
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path);p.add_argument('--source-slots',action='store_true');p.add_argument('--context-completion',action='store_true');a=p.parse_args()
    raw=read_bytes(a.source);data=json.loads(raw);catalog=compile_catalog(data['recipe']);layout=lower(data['recipe'],catalog,source_slots=a.source_slots,context_completion=a.context_completion)
    summary=dict(source_sha256=hashlib.sha256(raw).hexdigest(),rules=len(data['recipe']['rules']),
        catalog_entries=len(catalog['edges']),lowered_entries=len(layout['entries']),
        completed_consumers=sum(e['completed'] for e in layout['entries']),
        pending_effect_consumers=sum(not e['completed'] for e in layout['entries']),
        key_width=layout['key_width'],slot_width=layout['slot_width'],source_slots=a.source_slots,stages=layout['stages'],
        marks_by_reason=dict(Counter(reason for m in layout['marks'] for reason in m['reasons'])),
        catalog_boundary_count=len(catalog['boundaries']),
        context_completion=a.context_completion,context_boundaries=dict(Counter(p['reason'] for p in layout['context_proofs'] if not p['covered'])),
        scope='Recipe-only lowering coverage; no runtime matches, effects, ownership transfer or speed measured',
        closure_authorized=False,ownership_transfer_authorized=False)
    a.output.write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
