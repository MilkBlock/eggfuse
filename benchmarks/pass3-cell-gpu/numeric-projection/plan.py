"""Recognize integer sum/copy/literal expressions feeding a single min-merged function."""
from pathlib import Path
import json
import numpy as np


def read(path):
    return json.loads(path.read_bytes())


def plan(program,image):
    source=read(program)['recipe'];tables={t['name']:t for t in source['tables']}
    def expression(arg,definitions,seen):
        if 'literal' in arg:
            if arg.get('sort',{}).get('name')!='i64':raise ValueError
            return ([],int(arg['literal']),[('literal',int(arg['literal']))])
        slot=arg['slot']
        if slot in seen:raise ValueError
        if slot not in definitions:return ([slot],0,[('slot',slot)])
        leaves=[];literal=0;code=[]
        for item in definitions[slot]:
            slots,n,ins=expression(item,definitions,seen|{slot});leaves+=slots;literal+=n;code+=ins
        if len(definitions[slot])==2:code.append(('add',0))
        return leaves,literal,code
    result=[]
    for rid,rule in enumerate(source['rules']):
        body=rule['effects'];sets=[op for op in body if op['op']=='set']
        if len(sets)!=1 or body[-1]!=sets[0]:continue
        target=sets[0];name=target['call'].get('table');tab=tables.get(name)
        if not tab or tab['merge']!='(min old new)' or tab['schema'][-1]['name']!='i64':continue
        definitions={}
        try:
            for atom in rule['query']:
                if 'primitive' not in atom['call']:continue
                call=atom['call']
                if call['primitive']!='+' or call['inputs']!=['i64','i64'] or call['output']!='i64':raise ValueError
                dst=atom['args'][-1]['slot'];definitions[dst]=atom['args'][:-1]
            for op in body[:-1]:
                if op['op']=='copy':definitions[op['dst']]=[op['arg']]
                elif op['op']=='let' and op['call'].get('primitive')=='+' and op['call']['inputs']==['i64','i64']:
                    definitions[op['dst']]=op['args']
                else:raise ValueError
            leaf,literal,code=expression(target['value'],definitions,set())
            if len(leaf)>4 or len(code)>16 or any(rule['slots'][i]['sort']['name']!='i64' for i in leaf):raise ValueError
        except (KeyError,ValueError):continue
        result.append(dict(rule=rid,table=name,slots=leaf,literal=literal,code=code))
    return result
