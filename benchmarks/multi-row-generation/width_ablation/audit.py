"""CPU-only row/round diagnostics on Figure 20's original source witnesses."""
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
import sys

import numpy as np

# The verified Cell partitions and provenance checks are shared with Figure 20.
# Import the specific package rather than a generic module called `data`.
sys.path.append(str(Path(__file__).resolve().parents[1]))
from eclass_ablation.data import audit as source_audit, paired_controls as source_pairs
from eclass_ablation.data.check import discrete
from eclass_ablation.data.paired import request_decisions

DUPLICATE_BINS = ('duplicate_same_round_cross_row', 'duplicate_later_round_same_row',
                  'duplicate_later_round_cross_row')


def duplicate_profile(legal, slots, rows):
    """Charge each extra legal emission exactly once, independently of row order.

    For a witness emitted k times in a round, k-1 occurrences are simultaneous
    cross-row repeats. If it has appeared before, one additional occurrence is
    an inter-round repeat. Charge that repeat to same-row reuse if the current
    and historical emitter row sets overlap, else to a cross-row repeat. This
    overlap convention describes row participation, not a causal execution order.
    """
    if rows < 1 or slots % rows:
        raise ValueError('output slots must contain whole equal-length rows')
    length = slots // rows
    appearances = defaultdict(lambda: defaultdict(set))
    occupied = set()
    for slot, witness in legal:
        if not 0 <= slot < slots or slot in occupied:
            raise ValueError('duplicated physical slot or slot outside the layout')
        occupied.add(slot)
        row, step = divmod(slot, length)
        appearances[witness][step].add(row)
    result = dict.fromkeys(DUPLICATE_BINS, 0)
    for times in appearances.values():
        seen = set()
        for step in sorted(times):
            current = times[step]
            result['duplicate_same_round_cross_row'] += len(current) - 1
            if seen:
                name = 'duplicate_later_round_same_row' if seen & current else 'duplicate_later_round_cross_row'
                result[name] += 1
            seen.update(current)
    result['duplicate_later_round'] = sum(result[k] for k in DUPLICATE_BINS[1:])
    result['duplicate_cross_row'] = result[DUPLICATE_BINS[0]] + result[DUPLICATE_BINS[2]]
    result['duplicate_same_row'] = result[DUPLICATE_BINS[1]]
    if sum(result[k] for k in DUPLICATE_BINS) != len(occupied) - len(appearances):
        raise AssertionError('duplicate bins do not conserve the emission count')
    return result


def _valid_emissions(data, graph, first, second, legal_requests):
    """Recover semantic identities from selected sources and the *actual* parent slot."""
    a, b, req = (data[k][graph] for k in ('a', 'b', 'requests'))
    def at(stage):
        return {k:stage[k][graph] for k in ('active', 'pointers', 'rows')}
    parents = {}
    first_witnesses = []
    for slot, (i,j), _ in discrete(at(first)):
        if 0 <= i < len(a) and 0 <= j < len(b) and a[i,0] == b[j,0]:
            parents[slot] = (i,j)
            first_witnesses.append((slot,(i,j)))
    second_witnesses = []
    consumers = defaultdict(set)
    for slot, (pi,ri), _ in discrete(at(second)):
        if pi not in parents or not 0 <= ri < len(req) or not legal_requests[ri]:
            continue
        i,j = parents[pi]
        if not np.array_equal(a[i,:2], req[ri,2:4]):
            continue
        second_witnesses.append((slot,(i,j,ri)))
        consumers[(i,j)].add(ri)
    # Count use of a shared parent by distinct legal requests, separately from
    # repeating the same full obligation. An extra consumer is charged once.
    reuse = sum(len(requests)-1 for requests in consumers.values())
    return first_witnesses, second_witnesses, reuse


def _record_key(data, graph):
    h = sha256()
    h.update(str(data['template_id']).encode())
    for name in ('group_id','state','variant','a','b','requests','a_port','request_ports',
                 'phase','committed','external','external_ports'):
        value = np.ascontiguousarray(data[name][graph])
        h.update(name.encode());h.update(str(value.shape).encode());h.update(value.tobytes())
    return h.hexdigest()


def _groups(data):
    groups = defaultdict(list)
    for i, group_id in enumerate(data['group_id']):
        groups[int(group_id)].append(i)
    for indices in groups.values():
        pairs = [(int(data['state'][i]),int(data['variant'][i])) for i in indices]
        if len(set(pairs)) != len(pairs):
            raise ValueError('duplicate graph in a state/origin intervention group')
    return groups


def _subset(data, indices):
    return {key:(value[indices] if isinstance(value,np.ndarray) else value) for key,value in data.items()}


