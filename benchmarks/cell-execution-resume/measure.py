#!/usr/bin/env python3
"""Five-change checkpoint, reusing the frozen complete-process timing harness."""
import argparse
import json
import os
from pathlib import Path
import runpy


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('current','tag','historical','sum_program','ray_program','output'):
        p.add_argument(name,type=Path)
    a=p.parse_args();a.output.mkdir()
    harness=runpy.run_path(str(Path(__file__).resolve().parents[1]/'witness-prefix/measure.py'))
    harness['GROUPS']['cell_execution']=('cell_execution',)
    harness['GROUPS']['query_workers']=('query_workers',)
    os.environ.pop('CELL_CPU_PROGRESS',None);os.environ.pop('CELL_CPU_PROFILE',None)
    common=['--repair-ports','--entry-publications','--cell-absorption']
    parallel=['--query-workers','4','--parallel-residuals','--parallel-publication']
    for case,program,repeats in [('sum',a.sum_program,5),('ray',a.ray_program,3)]:
        lanes={name:{'runtime':str(binary.resolve()),'program':str(program.resolve()),'args':common+flags}
            for name,binary,flags in [
                ('tag4',a.tag,parallel),('historical4',a.historical,parallel),
                ('current_serial',a.current,[]),('current4',a.current,parallel),
                ('resumed4_g1',a.current,parallel+['--cell-execution-grain','1']),
                ('resumed4_g64',a.current,parallel+['--cell-execution-grain','64']),
            ]}
        manifest={'scope':'standalone Cell CPU; source-ordered Cell resumption checkpoint','lanes':lanes}
        (a.output/(case+'-manifest.json')).write_text(json.dumps(manifest,indent=2)+'\n')
        harness['measure'](manifest,a.output/case,repeats,1,90)


if __name__=='__main__':
    if not __debug__:raise SystemExit('run without Python -O')
    main()
