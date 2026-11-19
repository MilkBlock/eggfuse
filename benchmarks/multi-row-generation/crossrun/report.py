"""Write one record per arm, split and intervention for paired comparisons."""
import argparse
import csv
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('result',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();raw=json.loads(args.result.read_text());records=[]
    for label,panel in raw['panels'].items():
        arm,seed,split,mask=label.split('-')
        stage=panel['run2'];timed=raw['timings'][label]
        records.append(dict(arm=arm,seed=seed,split=split,mask=mask,
            complete=stage['nonempty_complete_graphs'],nonempty=stage['nonempty_graphs'],
            duplicates=stage['duplicates'],missing=stage['missing'],obligations=stage['obligations'],
            illegal=stage['illegal'],field_errors=stage['field_errors'],parent_field_errors=stage['parent_field_errors'],
            parent_ready=panel['supplied']['eligible'],complete_on_ready=panel['supplied']['complete'],
            twin_pairs_exact=panel.get('twins',{}).get('both_counterfactual_claims_exact',''),
            twin_pairs=panel.get('twins',{}).get('twin_pairs',''),median_ms=round(timed['median_ms'],5),
            timed_valid_nonempty_per_second=round(timed['complete_nonempty_graphs_per_second'],2)))
    with args.output.open('w',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=list(records[0]),delimiter='\t',lineterminator='\n');writer.writeheader();writer.writerows(records)

if __name__=='__main__':main()
