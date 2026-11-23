"""Lock the field reader on held programs before measuring the next program."""
import argparse
import json
from pathlib import Path

from alternate_proofs import digest
from higher_cell import read
from layout_credit_report import verify
from marginal_policy import splits


def totals(report):
    execution=report['execution']
    ledger=execution['ept']
    return dict(required=report['reference_commits'],signed=execution['counts']['accepted'],
                paid=execution['issued'],ops=sum(ledger['signed_external']+ledger['signed_internal']),
                complete_runs=sum(a==b for _,a,b in report['recall_by_nonempty_run']),
                held_complete=report['held_complete'],held_issued=report['held_issued'])


def lock(protocol_file, corpus, baseline, candidate, model, output):
    protocol=splits(protocol_file)
    sha=digest(model/'training.json')
    if read(model/'training.json')['protocol']!=digest(protocol_file):
        raise ValueError('wrong training protocol')
    records={}
    controls={}
    for arm,folder in [('base',baseline),('field',candidate)]:
        rows={}
        for name,program in protocol['validation'].items():
            case=corpus/name
            path=folder/(name+'.json')
            report=read(path)
            settings=[report[k] for k in ('mode','program','tape','binary','actor','policy','scorer','reader','catalog',
                                           'omit','attach','seed','recovery','reference_commits')]
            if (digest(case/'program.json')!=program or report['program']!=name or report['mode']!='native assist'
                    or report['tape']!=digest(case/'tape.json') or controls.setdefault(name,settings)!=settings
                    or report.get('field_reader')!=(sha if arm=='field' else None)):
                raise ValueError('validation arms or data do not match')
            verify(report,read(case/'exact.json'))
            rows[name]=dict(**totals(report),audit=digest(path))
        rates=[r['signed']/r['required'] for r in rows.values()]
        records[arm]=dict(programs=rows,worst=min(rates),macro=sum(rates)/len(rates),
                          paid_per_signed=sum(r['paid'] for r in rows.values())/sum(r['signed'] for r in rows.values()))
    base,field=records['base'],records['field']
    improved=(field['worst']>base['worst'] and field['macro']>=base['macro']
              and field['paid_per_signed']<=base['paid_per_signed'])
    result=dict(protocol=digest(protocol_file),field_reader=sha,selected='field' if improved else 'base',validation=records)
    if output.exists() and read(output)!=result:
        raise ValueError('existing validation lock differs')
    output.write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('protocol','corpus','baseline','candidate','model','output'):
        p.add_argument(k,type=Path)
    a=p.parse_args()
    lock(a.protocol,a.corpus,a.baseline,a.candidate,a.model,a.output)
