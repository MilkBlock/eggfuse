"""Read-only upper bound: count complete binding sets independent of fields.

Does not replace any predicted value, run the model, or feed corrected tokens to
later rounds. This is a frozen-binding diagnostic, not optimized-model accuracy.
"""
import sys,argparse,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'allocation'))
from diagnose import inspect


def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('output',type=Path);a=p.parse_args();result={}
    for path in sorted(a.root.glob('*/*.npz')):
        if path.stem.endswith(('-erase','-local')):continue
        if not path.stem.startswith(('iid-','triple_right-','four_right-')):continue
        result[str(path.relative_to(a.root))]=inspect(path)
    a.output.write_text(json.dumps(dict(scope='frozen-binding field-projection ceiling only; no output changes or corrected-history rollout',panels=result),indent=2)+'\n')
    for name,r in result.items():print(name,r['counts']['binding_set_exact_graphs'],r['counts']['field_only_failure_graphs'])

if __name__=='__main__':main()
