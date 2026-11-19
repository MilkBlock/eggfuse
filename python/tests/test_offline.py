"""Check the installed offline API on a same-field, wrong-parent example."""
import argparse
import json
from pathlib import Path
import sys
import tempfile

import numpy as np
import eggfuse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--binary', required=True, type=Path)
    parser.add_argument('--rules', required=True, type=Path)
    parser.add_argument('--plan', required=True, type=Path)
    args = parser.parse_args()
    source = args.rules.read_text() + '\n(run-schedule (seq (run make) (run finish)))\n'
    with tempfile.TemporaryDirectory() as td:
        output = Path(td)/'plan.json'
        plan = eggfuse.compile_projection(source, compiler_binary=args.binary, output_path=output)
        assert output.read_bytes() == args.plan.read_bytes()
    a = [[1,0],[1,0],[2,1],[3,1]]
    b = [[1,1],[4,0],[5,0],[6,0]]
    req = [[0,0,2],[2,1,1],[3,2,0],[1,3,3]]
    def blank():
        return {k:np.zeros((8,*width),dtype=np.int32) for k,width in
                [('active',()),('pointers',(2,)),('fields',(3,))]}
    first, second = blank(), blank()
    first['active'][:2] = 1
    first['pointers'][1,0] = 1
    first['fields'][:2] = [1,0,1]
    second['active'][0] = 1
    second['fields'][0] = [2,0,1]
    def verify():
        return eggfuse.verify_crossrun(plan,a,b,req,first,second)['run2']
    assert verify()['complete_graphs'] == 1
    second['pointers'][0,0] = 1
    wrong = verify()
    assert (wrong['complete_graphs'],wrong['illegal'],wrong['missing']) == (0,1,1)
    assert 'torch' not in sys.modules and 'mlx.core' not in sys.modules
    print(json.dumps({'installed_api':eggfuse.__all__,'plan_bytes_equal':True,
                      'accept_correct':True,'reject_wrong_parent':True,'gpu_framework_imported':False}))


if __name__ == '__main__':
    main()
