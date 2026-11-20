#!/usr/bin/env python3
"""Keep LLVM IR from the runtime crate in the exact Cargo invocation that links the benchmark."""
import os
import sys
args = sys.argv[1:]
if '--crate-name' in args and args[args.index('--crate-name')+1]=='eggfuse_cell_runtime':
    for i,arg in enumerate(args):
        if arg.startswith('--emit=') and 'link' in arg.split('=',1)[1].split(','):
            args[i] += ',llvm-ir'
os.execv(args[0],args)
