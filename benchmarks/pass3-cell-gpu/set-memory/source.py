"""Isolate the actual eggcc load_after_write memory phase; keep probes separate."""
from pathlib import Path
import argparse
import re

ROOT=Path(__file__).resolve().parents[3]
PHASE='(run-schedule (repeat 6 (saturate always-run memory-helpers) memory))'
# Direct rendering of the Rust AST in eggcc's optimizations/memory.rs::load_after_write.
INPUT="""
(let $ctx (InFunc "dummy"))
(let $ty (TupleT (TCons (StateT) (TNil))))
(let $one (Const (Int 1) (Base (IntT)) $ctx))
(let $two (Const (Int 2) $ty $ctx))
(let $alloc (Alloc 0 $one (Get (Arg $ty $ctx) 0) (PointerT (IntT))))
(let $ptr (Get $alloc 0))
(let $written (Top (Write) $ptr $two (Get $alloc 1)))
(let $load (Bop (Load) $ptr $written))
(Bop (Print) (Get $load 0) (Get $load 1))
"""
OBSERVERS="""
(let $a (ES (set-of $one)))
(let $b (ES (set-of $two)))
(let $ab (ExprSet-insert $a $two))
(ExprSet-union $a $b)
(ExprSet-intersect $ab $b)
"""
def all_passes():
    # The frozen pass-3 dump expands the shared helpers() schedule. Reuse its
    # exact sequence for the two preceding CompilerPass::Schedule entries.
    last=(ROOT/'workloads/pass3/inputs/common-suffix.egg').read_text().splitlines()[-1]
    h=last.split('(repeat 3 ',1)[1].split(' passthrough state-edge-passthrough)',1)[0]
    first=f'(run-schedule (repeat 3 {h} passthrough state-edge-passthrough) (repeat 2 {h} swap-if) {h} rec-to-loop {h})'
    second=f'(run-schedule (repeat 3 {h} (saturate ivt-analysis) loop-inversion) {h})'
    return first+'\n'+second+'\n'+last+'\n'

def inline_input(observe):
    bindings={}
    result=[]
    for line in (INPUT+(OBSERVERS if observe else '')).splitlines():
        if not line: continue
        if line.startswith('(let '):
            _,name,expr=line[:-1].split(' ',2)
            bindings[name]=re.sub(r'\$\w+',lambda m:bindings[m[0]],expr)
        else:result.append(re.sub(r'\$\w+',lambda m:bindings[m[0]],line))
    return '\n'.join(result)+'\n'

def source(observe=False,full=False):
    return (ROOT/'workloads/pass3/inputs/common-prefix.egg').read_text()+inline_input(observe)+(all_passes() if full else '')+PHASE+'\n'

if __name__=='__main__':
    q=argparse.ArgumentParser();q.add_argument('out',type=Path)
    q.add_argument('--observe',action='store_true')
    q.add_argument('--full',action='store_true')
    args=q.parse_args();args.out.write_text(source(args.observe,args.full))
