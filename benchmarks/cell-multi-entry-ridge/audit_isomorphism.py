"""Exhaustive color-preserving hypergraph isomorphism on small flat contracts."""
import argparse,collections,itertools,json,hashlib,math
from pathlib import Path

def canonical(colors,facts,active=None):
 active=list(range(len(colors))) if active is None else sorted(active)
 blocks=collections.defaultdict(list)
 for i in active:blocks[colors[i]].append(i)
 order=sorted(blocks);best=None;bestmap=None;offsets={};offset=0
 for color in order:offsets[color]=offset;offset+=len(blocks[color])
 permutations=math.prod(math.factorial(len(v)) for v in blocks.values())
 if permutations>1000000:raise ValueError('exhaustive permutation budget exceeded')
 for choices in itertools.product(*(itertools.permutations(blocks[c]) for c in order)):
  mapping={old:offsets[c]+i for c,block in zip(order,choices) for i,old in enumerate(block)}
  edges=tuple(sorted((fact['table'],tuple(mapping[p]for p in fact['columns']))for fact in facts))
  key=(tuple((c,len(blocks[c]))for c in order),edges)
  if best is None or key<best:best,bestmap=key,mapping
 return best,bestmap,permutations

def main():
 p=argparse.ArgumentParser();p.add_argument('--history',type=Path,required=True);p.add_argument('--structures',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();h=json.loads(a.history.read_text());s=json.loads(a.structures.read_text());sources=[]
 for impl in h['contracts']['implementations']:
  shape=h['contracts']['structures'][impl['class']]
  if 'colors'in shape:sources.append(('history',impl['unit'],shape,impl['source_path']))
 for i,row in enumerate(s['paths']):
  if row['result']['kind']=='flat':sources.append(('current',i,row['result']['structure'],row['path']))
 groups=collections.defaultdict(list)
 for source,unit,shape,path in sources:
  # Stage unions/effect boundaries cannot be discarded into a flat key.
  if shape.get('terminal_unions') or shape.get('constructor_unions'):continue
  key,mapping,count=canonical(shape['colors'],shape['completed'])
  assumptions=shape['assumptions'];used={p for f in assumptions for p in f['columns']}
  entry,_,_=canonical(shape['colors'],assumptions,used)
  groups[key].append(dict(source=source,unit=unit,path=path,entry_key=entry,completion_map=mapping,permutations=count,assumptions_in_completion=[dict(table=f['table'],columns=[mapping[p]for p in f['columns']])for f in assumptions]))
 multi=[]
 for key,rows in groups.items():
  if len(rows)>1:
   types=len({json.dumps(x['entry_key'])for x in rows});multi.append(dict(completion=key,entry_types=types,implementations=rows))
 result=dict(scope='exact completed-only flat hypergraph canonicalization; original assumptions retained separately; no saturation claim',source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in (a.history,a.structures)},flat_records=len(sources),distinct_completed_shapes=len(groups),multi_groups=multi,nonisomorphic_entry_groups=sum(g['entry_types']>1 for g in multi))
 a.output.write_text(json.dumps(result,indent=2)+'\n');print('records',len(sources),'groups',len(groups),'multi',len(multi),'nonisomorphic',result['nonisomorphic_entry_groups'])
 for g in multi:print(g['entry_types'],[(r['source'],r['unit'],r['path'])for r in g['implementations']])
if __name__=='__main__':main()
