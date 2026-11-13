"""Observed continuations across adjacent nonempty Runs with complete local premise evidence.

Restrict producers to union/copy: traces do not identify fresh constructor returns.
Never infer physical output ownership from a logical operation location.
"""
import argparse,hashlib,json
from collections import Counter,defaultdict
from pathlib import Path
from collect_observed_corpus import read_bytes
from observed_cell_targets import instantiate
from dominator_completion import compose,freeze


def producer_interface(sample,binding):
    env=dict(sample['binding']);quotient={freeze(a):freeze(b) for a,b in sample['completion']['source_map']};forward={};reverse={}
    for port in binding['eq_ports']:
        symbol=freeze(env[port['slot']]);root=quotient[symbol];physical=(port['sort'],port['after'])
        if physical in forward and forward[physical]!=root:return None,'outside_local_equality'
        if root in reverse and reverse[root]!=physical:return None,'missing_native_equality'
        forward[physical]=root;reverse[root]=physical
    return forward,None


def rebind_consumer(rule,binding,interface,tables):
    sample,reason=instantiate(rule,binding,tables)
    if reason:return None,reason
    ports={p['slot']:p for p in binding['eq_ports']};out=[]
    for slot,value in sample['binding']:
        if rule['slots'][slot]['sort']['kind']=='eq':
            p=ports[slot];key=(p['sort'],p['before'])
            if key not in interface:return None,'external_consumer_input'
            value=interface[key]
        out.append((slot,freeze(value)))
    return out,None


def boundary_inputs(binding,interface):
    """Separate observed consumer inputs without inventing producer ownership.

    Physical roots are evidence only, scoped to this program/Run. External
    aliases share a local index; neither roots nor future inputs are features
    available to the producer before the consumer boundary.
    """
    external={};ports=[]
    for p in binding['eq_ports']:
        key=(p['sort'],p['before'])
        if key in interface:
            source=dict(kind='producer_interface',symbol=interface[key])
        else:
            index=external.setdefault(key,len(external))
            source=dict(kind='external',index=index)
        ports.append(dict(slot=p['slot'],sort=p['sort'],source=source))
    return dict(ports=ports,external_classes=len(external),
                observed_values=binding['values'])


def collect(program,trace,case,split,boundary_sink=None):
    if program['sha256']!=trace['program_sha256'] or not trace['strict_audit_reference_equal'] or not trace['run_control_counts_equal']:raise ValueError('unaudited program trace')
    rules=program['recipe']['rules'];tables={t['name']:t for t in program['recipe']['tables']};steps={s['ordinal']:s for s in trace['steps']};runs=trace['runs'];rows={};counts=Counter()
    for before,after in zip(runs,runs[1:]):
        po,co=before['ordinal'],after['ordinal']
        gap=list(range(po+1,co))
        if any(k not in steps or steps[k]['executed_bindings']!=0 for k in gap):counts['unproved_run_gap']+=1;continue
        if gap:counts['proved_empty_run_gaps']+=1
        index=defaultdict(list)
        for j,b in enumerate(after['audit']['bindings']):
            keys={(p['sort'],p['before']) for p in b['eq_ports']}
            for key in keys:index[key].append(j)
        for ordinal,b in enumerate(before['audit']['bindings']):
            rid=b['rule'];rule=rules[rid];kinds={op['kind'] for op in rule['effects']}
            if 'union' not in kinds or not kinds<={'union','copy'}:continue
            counts['producer_bindings']+=1;sample,reason=instantiate(rule,b,tables)
            if reason:counts['producer:'+reason]+=1;continue
            if not sample['completion']['novel']:counts['producer_no_local_change']+=1;continue
            interface,reason=producer_interface(sample,b)
            if reason:counts[reason]+=1;continue
            candidates=sorted({j for key in interface for j in index.get(key,[])})
            for j in candidates:
                cb=after['audit']['bindings'][j];cid=cb['rule']
                if cid==rid:continue
                inputs,reason=rebind_consumer(rules[cid],cb,interface,tables)
                if reason:
                    counts['consumer:'+reason]+=1
                    if reason=='external_consumer_input' and boundary_sink is not None:
                        boundary_sink(dict(case=case,split=split,program_sha256=program['sha256'],
                            producer=rid,consumer=cid,producer_run=po,consumer_run=co,
                            producer_binding_ordinal=ordinal,consumer_binding_ordinal=j,
                            producer_ruleset=steps[po]['ruleset'],consumer_ruleset=steps[co]['ruleset'],
                            empty_intervening_runs=gap,source=sample['source'],
                            producer_binding=sample['binding'],first_completion=sample['completion'],
                            consumer_inputs=boundary_inputs(cb,interface),
                            evidence='observed_shared_interface_candidate',
                            causal_link_proven=False,takeover_authorized=False))
                    continue
                completion,reason=compose(sample['completion']['facts'],rules[cid],inputs,tables)
                if reason:counts['local_premise:'+reason]+=1;continue
                if not completion['novel']:counts['consumer_no_local_change']+=1;continue
                # Consumer must become locally enabled by the producer, not
                # merely be a different request already true in the source.
                earlier,reason_before=compose(sample['source'],rules[cid],inputs,tables)
                if reason_before is None:counts['consumer_already_enabled']+=1;continue
                if reason_before!='missing consumer premise':counts['unsupported_precheck']+=1;continue
                key=json.dumps((rid,sample['source'],sample['binding'],cid,inputs),sort_keys=True)
                counts['proven_observed_occurrences']+=1
                if key in rows:rows[key]['observations']+=1;continue
                rows[key]=dict(case=case,split=split,program_sha256=program['sha256'],producer=rid,consumer=cid,source=sample['source'],producer_binding=sample['binding'],first_completion=sample['completion'],consumer_binding=inputs,second_completion=completion,producer_run=po,consumer_run=co,empty_intervening_runs=gap,producer_ruleset=steps[po]['ruleset'],consumer_ruleset=steps[co]['ruleset'],producer_binding_ordinal=ordinal,consumer_binding_ordinal=j,observations=1,source_run_validated=True)
    return list(rows.values()),dict(counts)


