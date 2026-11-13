"""Earlier constructor observations for uncovered inputs; not lifetime certificates."""
from collections import Counter,defaultdict
from link_rhs_results import link


def candidates(trace,earliest=False):
    adjacent=link(trace);covered={(w['consumer_run'],c['binding'],p['slot']) for w in adjacent['windows'] for c in w['consumers'] for p in c['ports'] if 'group' in p}
    history={};out={};counts=Counter();rules=trace['recipe']['rules'];steps={s['ordinal']:s for s in trace['steps']}
    for position,run in enumerate(trace['runs']):
        ordinal=run['ordinal']
        # Read old observations before adding any result from this Run.
        for i,b in enumerate(run['audit']['bindings']):
            for port in b.get('eq_ports',[]):
                address=(ordinal,i,port['slot']);counts['input_ports']+=1
                if address in covered:counts['adjacent_covered_ports']+=1;continue
                counts['uncovered_ports']+=1;entry=history.get((port['sort'],port['identity']))
                if entry is None:continue
                source_position,providers=entry
                out[address]=providers;counts['historical_candidate_ports']+=1
                counts['candidate_edges']+=len(providers)
                counts['age_nonempty_runs:'+str(position-source_position)]+=1
                if any(p['after_run']!=port['before'] for p in providers):counts['changed_endpoint_root_ports']+=1
                if steps[providers[0]['run']]['ruleset']!=steps[ordinal]['ruleset']:counts['cross_ruleset_ports']+=1
        current=defaultdict(list)
        for i,b in enumerate(run['audit']['bindings']):
            if not b['rhs']['completed'] or any('unavailable' in slot for slot in b['rhs']['slots']):
                counts['incomplete_provider_states_skipped']+=1;continue
            slots={s['slot']:s for s in b['rhs']['slots']}
            for operation,op in enumerate(rules[b['rule']]['effects']):
                if op['kind']!='construct':continue
                slot=slots.get(op['dst'],{})
                if 'unavailable' in slot or 'eq_port' not in slot:continue
                port=slot['eq_port'];key=(port['sort'],port['identity'])
                current[key].append(dict(run=ordinal,binding=i,rule=b['rule'],operation=operation,slot=op['dst'],
                    identity=port['identity'],after_run=port['after_run']))
        for key,providers in current.items():
            if not earliest or key not in history:history[key]=(position,providers)
        counts['peak_identity_groups']=max(counts['peak_identity_groups'],len(history))
        counts['peak_retained_provider_records']=max(counts['peak_retained_provider_records'],sum(len(p) for _,p in history.values()))
    counts['candidate_consumers']=len({(r,b) for r,b,_ in out})
    return adjacent,out,dict(counts)


def link_history(trace,fallback_only=False,earliest=False):
    adjacent,extra,counts=candidates(trace,earliest=earliest)
    windows={w['consumer_run']:w for w in adjacent['windows']}
    if fallback_only:
        connected={(w['consumer_run'],c['binding']) for w in adjacent['windows'] for c in w['consumers']}
        extra={a:p for a,p in extra.items() if a[:2] not in connected}
        counts['fallback_candidate_ports']=len(extra)
        counts['fallback_candidate_edges']=sum(len(p) for p in extra.values())
    grouped=defaultdict(list)
    for (run,binding,slot),providers in extra.items():grouped[run].append((binding,slot,providers))
    bindings={r['ordinal']:r['audit']['bindings'] for r in trace['runs']}
    for run,items in grouped.items():
        window=windows.setdefault(run,dict(consumer_run=run,producer_run=None,groups=[],consumers=[]))
        consumers={c['binding']:c for c in window['consumers']};groups={}
        for binding,slot,providers in items:
            # All alternatives from the selected observed constructor Run.
            key=tuple((p['run'],p['binding'],p['slot']) for p in providers)
            if key not in groups:
                groups[key]=len(window['groups']);window['groups'].append(dict(providers=providers))
            consumer=consumers.setdefault(binding,dict(binding=binding,rule=bindings[run][binding]['rule'],ports=[]))
            consumer['ports']=[p for p in consumer['ports'] if p['slot']!=slot]
            consumer['ports'].append(dict(slot=slot,group=groups[key],relation='historical_observed_identity'))
        window['consumers']=list(consumers.values())
    return dict(windows=[windows[k] for k in sorted(windows)],counts=counts,
        causal_link_proven=False,takeover_authorized=False,
        scope='offline observed-history context; no proof of retirement, generation or ownership')


def main():
    import argparse,hashlib,json,time
    from pathlib import Path
    from collect_observed_corpus import read_bytes
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    raw=read_bytes(a.trace);started=time.monotonic();_,extra,counts=candidates(json.loads(raw))
    result=dict(trace_sha256=hashlib.sha256(raw).hexdigest(),counts=counts,preparation_seconds=time.monotonic()-started,
        historical_observations=True,causal_link_proven=False,takeover_authorized=False,
        policy='fill uncovered ports using all complete-state constructor observations from latest prior source Run per typed identity',
        limitations=['No retirement, generation or ownership evidence in these records',
            'Changed endpoint roots are counted, never used to prove historical equivalence',
            'Provider states are historical completions; prediction must tolerate stale context',
            'Only input observations select candidates; RHS labels do not choose history'])
    a.output.write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main()
