"""Reuse the shared constructor-program compiler for two same-witness Pair instances."""
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/'multi-row-cell'))
from catalog import Catalog


def compose():
    catalog=Catalog()
    names=('owner','handle','raw','payload','tag')
    source=catalog.add('Pair',names,[('pair',1,names,1)])
    i=catalog.compose(source,source,{'owner':'owner','tag':'tag'},'SharedBPair')
    c=catalog.compositions[i]
    target=catalog.templates[c.target]
    # Runtime stores boundary scalars densely. Internal constructor outputs
    # remain virtual. Convert physical program port to its boundary-array index.
    views=[[target.ports[k].binding for k in mapping[:5]] for mapping in
           (c.left_projection,c.right_projection)]
    return dict(fields=names,boundary_sources=c.boundary_sources,field_views=views,
                record_ports=[c.left_projection[-1],c.right_projection[-1]],
                operand_ports=[list(target.ports[k].arguments) for k in (c.left_projection[-1],c.right_projection[-1])])


if __name__=='__main__':
    (HERE/'plan.json').write_text(json.dumps(compose(),indent=2)+'\n')
