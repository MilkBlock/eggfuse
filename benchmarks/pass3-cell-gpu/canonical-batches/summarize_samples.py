"""Group leaf sample weights under identifiable ordered-effect and rebuild call paths."""
import argparse
from collections import Counter
from pathlib import Path
import re,json

def count(path):
    body=path.read_text().split('Call graph:\n')[1].split('\nTotal number')[0]
    stack=[];active=False;total=0;fees=Counter();roots=Counter();leaves=Counter();families=Counter()
    def flush():
        depth,weight,children,symbol=stack.pop();n=weight-children
        assert n>=0
        if not n:return
        names=[s[3] for s in stack]+[symbol];text='\n'.join(names)
        if 'Executor::execute' not in text and 'Executor::run' not in text:phase='outside_exec'
        elif any(q in text for q in ('repair_selected','Graph::repair::','complete_source_run')):phase='repair'
        elif any(q in text for q in ('Executor::apply','RhsFrame::execute','Graph::apply_write','joint_root::consume','Graph::construct_inner',
                                     'Graph::insert_constructor','Graph::set_inner','Stage::begin_step','Graph::start_cell')):phase='rhs'
        else:phase='other_exec'
        if phase in ('rhs','repair'):
            for label,parts in [('canonical_value',('value::root','value::canon','Parents::get','Parents::selected_root','Parents::source_root')),
                                ('constructor',('Graph::construct_inner','Graph::insert_constructor','Graph::activate')),
                                ('mutable_write',('Graph::apply_write','Graph::set_inner','Graph::set_function','Graph::merge_value','Graph::function_index')),
                                ('graph_store',('Graph::fact','Graph::find_repair_collision','Graph::row','Graph::live_table','Graph::lookup_canonical','Graph::slot','Graph::function')),
                                ('subscriptions',('subscribe_edges','subscribe_value','::subscriptions','::reverse_uses','::UseSet')),
                                ('root_recipe',('joint_root::','joint_merge::')),('hash_map',('hashbrown::','HashMap','HashTable','HashSet')),
                                ('btree',('btree::','BTreeMap','BTreeSet')),('allocation',('malloc','free','alloc::alloc::'))]:
                if not any(q in symbol for q in parts):continue
                break
            else:label='other_or_inlined'
            fees[(phase,label)]+=n
            if any('value::canon' in s or 'value::root' in s or 'Parents::selected_root' in s or 'Parents::source_root' in s for s in names):
                roots[phase]+=n
            normal=lambda x:re.sub(r'::h[0-9a-f]+$','',x)
            leaves[(phase,normal(symbol))]+=n
            # Attribute standard-library tree and allocator cost to the nearest identifiable
            # Cell routine on its stack. These counts are mutually exclusive per family.
            tag=None
            if any('collections::btree' in f or 'BTreeMap' in f or 'BTreeSet' in f for f in names):tag='btree'
            elif any('malloc' in f or 'free_small' in f or 'alloc::alloc::' in f for f in names):tag='alloc'
            if tag:
                caller=next((normal(v) for v in reversed(names) if 'eggfuse_cell_runtime::' in v),'inlined')
                families[(phase,tag,caller)]+=n
        else:fees[(phase,'all')]+=n
    for line in body.splitlines():
        m=re.match(r'^([ |+!:]*)\s*(\d+)\s+(.+)$',line)
        if not m:continue
        prefix,w,name=m.groups();depth=len(prefix);w=int(w);name=name.partition('  (in ')[0].strip()
        while stack and stack[-1][0]>=depth:flush()
        if not stack and 'Thread_' in name:
            active='main-thread' in name or total==0
            if active:total+=w
        if not active:continue
        if stack:stack[-1][2]+=w
        stack.append([depth,w,0,name])
    while stack:flush()
    assert sum(fees.values())==total>0
    return dict(main_thread=total,scopes={zone:dict((k,v) for (p,k),v in fees.items() if p==zone) for zone in ('rhs','repair','other_exec','outside_exec')},
                source_owners={p:{tag:[(s,n) for (q,t,s),n in sorted(families.items(),key=lambda i:-i[1]) if q==p and t==tag][:8] for tag in ('btree','alloc')} for p in ('rhs','repair')},
                named_canonical_subtree=roots,top={p:[(s,n) for (q,s),n in sorted(leaves.items(),key=lambda t:-t[1]) if q==p][:12] for p in ('rhs','repair')})
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('sample_dir',type=Path);p.add_argument('out',type=Path);a=p.parse_args()
    data={f.stem:count(f) for f in a.sample_dir.glob('*.sample')};assert len(data)==2
    a.out.write_text(json.dumps(data,indent=1)+'\n')
