"""Attribute each main-thread sample exactly once using its complete call stack."""
import argparse
from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import re


@dataclass
class Frame:
    depth: int
    weight: int
    children: int
    name: str


def classify(stack):
    text='\n'.join(stack)
    inside='Executor::execute' in text or 'Executor::run' in text
    if not inside:
        for term,label in [('Graph::new','initial_graph'),('Program::clone','initial_graph'),
                           ('Executor::new','initial_graph'),('write_export','graph_export'),
                           ('Executor::report','report'),('::report','report'),
                           ('::configure','model_setup'),('use_single_witness','model_setup'),
                           ('read_nocancel','blocked_on_request'),('__read','blocked_on_request'),
                           ('__write','response_io')]:
            if term in text:return ('outside_execute',label)
        if stack[-1] in ('read','write'):
            return ('outside_execute','blocked_on_request' if stack[-1]=='read' else 'response_io')
        return ('outside_execute','other_load_report_drop_or_io')
    # Choose the nearest identifiable execution owner for an allocation/primitive in its subtree.
    # More specific symbol matches within each frame precede enclosing provider labels.
    for symbol in reversed(stack):
        for term,label in [('joint_root::','root_recipe'),('joint_merge::','merge_recipe'),
                           ('single_witness::Trial::features','single_features'),
                           ('single_witness::Model::score','single_score'),
                           ('single_witness::Trial::check','single_verification'),
                           ('single_witness::VerifiedRows::','single_verification'),
                           ('single_witness::RowInput::','single_score'),
                           ('single_witness::Trial::commit','single_commit'),
                           ('single_witness::Trial::generate','single_generation'),
                           ('ordinary_witness::','multi_witness'),
                           ('transfer_audit::','audit_hook'),
                           ('publish_finished_tables','publication'),('publish_batch','publication'),
                           ('update_change','publication'),('change_batch','publication'),
                           ('entry_schedule::Scheduler','entry_schedule'),('commit_union_batch','source_repair'),
                           ('complete_source_run','source_repair'),('::repair','source_repair'),
                           ('::rebuild','source_repair'),
                           ('stage_spine::','spine'),('::dedup_bindings','binding_dedup'),
                           ('Executor::apply','ordered_rhs'),('cell::apply','ordered_rhs'),
                           ('cell::eval::','ordered_rhs'),('Graph::apply_write','graph_write'),
                           ('Graph::set_inner','graph_write'),('Graph::activate','graph_write'),
                           ('::construct','graph_write'),('::set_function','graph_write'),
                           ('Executor::matches','other_matching'),('::matches_before','other_matching'),
                           ('Executor::probe','other_matching'),('Executor::run','run_self'),
                           ('Executor::execute','outer_schedule')]:
            if term in symbol:return ('execute',label)
    return ('execute','unattributed')


def attribute(path):
    body=path.read_text().split('Call graph:\n')[1].split('\nTotal number')[0]
    stack=[]; fees=Counter(); leaves=Counter(); scopes=Counter(); active=False; root=0
    def pop():
        node=stack.pop()
        count=node.weight-node.children
        if count<0:raise ValueError(f'child counts exceed {node}')
        if count:
            names=[x.name for x in stack]+[node.name]
            owner=classify(names);fees[owner]+=count
            leaves[(owner[0],owner[1],node.name)]+=count
            if owner[0]=='execute':
                for name in ('Store::seal_raw','joint_root::bind','Trial::generate','Store::emit_stack',
                             'Programs::resume_tokens','Scheduler::batches','Graph::repair_selected','RhsFrame::execute'):
                    if any(name in frame for frame in names):scopes[name]+=count
    for line in body.splitlines():
        m=re.match(r'^([ |+!:]*)\s*(\d+)\s+(.+)$',line)
        if not m:continue
        prefix,count,tail=m.groups();depth=len(prefix);count=int(count)
        name=tail.partition('  (in ')[0].strip()
        while stack and stack[-1].depth>=depth:pop()
        if 'Thread_' in name and not stack:
            active='main-thread' in name or root==0
            if active:root+=count
        if not active:continue
        if stack:stack[-1].children+=count
        stack.append(Frame(depth,count,0,name))
    while stack:pop()
    assert sum(fees.values())==root and root>0,(path,root,sum(fees.values()))
    return dict(main_thread_samples=root,inclusive_scopes=dict(scopes),
                categories={zone:{k:v for (z,k),v in fees.items() if z==zone}
                            for zone in ('execute','outside_execute')},
                top_symbols=[dict(region=z,category=k,symbol=name,samples=v)
                             for (z,k,name),v in leaves.most_common(25)])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('out',type=Path)
    a=p.parse_args()
    report={f.stem:attribute(f) for f in sorted(a.directory.glob('*.sample'))}
    assert report
    timing_path=a.directory/'timing.json'
    if timing_path.is_file():
        captures=json.loads(timing_path.read_text())
        assert captures.keys()==report.keys()
        for label,record in captures.items():
            case=label.rsplit('-',1)[0]
            assert record['state_sha']==captures[case+'-vanilla']['state_sha']
            report[label]['state_sha']=record['state_sha']
            report[label]['completed_requests']=len(record['inference_and_roundtrip_ms'])
    a.out.write_text(json.dumps(report,indent=2)+'\n')