def main():
    p=argparse.ArgumentParser();p.add_argument('manifest',type=Path);p.add_argument('output',type=Path);p.add_argument('--max-cases',type=int,default=10);p.add_argument('--max-bindings',type=int,default=20000);p.add_argument('--boundary-output',type=Path);a=p.parse_args()
    boundary_file=a.boundary_output.open('w') if a.boundary_output else None
    boundary_counts=Counter();boundary_consumers=set();boundary_producers=set();boundary_digest=hashlib.sha256()
    def sink(row):
        encoded=json.dumps(row)+'\n';boundary_file.write(encoded);boundary_digest.update(encoded.encode())
        boundary_counts['candidate_pairs']+=1
        boundary_counts['external_classes:'+str(row['consumer_inputs']['external_classes'])]+=1
        boundary_counts['split:'+row['split']]+=1
        boundary_counts['cross_ruleset_pairs']+=int(row['producer_ruleset']!=row['consumer_ruleset'])
        boundary_consumers.add((row['case'],row['consumer_run'],row['consumer_binding_ordinal']))
        boundary_producers.add((row['case'],row['producer_run'],row['producer_binding_ordinal']))
    manifest=json.loads(a.manifest.read_text());rows=[];reports=[];skipped=[];used=0
    for entry in manifest['cases']:
        if entry['status']!='complete':continue
        if entry['summary']['observed_bindings']>a.max_bindings:skipped.append(dict(case=entry['case'],reason='binding budget'));continue
        if used>=a.max_cases:skipped.append(dict(case=entry['case'],reason='case budget'));continue
        used+=1;program_bytes=read_bytes(Path(entry['program']));trace_bytes=read_bytes(Path(entry['trace']))
        if hashlib.sha256(trace_bytes).hexdigest()!=entry['trace_sha256']:raise ValueError('trace fingerprint mismatch')
        program=json.loads(program_bytes);trace=json.loads(trace_bytes);found,counts=collect(program,trace,entry['case'],entry['split'],sink if boundary_file else None);rows.extend(found)
        report=dict(case=entry['case'],split=entry['split'],trace_sha256=entry['trace_sha256'],chains=len(found),counts=counts);reports.append(report);print(json.dumps(report),flush=True)
    if boundary_file:boundary_file.close()
    result=dict(schema='observed-local-cell-continuations/v1',manifest_sha256=hashlib.sha256(a.manifest.read_bytes()).hexdigest(),chains=rows,cases=reports,skipped=skipped,limits=dict(max_cases=a.max_cases,max_bindings=a.max_bindings),summary=dict(chains=len(rows),observations=sum(r['observations'] for r in rows),cross_ruleset=sum(r['producer_ruleset']!=r['consumer_ruleset'] for r in rows)),limitations=['Adjacent nonempty observed Runs; intervening Runs must have zero executed bindings; union/copy producers only','Consumer local completion is conditional teacher output, not observed constructor return identity','Actual match occurrence and local premise closure do not prove arbitrary full-program takeover','No neural or GPU successor execution in this collector'])
    result['boundary_candidates']=dict(enabled=boundary_file is not None,counts=dict(boundary_counts),
        unique_consumers=len(boundary_consumers),unique_producers=len(boundary_producers),
        sha256=boundary_digest.hexdigest() if boundary_file else None,
        causal_link_proven=False,takeover_authorized=False)
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result['summary']))

if __name__=='__main__':main()
