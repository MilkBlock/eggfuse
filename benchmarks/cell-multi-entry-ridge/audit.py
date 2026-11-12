"""Read-only inventory of exact constructor completion contracts, not saturation."""
import argparse,collections,hashlib,json
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument('--history',type=Path,required=True);p.add_argument('--structures',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 d=json.loads(a.history.read_text());c=d['contracts'];counts=collections.Counter(d['event_units']);groups=collections.defaultdict(list)
 for impl in c['implementations']:groups[impl['class']].append(impl)
 multi=[]
 for cls,items in groups.items():
  if len(items)>1:multi.append(dict(completion_class=cls,structure=c['structures'][cls],implementations=items,event_counts={str(x['unit']):counts[x['unit']] for x in items}))
 s=json.loads(a.structures.read_text());sg=collections.defaultdict(list)
 for row in s['paths']:
  if 'structure' in row['result']:sg[json.dumps(row['result']['structure'],sort_keys=True)].append(row['path'])
 result=dict(scope='exact exported contracts; not whole-program saturation or logical mutation labels',history_sha256=hashlib.sha256(a.history.read_bytes()).hexdigest(),structures_sha256=hashlib.sha256(a.structures.read_bytes()).hexdigest(),history=dict(events=len(d['events']),dropped_events=d['dropped_events'],direct_truncated_parents=sum(e['truncated_parent'] for e in d['events']),parent_edges=sum(e['parent'] is not None for e in d['events']),implementations=len(c['implementations']),classes=len(c['structures']),typed_implementations=sum('ports'in x for x in c['implementations']),exact_extensions=sum(bool(x.get('extension'))for x in c['implementations']),transitions=len(c['transitions']),multi_groups=multi),new_analysis=dict(paths=len(s['paths']),counts=s['counts'],supported_paths=sum(map(len,sg.values())),distinct_structures=len(sg),multi_groups=[v for v in sg.values() if len(v)>1]))
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result['new_analysis'].items()},indent=2))
if __name__=='__main__':main()
