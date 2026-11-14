"""Reproducible finite-interface census from compiler rules, no real Run data."""
import argparse,hashlib,json
from pathlib import Path
from device_stage_models import select_ruleset
from finite_entry_domain import input_cases
from neural_cell_samples import samples
from neural_cell_chains import chains


def main():
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--ruleset',default='canon');p.add_argument('--rule',type=int,default=0);a=p.parse_args()
    source=json.loads(a.trace.read_text());recipe,manifest=select_ruleset(source.get('recipe',source),a.ruleset)
    if not 0<=a.rule<len(recipe['rules']):raise ValueError('invalid local rule index')
    inputs={i:input_cases(rule) for i,rule in enumerate(recipe['rules'])}
    data=samples(recipe,1,0,ordered=True,eq_targets=True,input_cases=inputs)
    one=dict(recipe,rules=[recipe['rules'][a.rule]]);records=[]
    samples(one,1,0,records,ordered=True,input_cases={0:inputs[a.rule]});transfers=[]
    legacy,_=chains(one,records,ordered=True)
    chain,coverage=chains(one,records,ordered=True,transfers=transfers,include_uncovered_transfers=True,finite_boundary=True)
    result=dict(scope='All typed source input partitions; bounded continuation census for one selected rule only',
                stage_manifest=manifest,rule=a.rule,source_samples=len(data['valid']),valid_sources=int(data['valid'].sum()),
                typed_input_partitions={str(i):len(v) for i,v in inputs.items()},
                legacy_positive=int(legacy['valid'].sum()),
                continuations=dict(samples=len(chain['valid']),positive=int(chain['valid'].sum()),transfer_records=len(transfers),coverage=coverage),
                recipe_sha256=hashlib.sha256(json.dumps(recipe,sort_keys=True).encode()).hexdigest(),
                limitations=['No prior source-root changes in boundary domain','No unspecified external facts or scalar domains','Not all ruleset interactions or arbitrary-depth closure','Compiled candidates are not runtime ownership transfers'])
    a.output.write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
