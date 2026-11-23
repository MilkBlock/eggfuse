"""Assemble the native anchor census, signed pointer diagnostics and live costs."""
import argparse
import csv
import gzip
import io
import json
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from statistics import median


def read(path):
    return json.loads(path.read_bytes())


@contextmanager
def ledger(path):
    with path.open('wb') as output, gzip.GzipFile(filename='', fileobj=output, mode='wb', mtime=0) as zipped:
        with io.TextIOWrapper(zipped, encoding='utf-8', newline='') as stream:
            yield csv.writer(stream, lineterminator='\n')


def run_metrics(required, misses):
    recall = [(n - misses[r]) / n for r, n in required.items() if n]
    return dict(nonempty=len(recall), complete=recall.count(1.), mean=sum(recall)/len(recall))


def assemble(root, raw, output, cases):
    output.mkdir(parents=True, exist_ok=True)
    summary = {}
    with (ledger(output/'anchors.csv.gz') as anchors, ledger(output/'missing.csv.gz') as missing,
          ledger(output/'recall.csv.gz') as recall):
        anchors.writerow(('case','run','rule','query_pivot','watermark','dirty','physical_anchors','empty','proofs',
                          'candidate_visits','discovery_ns','expand_ns','point_reads','token_alias_scores',
                          'score_ns','selector_ns'))
        missing.writerow(('case','arm','run','rule','teacher_commit','loss','first_depth','cause'))
        recall.writerow(('case','arm','run','required','distinct'))
        for name in cases:
            def result(suffix):
                return read(raw/f'{name}-{suffix}.json')
            ref = read(root/name/'capture.json')
            program = read(root/name/'program.json')['recipe']['rules']
            census = result('final-census')
            for key in ('state_sha','schedule','rhs','writes','resumes','events'):
                if census[key] != ref[key]:
                    raise ValueError(f'census differs on {name}/{key}')
            required = {run: step[4] for run, step in enumerate(ref['schedule'], 1)}
            historic = read(root/'alternate-proofs'/'root-calibration'/'opaque-parent'/'calibrated'/f'{name}.json')
            times = result('scores')
            by_pivot = {}
            for run, rid, role, count, _, score_ns, selector_ns in times['rows']:
                pivots = [i for i, atom in enumerate(program[rid]['query']) if 'table' in atom['call']]
                by_pivot[run,rid,pivots[role]] = (count,score_ns,selector_ns)
            totals = Counter()
            arity_totals = {}
            for run,rid,pivot,wm,semi,dirty,n,empty,proofs,visits,discovery,expand,_,_,_,points,_ in census['anchor_census']:
                scores = by_pivot.pop((run,rid,pivot),(0,0,0))
                if pivot is None and (n or proofs):
                    raise ValueError('unexpected table anchors on an empty LHS')
                anchors.writerow((name,run,rid,pivot,wm,int(dirty),n,empty,proofs,visits,discovery,expand,points,*scores))
                if proofs and not dirty:
                    raise ValueError('productive anchor omitted on idle rule')
                arity = sum('table' in atom['call'] for atom in program[rid]['query'])
                by_depth = arity_totals.setdefault(arity,Counter())
                by_depth.update(physical=n,empty=empty,proofs=proofs,point_reads=points,visits=visits,expand_ns=expand)
                totals.update(dict(physical=n,empty=empty,proofs=proofs,candidate_visits=visits,point_reads=points,
                                   discovery_ns=discovery,expand_ns=expand,alias_scores=scores[0],score_ns=scores[1],
                                   selector_ns=scores[2]))
            if by_pivot: raise ValueError(f'unaccounted neural roles: {len(by_pivot)}')
            case = summary[name] = dict(census=dict(totals),by_arity=arity_totals,required=ref['matches'],runs=ref['runs'],
                                        controls=result('controls'),semantics=ref['state_sha'],pointers={},
                                        scoring={k:times[k] for k in ('actor','recovery','seed','template_ns','encode_ns','history_ns')})
            for arm in ('historical-source','historical-delta','historical-oracle-source','source','delta','oracle'):
                file = raw/f'{name}-{arm}.json'
                data = read(file)
                lost = Counter()
                with file.with_suffix('.csv').open() as stream:
                    for row in csv.DictReader(stream):
                        missing.writerow((name,arm,*(row[k] for k in ('run','rule','teacher_commit','loss','first_depth','cause'))))
                        lost[int(row['run'])] += 1
                if sum(lost.values()) + data['distinct'] != ref['matches']:
                    raise ValueError('unbalanced teacher recall')
                for run, n in required.items():
                    recall.writerow((name,arm,run,n,n-lost[run]))
                if arm=='historical-source':
                    old = historic['result']
                    if data['actor'] != historic['weights_sha256'] or any(
                            required[int(r)]-lost[int(r)]!=row['recovered'] for r,row in old['by_run'].items()):
                        raise ValueError('historical Run recall or checkpoint did not reproduce')
                    data['original_paid']=old['issued']
                data.update(run_metrics(required,lost))
                case['pointers'][arm]=data
            for arm in ('historical-partition','final-empty','model'):
                data = result(arm)
                by_run=Counter()
                for run,_,count in data.pop('coverage_by_rule'):
                    by_run[run]+=count
                if sum(by_run.values())!=data['selected_commits'] or data['state_sha']!=ref['state_sha']:
                    raise ValueError('hybrid accounting or state mismatch')
                misses={run:n-by_run[run] for run,n in required.items()}
                if any(n<0 for n in misses.values()):raise ValueError('overcredited a selected anchor')
                data.update(run_metrics(required,misses))
                for run,n in required.items():recall.writerow((name,arm,run,n,by_run[run]))
                case[arm]=data
            control=case['final-empty']
            model=case['historical-partition']
            for counter in ('visits','point_reads'):
                if model['residual_'+counter]+model['selected_'+counter] != control['residual_'+counter]:
                    raise ValueError(f'partition changed total {counter} in {name}')
            case['reference_wall_median']=median(s['wall_seconds'] for s in case['controls']['samples'] if s['role']=='reference')
            case['oracle_wall_median']=median(s['wall_seconds'] for s in case['controls']['samples'] if s['role']=='replay')
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for arg in ('root','raw','output'):
        parser.add_argument(arg,type=Path)
    parser.add_argument('cases',nargs='+')
    opts=parser.parse_args()
    assemble(opts.root,opts.raw,opts.output,opts.cases)
