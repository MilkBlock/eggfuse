"""Audit the first divergent exclusive Run by resolving its actually issued proof addresses."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

import torch

from alternate_proofs import digest
from anchor_set_audit import check
from online import SourcePanic,execute
from prefix_policy import Policy
from rule_read import load_actor


def receipt_probe(folder,binary,tape,issued,known,run):
    requests=[]
    unresolved=Counter()
    for packet in issued:
        parents=[]
        for item in packet['parents']:
            addr=item['address']
            tok=addr['token']
            src=tok if tok<0 and tok%2 else known.get(tok)
            if src is None:
                unresolved['repair' if tok<0 else 'unmapped_producer']+=1
                break
            parents.append(dict(address=dict(token=src,op=addr['op']),version=item['version']))
        else:
            requests.append(dict(packet,parents=parents))
    reports=check(folder,binary,tape,requests)['recall_verdicts']
    if any(r!=run for r,_,_,_ in reports):
        raise ValueError('probe crossed source boundary')
    hits={t:w for _,t,w,_ in reports if w is not None}
    return hits,dict(issued=len(issued),unresolved=unresolved,distinct=len(set(hits.values())),
                     duplicates=len(hits)-len(set(hits.values())),
                     other=Counter(reason for _,_,w,reason in reports if w is None))


def inspect(folder,receiver,weights,seed):
    native=json.loads((folder/'capture.json').read_bytes())
    tape=json.loads((folder/'tape.json').read_bytes())
    reference=defaultdict(dict)
    for packet in tape['requests']:
        reference[packet['run']][packet['token']]=packet
    issued=defaultdict(list)
    def keep(packets):
        for p in packets:
            issued[p['run']].append(p)
    actor=load_actor(weights,True)
    failure=None
    try:
        model=execute(receiver,folder/'program.json',actor,seed,observe_packets=keep,prefix_policy=Policy(32))
    except SourcePanic as error:
        rules=json.loads((folder/'program.json').read_bytes())['recipe']['rules']
        proposals=Counter(p['rule'] for p in issued[error.run])
        failure=dict(kind='source_panic',run=error.run,charged=error.charged,issued_by_rule=proposals,
                     proposed_rules_with_panic=[rid for rid in proposals
                                                if any(op['op']=='panic' for op in rules[rid]['effects'])])
        model=execute(receiver,folder/'program.json',actor,seed,run_limit=error.run-1,prefix_policy=Policy(32))
        if model['runs']!=error.run-1:
            raise ValueError('failed to reproduce completed prefix')
    first=next((i+1 for i,(step,expected) in enumerate(zip(model['source_schedule'],native['schedule']))
        if step!=expected or model['writes_by_run'][i]!=native['writes'][i] or model['rhs_by_run'][i]!=native['rhs'][i]),failure['run'] if failure else None)
    if first is None:
        raise ValueError('no comparable divergent source Run')
    mapped={}
    report={}
    for run in range(1,first+1):
        owners,ledger=receipt_probe(folder,receiver,tape,issued[run],mapped,run)
        hits=set(owners.values())
        if not hits<=reference[run].keys():
            raise ValueError('invalid committed owner')
        mapped.update(owners)
        unresolved=ledger['unresolved']
        missing=set(reference[run])-hits
        rules=Counter(p['rule'] for p in issued[run])
        required=Counter(p['rule'] for p in reference[run].values())
        report[run]=dict(issued=len(issued[run]),translated=len(issued[run])-sum(unresolved.values()),unresolved=unresolved,
            required=len(reference[run]),covered=len(hits),required_by_rule=required,issued_by_rule=rules,
            missing_by_rule=Counter(reference[run][w]['rule'] for w in missing),
            required_rules_proposed=len(rules.keys()&required.keys()),proposed_rules=len(rules),
            required_rules=len(required),missing_winners=sorted(missing),rejections=ledger['other'],
            reference_order_digest=native['rhs'][run-1],actual_order_digest=model['rhs_by_run'][run-1] if run<=model['runs'] else None,
            reference_step=native['schedule'][run-1],actual_step=model['source_schedule'][run-1] if run<=model['runs'] else None,
            effective_write_digest_equal=run<=model['runs'] and native['writes'][run-1]==model['writes_by_run'][run-1])
        if run<first and (missing or unresolved or len(reference[run])!=model['source_schedule'][run-1][4]):
            raise ValueError('earlier correspondence is incomplete')
    return dict(first=first,runs=report,failure=failure)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('root','receiver','weights','out'):p.add_argument(n,type=Path)
    p.add_argument('--cases',nargs='+',required=True)
    a=p.parse_args()
    torch.set_num_threads(1)
    seeds={r['directory']:r['seed'] for r in json.loads((a.root/'manifest.json').read_bytes())}
    results={n:inspect(a.root/n,a.receiver,a.weights,1703+seeds.get(n,0)) for n in a.cases}
    a.out.write_text(json.dumps(dict(mode='exclusive with offline address audit',receiver_sha256=digest(a.receiver),
                                    weights_sha256=digest(a.weights),cases=results),indent=2)+'\n')