def _origin_switches(data, first, second, groups):
    counts = {state:dict(pairs=0, exact_on_both=0, required_parents_ready_on_both=0,
                         both_exact_given_ready=0) for state in ('post','external')}
    for indices in groups.values():
        loc = {(int(data['state'][i]),int(data['variant'][i])):i for i in indices}
        for state, name in ((1,'post'),(3,'external')):
            if (state,0) not in loc or (state,1) not in loc:
                continue
            i,j = loc[state,0],loc[state,1]
            before,after = data['requests'][i],data['requests'][j]
            changed = (before[:,2:4] != after[:,2:4]).any(-1)
            if changed.sum() != 1 or not np.array_equal(before[:,:2],after[:,:2]):
                raise ValueError('expected one changed requested origin and a fixed read endpoint')
            left, right = [request_decisions(data,k,first,second) for k in (i,j)]
            mask = changed & left[0] & right[0]
            exact, ready = left[1] & right[1], left[2] & right[2]
            bucket = counts[name]
            for key, flags in [('pairs', mask), ('exact_on_both', mask & exact),
                               ('required_parents_ready_on_both', mask & ready),
                               ('both_exact_given_ready', mask & exact & ready)]:
                bucket[key] += int(np.count_nonzero(flags))
    return counts


def metrics(data, first, second, rows, relation_pred=None):
    """Score actual device outputs. Supports full groups or a batch-one timing subset.

    `rows` counts parallel streams, or is a (make_rows, finish_rows) pair.
    Both stages store row-major slots: slot = r*L + t.
    Pass hard relation decisions [B,4] or logits [B,4,2] for paired legality tests.
    Source data and certificate state enter this routine only after generation.
    """
    batch = len(data['a']);slots = np.asarray(first['active']).shape[-1]
    widths = tuple(rows) if isinstance(rows,(tuple,list)) else (rows,rows)
    if (len(widths)!=2 or any(not isinstance(w,(int,np.integer)) or isinstance(w,(bool,np.bool_))
                              or w<1 or slots%w for w in widths)):
        raise ValueError('requested row count cannot tile this output layout')
    make_rows,finish_rows=map(int,widths)
    if batch==0 or np.shape(second['active'])!=(batch,slots) or np.shape(first['active'])!=(batch,slots):
        raise ValueError('both Runs require identical [graph,slot] geometry')
    report = source_audit(data,first,second)
    for graph in range(batch):
        make,finish,reuse = _valid_emissions(data,graph,first,second,report['request_legal'][graph])
        for label,witnesses,width in [('run1',make,make_rows),('run2',finish,finish_rows)]:
            graph_report=report[label]['per_graph'][graph]
            bins=duplicate_profile(witnesses,slots,width)
            if sum(bins[k] for k in DUPLICATE_BINS)!=graph_report['duplicates']:
                raise AssertionError('parallel duplicate attribution disagrees with source audit')
            if len(witnesses)+graph_report['illegal']!=graph_report['active_outputs']:
                raise AssertionError('legal and illegal proposals do not account for every active slot')
            if label=='run2':bins['distinct_requests_reusing_a_parent']=reuse
            graph_report.update(bins)
            for key,value in bins.items():report[label][key]=report[label].get(key,0)+value
    groups = _groups(data)
    complete_groups=[idx for idx in groups.values() if len(idx)==8]
    report['make_rows']=make_rows;report['finish_rows']=finish_rows
    report['rows']=finish_rows;report['slots_per_row']=slots//finish_rows
    report['graph_keys']=[_record_key(data,i) for i in range(batch)]
    report['group_ids']=[int(v) for v in data['group_id']]
    report['group_count']=len(groups);report['complete_intervention_groups']=len(complete_groups)
    report['origin_switch']=_origin_switches(data,first,second,groups)
    report['paired_controls']=None
    if relation_pred is not None:
        prediction=np.asarray(relation_pred)
        if prediction.shape==np.shape(data['requests'])[:2]+(2,):
            if not np.isfinite(prediction).all():raise ValueError('nonfinite relation logits')
            prediction=prediction.argmax(-1)
        if (prediction.shape!=np.shape(data['requests'])[:2] or prediction.dtype.kind not in 'biu'
                or not np.isin(prediction,(0,1)).all()):
            raise ValueError('expected binary decisions or two-class logits for each request')
        if complete_groups:
            ix=np.array([i for group in complete_groups for i in group],dtype=int)
            report['paired_controls']=source_pairs(_subset(data,ix),_subset(first,ix),_subset(second,ix),prediction[ix])
    return report


