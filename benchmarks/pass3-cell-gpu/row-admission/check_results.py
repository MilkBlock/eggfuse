from pathlib import Path
import json


def check(root):
    data=json.loads((root/'results.json').read_text())
    assert len(data)==8
    for key,study in data.items():
        assert len(study)==13
        for label,v in study.items():
            if label=='exact':continue
            assert v['aligned'] and v['slots']==v['runs']*8 and v['issued']+v['idle']==v['slots']
            assert len(v['ms'])==len(v['cli_ms'])==6 and sum(v['by_row'])==v['neural']
            assert v['roots']+v['children']==v['neural']==v['rhs']-v['exact']
            if label.endswith(('static','transfer')):assert not v['duplicates']
            if label.startswith('2x4'):assert v['without_residual']['first_divergence']==1
            if not label.endswith('transfer') or label.startswith('1x8'):assert not v['transfers']
    print('Verified native source alignment and fixed eight-slot attribution for 96 row-placement arms.')


if __name__=='__main__':check(Path(__file__).resolve().parent)
