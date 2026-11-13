"""Structural counterfactual only: removing edges is not semantic authorization."""
import argparse,hashlib,json
from collections import Counter,defaultdict
from pathlib import Path
from collect_observed_corpus import read_bytes
from historical_cell_sources import link_history


def depths(order,edges):
    result={}
    for address in order:
        sources=edges.get(address,[])
        if any(source not in result for source in sources):raise ValueError('noncausal dependency')
        result[address]=1+max((result[source] for source in sources),default=-1)
    return result


def analyze(trace):
    order=[(r['ordinal'],i) for r in trace['runs'] for i,_ in enumerate(r['audit']['bindings'])]
    links=link_history(trace,fallback_only=True);edges=defaultdict(list);reduced=defaultdict(list)
    counts=Counter();by_constructor=Counter();removed_consumers=set();edge_tables={}
    for window in links['windows']:
        for c in window['consumers']:
            destination=(window['consumer_run'],c['binding'])
            for port in c['ports']:
                if 'group' not in port:continue
                historical=port.get('relation')=='historical_observed_identity'
                for provider in window['groups'][port['group']]['providers']:
                    source=(provider.get('run',window['producer_run']),provider['binding'])
                    effect=trace['recipe']['rules'][provider['rule']]['effects'][provider['operation']]
                    nullary=effect['kind']=='construct' and not effect.get('args',[])
                    edges[destination].append(source);counts['all_edges']+=1
                    if historical:counts['historical_edges']+=1
                    if historical and nullary:
                        counts['historical_nullary_edges']+=1;removed_consumers.add(destination)
                        by_constructor[effect.get('call',{}).get('table','unknown')]+=1
                    else:
                        reduced[destination].append(source)
                        edge_tables[(destination,source)]=effect.get('call',{}).get('table','unknown')
    original=depths(order,edges);counterfactual=depths(order,reduced)
    critical=Counter();cursor=max(order,key=lambda a:counterfactual[a]) if order else None
    while cursor is not None and reduced[cursor]:
        source=max(reduced[cursor],key=lambda a:counterfactual[a]);critical[edge_tables[(cursor,source)]]+=1;cursor=source
    counts['consumers_losing_edges']=len(removed_consumers)
    counts['consumers_losing_all_sources']=sum(not reduced[a] for a in removed_consumers)
    return dict(counterfactual_critical_chain_tables=dict(critical),counts=dict(counts),nullary_tables=dict(by_constructor),
        original_layers=max(original.values(),default=-1)+1,
        counterfactual_layers=max(counterfactual.values(),default=-1)+1,
        original_base_coefficient_floats=counts['all_edges']*128,
        counterfactual_base_coefficient_floats=(counts['all_edges']-counts['historical_nullary_edges'])*128,
        nodes_with_reduced_depth=sum(counterfactual[a]<original[a] for a in order),
        semantic_equivalence_proven=False,takeover_authorized=False,
        scope='CPU graph-shape counterfactual, no inference or graph mutation',
        limitations=['Nullary constructors can belong to dynamic Eq classes; removing their full Cell context is not proved safe',
            'Depth changes are not a GPU timing or accuracy result',
            'Adjacent sources are preserved; only historical nullary edges are omitted in the counterfactual'])


def main():
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    raw=read_bytes(a.trace);result=analyze(json.loads(raw));result['trace_sha256']=hashlib.sha256(raw).hexdigest()
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