def paired_layouts(baseline,candidate):
    """Compare exactly the same graphs and retain matched eight-graph-group counts.

    A win/loss is a graph complete in just one layout. Both arms' Run 1 frontiers
    are tested independently for the common-ready subset, including parent fields.
    """
    if baseline['graph_keys']!=candidate['graph_keys'] or baseline['group_ids']!=candidate['group_ids']:
        raise ValueError('paired layouts require identical source inputs and order')
    def bucket():return dict(graphs=0,baseline_complete=0,candidate_complete=0,both_complete=0,
                             neither_complete=0,baseline_only=0,candidate_only=0)
    def add(b,x,y):
        b['graphs']+=1;b['baseline_complete']+=x;b['candidate_complete']+=y
        b['both_complete']+=x and y;b['neither_complete']+=not(x or y)
        b['baseline_only']+=x and not y;b['candidate_only']+=y and not x
    output={key:bucket() for key in ('nonempty','common_parent_ready_nonempty')}
    by_group={}
    for group,x,y in zip(baseline['group_ids'],baseline['run2']['per_graph'],candidate['run2']['per_graph']):
        if x['nonempty']!=y['nonempty']:raise ValueError('source nonempty disagreement')
        if not x['nonempty']:continue
        g=by_group.setdefault(str(group),{k:bucket() for k in output})
        which=['nonempty']
        if x['parent_ready'] and y['parent_ready']:which.append('common_parent_ready_nonempty')
        for key in which:
            add(g[key],bool(x['complete']),bool(y['complete']))
            add(output[key],bool(x['complete']),bool(y['complete']))
    return dict(baseline_rows=baseline['rows'],candidate_rows=candidate['rows'],
                baseline_layout=[baseline['make_rows'],baseline['finish_rows']],
                candidate_layout=[candidate['make_rows'],candidate['finish_rows']],
                groups_compared=len(by_group),per_group=by_group,**output)


def load_trace(path, data, rows):
    """Bind the discrete outputs to actual token channels before the source audit."""
    with np.load(path,allow_pickle=False) as z:
        first,second=[{k:z[f'{i}_{k}'] for k in ('active','pointers','rows')} for i in (0,1)]
        token,rel=z['token'],z['rel']
    if not np.isfinite(token).all() or not np.isfinite(rel).all():
        raise ValueError(f'nonfinite recorded tensor in {path.name}')
    if token.shape!=(len(data['a']),8,56):
        raise ValueError(f'unsupported retained Pair token shape {token.shape}')
    g=np.arange(len(token))[:,None]
    li,ri=first['pointers'].transpose(2,0,1);pi,qi=second['pointers'].transpose(2,0,1)
    if not (np.all((li>=0)&(li<data['a'].shape[1])) and np.all((ri>=0)&(ri<data['b'].shape[1])) and
            np.all((pi>=0)&(pi<8)) and np.all((qi>=0)&(qi<data['requests'].shape[1]))):
        raise ValueError('saved decoder pointer outside its categorical output range')
    for offset,width,values in ((32,2,first['active']),(34,8,li),(42,8,ri)):
        np.testing.assert_array_equal(token[...,offset:offset+width],np.eye(width)[values])
    # A/B -> committed physical row; only a retained Pair slot and Request
    # may supply the finish projection, even when the proposed witness is illegal.
    projected=np.concatenate((data['a'][g,li],data['b'][g,ri,1,None]),axis=-1)
    np.testing.assert_array_equal(first['rows'],projected)
    np.testing.assert_array_equal(token[...,50:55],projected)
    np.testing.assert_array_equal(token[...,-1],data['a_port'][g,li])
    selected=token[g,pi,50:55]
    expected=np.concatenate((selected[...,:2],data['requests'][g,qi,4,None],selected[...,3:]),-1)
    np.testing.assert_array_equal(second['rows'],expected)
    for indices in _groups(data).values():
        group=token[indices]
        np.testing.assert_array_equal(group,np.broadcast_to(group[0],group.shape))
    return metrics(data,first,second,rows,relation_pred=rel)


def _sha(path):
    return sha256(path.read_bytes()).hexdigest()


