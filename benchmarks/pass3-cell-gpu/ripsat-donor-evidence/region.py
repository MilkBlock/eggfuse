"""Copy exact source forms and ground the selected root rows from the donor snapshot."""
import json,re
from pathlib import Path
from hashlib import sha256
HERE=Path(__file__).resolve().parent
INPUT=HERE.parents[2]/'workloads/pass3/inputs'
TOKEN=re.compile(r';[^\n]*|\(|\)|"(?:\\.|[^"\\])*"|[^\s();"\x00]+',re.S)
def tokens(text):return [t.group() for t in TOKEN.finditer(text) if not t.group().startswith(';')]
def forms(parts):
    texts=[p.read_text() for p in parts];text=''.join(texts);depth=0
    def locate(pos):
        for p,part in zip(parts,texts):
            if pos<len(part):return p.name,part.count('\n',0,pos)+1
            pos-=len(part)
        raise ValueError('source position outside workload')
    for token in TOKEN.finditer(text):
        v=token.group()
        if v=='(':
            if not depth:start=token.start()
            depth+=1
        elif v==')':
            depth-=1
            if not depth:
                code=text[start:token.end()]
                location,line=locate(start);yield dict(path=location,line=line,code=code,sha256=sha256(code.encode()).hexdigest())
    if depth:raise ValueError(f'unbalanced joined workload: {parts}')

class Source:
    def __init__(self,donor):
        self.forms=list(forms([INPUT/name for name in ('common-prefix.egg',donor+'.eggpart','common-suffix.egg')]))
        self.rules={};self.decls={};self.sorts={};self.sets={};self.names={}
        for f in self.forms:
            t=tokens(f['code'])
            if len(t)<3:continue
            cmd=t[1]
            if cmd in ('rule','rewrite','birewrite'):
                if ':name' in t:
                    j=t.index(':name');name=json.loads(t[j+1].replace('\n','\\n'));self.rules[name]=f
                self.names[tuple(t)]=f
            elif cmd in ('constructor','function','relation'):self.decls[t[2]]=f
            elif cmd=='sort':self.sorts[t[2]]=f
            elif cmd=='ruleset':self.sets[t[2]]=f
    def rule(self,name):return self.rules.get(name) or self.names.get(tuple(tokens(name)))
    def entry(self,sample,mode,extra=None):
        p=sample['producer'];c=sample['consumer'];roles={'full':[p,c],'producer':[p],'consumer':[c],'augmented':[p,c]+(extra or [])}[mode]
        rules=[]
        for r in roles:
            cmd=self.rule(r['source_name'])
            if cmd is None:raise ValueError('No exact original .egg rule for '+r['source_name'])
            if cmd not in rules:rules.append(cmd)
        seed=roles[0];rows=[];ports={};asserts=[];source_values={};aliases=[]
        def alias(name,value):
            k=json.dumps(value,sort_keys=True)
            if 'Eq' in value and k in source_values:
                other=source_values[k];aliases.append([name,other,value])
                asserts.append('(union '+name+' '+other+')')
            else:source_values[k]=name
        for row in seed['rows']:
            i=row['atom'];tn=row['table']
            mutable=self.decls[tn]['code'].startswith('(function')
            args=[]
            for j,(term,value) in enumerate(zip(row['terms'],row['values'][:-1])):
                nm=f'input_{i}_c{j}';rows.append('(let '+nm+' '+term+')');ports[nm]=value;alias(nm,value);args.append(nm)
            nm=f'input_{i}'
            if mutable:
                term=row.get('result_term')
                if not term:raise ValueError('No graph-grounded result term for original function '+tn)
                rows.append('(let '+nm+' '+term+')')
                rows.append('(set ('+tn+' '+' '.join(args)+') '+nm+')')
            else:rows.append('(let '+nm+' ('+tn+' '+' '.join(args)+'))')
            ports[nm]=row['values'][-1];alias(nm,row['values'][-1])
        # Copy declarations from source, including dependencies referenced by merge expressions.
        content='\n'.join(rows+asserts+[f['code'] for f in rules])
        table_names=set(tokens(content)) & self.decls.keys()
        required=set(table_names)
        while True:
            extra={x for k in required for x in tokens(self.decls[k]['code'])[3:] if x in self.decls}
            if extra<=required:break
            required.update(extra)
        sort_names={k for t in required for k in tokens(self.decls[t]['code'])[3:] if k in self.sorts}
        while True:
            extra={x for k in sort_names for x in tokens(self.sorts[k]['code'])[3:] if x in self.sorts}
            if extra<=sort_names:break
            sort_names.update(extra)
        rulesets={x['ruleset'] for x in roles}
        selected=[*map(self.sorts.get,sort_names),*map(self.decls.get,required),*map(self.sets.get,rulesets),*rules]
        if None in selected:raise ValueError('Missing original declaration or ruleset')
        text='\n'.join(f['code'] for f in self.forms if f in selected)+'\n'+'\n'.join(rows+asserts)+'\n'
        return text,dict(scope_mode=mode,source_rules=[{k:v for k,v in f.items() if k!='code'} for f in rules],root_rows=seed['rows'],root_ports=ports,donor_aliases=aliases,selected_rules=[r['rule'] for r in roles],extra_rules=[r['rule'] for r in extra or []])

if __name__=='__main__':
    import argparse
    q=argparse.ArgumentParser();q.add_argument('origins',type=Path);q.add_argument('out',type=Path);q.add_argument('donor');q.add_argument('producer',type=int);q.add_argument('consumer',type=int);q.add_argument('mode');a=q.parse_args()
    x=json.loads((a.origins/(a.donor+'.json')).read_bytes());s=next(s for s in x['samples'] if s['producer']['rule']==a.producer and s['consumer']['rule']==a.consumer)
    txt,meta=Source(a.donor).entry(s,a.mode);a.out.mkdir(parents=True,exist_ok=True);(a.out/'entry.egg').write_text(txt)
    (a.out/'origin.json').write_text(json.dumps(dict(sample=s,profile=meta),indent=1)+'\n')
