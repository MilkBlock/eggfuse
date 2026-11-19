"""Zero-shot lane-width sensitivity of Figure 20 checkpoints and learned positions."""
import argparse
from functools import partial
import importlib.util
import json
from pathlib import Path
import statistics
import sys
import time

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
FIG20 = HERE.parent / 'eclass_ablation'
# The checkpoint owns its complete original AliasSystem, including its eight
# absolute slot embeddings. Only the unweighted stage scheduler is substituted.
sys.path.insert(0, str(FIG20))
from evaluate import audit_trace, combine, host, run_bulk, subset
from fit import AliasSystem, SEEDS, device, digest, study, transfer
from data import audit, dataset, paired_controls

LANES = (1, 2, 4)


def scheduler():
    spec = importlib.util.spec_from_file_location('width_grouping', HERE/'model.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.grouped_stage


def verify_replay(new, old):
    stages, token, rel = new
    differences = {}
    for index, stage in enumerate(stages):
        for key, arr in stage.items():
            original = old[f'{index}_{key}']
            differences[f'{index}_{key}'] = int(np.count_nonzero(arr != original))
    hard = np.array_equal(stages[0]['active'], old['0_active']) and not any(differences.values())
    semantic = int(np.count_nonzero(rel.argmax(-1) != old['rel'].argmax(-1)))
    # The printed tolerance is diagnostic. Acceptance requires exact discrete
    # pointer, activation, emitted field and classifier outputs throughout.
    result = dict(disagreements=differences, relation_disagreements=semantic,
                  token_bitwise_equal=bool(np.array_equal(token, old['token'])),
                  token_max_abs=float(np.abs(token-old['token']).max()),
                  relation_max_abs=float(np.abs(rel-old['rel']).max()),
                  relation_bitwise_equal=bool(np.array_equal(rel, old['rel'])))
    if not hard or semantic:
        raise ValueError(f'grouped 1x8 disagreed with frozen Figure 20 trace: {result}')
    return result


def summarize(d, output):
    stages, token, rel = output
    report, truth, eq = audit_trace(d, stages, token, rel)
    controls = paired_controls(d, *stages, eq)
    # Counts come from the original CPU semantics including external congruence.
    def counts(stage):
        return {k:v for k,v in stage.items() if k != 'per_graph'}
    return dict(make=counts(report['run1']), finish=counts(report['run2']),
                predictions=[int(r['complete']) for r in report['run2']['per_graph']],
                both_complete_graphs=report['both_complete_graphs'],
                relation_tests=int(truth.size), relation_correct=int((eq==truth).sum()),
                pairs={group:{k:items[k] for k in ('same_class_origin_switch_post', 'same_class_origin_switch_external')}
                       for group,items in controls.items()})


def benchmark(m, select, d, table, ids, dev, bulk):
    ids = np.array(ids)
    times = {r:[] for r in LANES}
    saved = {r:[] for r in LANES}
    for r in LANES:
        select(r)
        for i in ids[:3]:
            m(*transfer(d, slice(i,i+1), dev), table)
            torch.mps.synchronize()
    for num, i in enumerate(ids):
        # Python scheduler selection is an experimental intervention, outside
        # each timer. Transfer, both neural Runs, output and sync are timed.
        for r in LANES[num%len(LANES):] + LANES[:num%len(LANES)]:
            select(r)
            start = time.perf_counter_ns()
            result = m(*transfer(d,slice(i,i+1),dev), table)
            torch.mps.synchronize()
            times[r].append((time.perf_counter_ns()-start)/1e6)
            saved[r].append(result)
    result = {}
    for r in LANES:
        out = combine([host(x) for x in saved[r]])
        checked,_,_ = audit_trace(subset(d,ids),*out)
        same = all(np.array_equal(out[0][stage][k],bulk[r][0][stage][k][ids])
                   for stage in range(2) for k in out[0][stage])
        wins = checked['run2']['nonempty_complete_graphs']
        result[str(r)] = dict(samples_ms=times[r], median_ms=statistics.median(times[r]),
                              successes=int(wins),graphs=len(ids), matches_bulk_discrete=bool(same),
                              complete_nonempty_per_second=wins*1000/sum(times[r]))
    return result


def main():
    p = argparse.ArgumentParser();p.add_argument('fig20_root', type=Path);p.add_argument('output', type=Path)
    args = p.parse_args()
    grouped_stage = scheduler();dev=device();_,_,held,schema=study()
    original = json.loads((args.fig20_root/'results.json').read_text())
    paired = json.loads((args.fig20_root/'paired-controls.json').read_text())
    traces = args.output.parent/'legacy-width-traces';traces.mkdir(parents=True,exist_ok=True)
    report={}; samples={}; replay={}; hashes={}
    with torch.inference_mode():
        for seed in SEEDS:
            tag=f'pairwise-{seed}';directory=args.fig20_root/tag;weight=directory/'final.pt'
            fit=json.loads((directory/'fit.json').read_text());hashes[tag]=digest(weight)
            assert fit['weight_sha256']==hashes[tag]
            with torch.inference_mode(False):
                m=AliasSystem(schema,seed)
                m.load_state_dict(torch.load(weight,map_location='cpu',weights_only=True),strict=True)
                m=m.to(dev).eval()
            require_dims=(m.decoder.slots,m.decoder.position.weight.shape[0],m.decoder.source_position.weight.shape[0])
            if require_dims!=(8,8,8):raise ValueError('expected the two original learned eight-position tables')
            def select(r):
                m.decoder._stage=partial(grouped_stage,m.decoder,rows=r,schedule='parallel')
            report[tag]={};samples[tag]={};replay[tag]={}
            for t in held:
                tid=t['id'];d=dataset('test',t)
                bank=schema.bank(t,'pairwise',dev);table=m.encoder.frozen_bank(bank)
                bulk={};panel={};reference_path=args.fig20_root/'traces'/f'{tid}-{tag}.npz'
                assert paired['trace_hashes'][reference_path.name]==digest(reference_path)
                for r in LANES:
                    select(r);bulk[r]=run_bulk(m,d,table,dev)
                    if r==1:
                        with np.load(reference_path,allow_pickle=False) as old:
                            replay[tag][tid]=verify_replay(bulk[r],old)
                    stats=summarize(d,bulk[r]);panel[str(r)]=stats
                    if r==1 and stats['predictions']!=original['reports'][tid][tag]['complete']:
                        raise ValueError('grouped 1x8 must replay every prior per-graph hard decision')
                    st,tok,rel=bulk[r]
                    np.savez_compressed(traces/f'{tid}-{tag}-{r}.npz',token=tok,rel=rel,
                        **{f'{index}_{k}':v for index,frame in enumerate(st) for k,v in frame.items()})
                report[tag][tid]=panel
                ids=original['timings'][tid]['indices']
                samples[tag][tid]=dict(indices=ids,widths=benchmark(m,select,d,table,ids,dev,bulk))
                print(tag,tid,[panel[str(r)]['finish']['nonempty_complete_graphs'] for r in LANES],flush=True)
    aggregate={}
    for tag,templates in report.items():
        totals={};aggregate[tag]=totals
        for r in LANES:
            records=[p[str(r)] for p in templates.values()]
            values={stage:{k:sum(p[stage][k] for p in records) for k in records[0][stage]} for stage in ('make','finish')}
            values['both_complete_graphs']=sum(p['both_complete_graphs'] for p in records)
            values['relation_correct']=sum(p['relation_correct'] for p in records)
            values['relation_tests']=sum(p['relation_tests'] for p in records)
            values['pairs']={group:{k:{v:sum(p['pairs'][group][k][v] for p in records) for v in counters}
                                     for k,counters in items.items()} for group,items in records[0]['pairs'].items()}
            base=[p['1']['predictions'] for p in templates.values()];new=[p[str(r)]['predictions'] for p in templates.values()];diff=np.asarray(new)-np.asarray(base)
            values['gained_vs_old']=int(np.sum(diff==1));values['lost_vs_old']=int(np.sum(diff==-1));totals[str(r)]=values
    result=dict(scope='Frozen Figure 20 pairwise decoder. Only grouping of the previous generated token changes. Each combined slot retains its original absolute learned position.',
        original_weights=hashes,model_sha256=digest(FIG20/'model.py'),decoder_sha256=digest(HERE.parent/'port_ablation/decoder.py'),
        grouped_stage_sha256=digest(HERE/'model.py'),legacy_sha256=digest(Path(__file__)),
        original_result_sha256=digest(args.fig20_root/'results.json'),original_trace_manifest_sha256=digest(args.fig20_root/'paired-controls.json'),
        torch=torch.__version__,panels=report,timing=samples,one_row_replay=replay,totals=aggregate,
        trace_sha256={f.name:digest(f) for f in sorted(traces.glob('*.npz'))})
    tmp=args.output.with_suffix('.tmp');tmp.write_text(json.dumps(result,separators=(',',':'))+'\n');tmp.replace(args.output)
    for tag,stats in aggregate.items():print(tag, {r:(s['finish']['nonempty_complete_graphs'],s['finish']['missing'],s['finish']['duplicates']) for r,s in stats.items()})


if __name__=='__main__':main()