def replay_legacy(path):
    from eclass_ablation.data import dataset
    from eclass_ablation.data.runtime import CORPUS
    recorded=json.loads(path.read_text());base=path.parent/'legacy-width-traces'
    templates={t['id']:t for t in json.loads((CORPUS/'manifest.json').read_text())['templates'] if t['split']=='heldout'}
    reports={};comparisons={};hashes={}
    for tag,items in recorded['panels'].items():
        reports[tag]={};comparisons[tag]={}
        if set(templates)!=set(items):raise ValueError('legacy template panel incomplete')
        for tid,lanes in items.items():
            d=dataset('test',templates[tid]);reports[tag][tid]={};comparisons[tag][tid]={}
            if set(lanes)!={'1','2','4'}:raise ValueError('missing width in legacy comparison')
            for lane,stored in lanes.items():
                trace=base/f'{tid}-{tag}-{lane}.npz';hashes[trace.name]=_sha(trace)
                if hashes[trace.name]!=recorded['trace_sha256'][trace.name]:raise ValueError('legacy trace checksum mismatch')
                r=load_trace(trace,d,int(lane));reports[tag][tid][lane]=r
                assert [int(g['complete']) for g in r['run2']['per_graph']]==stored['predictions']
                assert r['both_complete_graphs']==stored['both_complete_graphs']
                for scope,key in [('run1','make'),('run2','finish')]:
                    for metric,value in stored[key].items():
                        if r[scope][metric]!=value:raise ValueError(f'legacy mismatch: {tag}/{tid}/{lane}/{scope}/{metric}')
            for lane in ('2','4'):
                comparisons[tag][tid][lane]=paired_layouts(reports[tag][tid]['1'],reports[tag][tid][lane])
    return dict(schema='eggfuse.width.trace-replay/v1',kind='legacy',results_sha256=_sha(path),
                trace_sha256=hashes,panels=reports,paired_layouts=comparisons)


def replay_formal(root):
    from eclass_ablation.data.runtime import CORPUS
    from study import fresh_panel
    path=root/'results.json';recorded=json.loads(path.read_text());traces=root/'traces'
    templates={t['id']:t for t in json.loads((CORPUS/'manifest.json').read_text())['templates'] if t['split']=='heldout'}
    reports={};comparisons={};hashes={}
    if not set(templates)<=set(recorded['panels']):raise ValueError('formal results lack held-out templates')
    def copy_integer_summary(actual,stored,which):
        for name,value in stored.items():
            if isinstance(value,(int,bool)) and (name not in actual or actual[name]!=value):
                raise ValueError(f'{which}/{name}: replay disagrees with stored value {value}')
    for tid,t in templates.items():
        d=fresh_panel(t);ids=set(map(int,d['group_id']))
        if ids!=set(range(720,752)) or len(d['a'])!=256:raise ValueError('unexpected formal source group range')
        reports[tid]={};comparisons[tid]={}
        for label,stored in recorded['panels'][tid].items():
            seed,layout,schedule=label.split('-',2);make,finish=map(int,layout.split('x'))
            trace=traces/f'{tid}-{label}.npz';hashes[trace.name]=_sha(trace)
            if 'trace_sha256' in recorded and trace.name in recorded['trace_sha256']:
                if recorded['trace_sha256'][trace.name]!=hashes[trace.name]:raise ValueError('formal trace checksum mismatch')
            r=load_trace(trace,d,(make,finish));reports[tid][label]=r
            copy_integer_summary(r['run1'],stored['r1'],label+'/run1')
            copy_integer_summary(r['run2'],stored['r2'],label+'/run2')
            for field,key in [('complete','complete_by_graph'),('parent_ready','parent_ready')]:
                if [int(g[field]) for g in r['run2']['per_graph']]!=stored[key]:
                    raise ValueError(f'{tid}/{label}: per-graph {field} differs')
            if r['origin_switch']!=stored['origin_switch'] or r['both_complete_graphs']!=stored['both_complete_graphs']:
                raise ValueError(f'{tid}/{label}: lineage or origin-switch score differs')
        for label,current in reports[tid].items():
            baseline=label.split('-',1)[0]+'-1x1-parallel'
            paired=paired_layouts(reports[tid][baseline],current)
            if paired!=recorded['paired'][tid][label]:
                raise ValueError(f'{tid}/{label}: paired comparisons differ from original evaluation')
            comparisons[tid][label]=paired
    if set(hashes)!={p.name for p in traces.glob('*.npz')}:
        raise ValueError('formal replay did not visit exactly the saved source traces')
    return dict(schema='eggfuse.width.trace-replay/v1',kind='formal-groups-720-751',
                results_sha256=_sha(path),trace_sha256=hashes,panels=reports,paired_layouts=comparisons)


def main():
    import argparse
    p=argparse.ArgumentParser();source=p.add_mutually_exclusive_group(required=True)
    source.add_argument('--legacy',type=Path,help='historical-width results JSON')
    source.add_argument('--formal',type=Path,help='formal output directory containing results.json and traces/')
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    result=replay_legacy(args.legacy) if args.legacy is not None else replay_formal(args.formal)
    if 'torch' in sys.modules or 'mlx.core' in sys.modules:raise RuntimeError('CPU trace replay imported a neural execution backend')
    result['audit_sha256']=_sha(Path(__file__))
    tmp=args.output.with_suffix('.tmp');tmp.write_text(json.dumps(result,separators=(',',':'))+'\n');tmp.replace(args.output)
    print('replayed',len(result['trace_sha256']),'saved two-Run traces with conserved duplicate attribution')

if __name__=='__main__':main()
