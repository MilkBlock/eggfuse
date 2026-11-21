"""Generate a genuinely saturated foreign graph with the same cardinalities as the donor graph."""
import argparse
import json
from pathlib import Path
import subprocess

def generate(real, root, exporter):
    root.mkdir(parents=True, exist_ok=False)
    source=(real/'entry.egg').read_text()
    assert '(Single' in source and 'ForeignSingle' not in source
    (root/'entry.egg').write_text(source.replace('Single','ForeignSingle'))
    subprocess.run([exporter, root/'entry.egg', root/'native'], check=True)
    a=json.loads((real/'native/ripen.json').read_bytes())
    b=json.loads((root/'native/ripen.json').read_bytes())
    assert b['ripen']['state']==a['ripen']['state']=='Saturated'
    assert b['saturated_rule_composition']==a['saturated_rule_composition']
    ga=json.loads((real/'native/saturated-rule-composition.json').read_bytes())
    gb=json.loads((root/'native/saturated-rule-composition.json').read_bytes())
    assert ga['rows']!=gb['rows']
    assert [len(x['values']) for x in (ga,gb)]==[a['saturated_rule_composition']['values']]*2
    assert [len(x['rows']) for x in (ga,gb)]==[a['saturated_rule_composition']['facts']]*2

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('sample','output','exporter'):p.add_argument(k,type=Path)
    a=p.parse_args();generate(a.sample,a.output,a.exporter)
