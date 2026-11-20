"""Typed port graphs derived from two certified Bake leaves and a declared effect-to-pivot connection."""
from copy import deepcopy
from dataclasses import dataclass,field

import torch
from torch import nn

WIDTH=12
EDGE_TYPES=4


@dataclass
class Graph:
    labels:list=field(default_factory=list)
    edges:list=field(default_factory=list)
    effects:list=field(default_factory=list)
    pivot:int=-1
    columns:dict=field(default_factory=dict)
    retained:list=field(default_factory=list)

    def node(self,*labels):
        self.labels.append(list(labels))
        return len(self.labels)-1

    def edge(self,a,b,kind):
        self.edges.append((a,b,kind))


def leaf_graph(program,entry):
    rules=program['recipe']['rules']
    r=rules[entry['consumer']];g=Graph()
    slots=[g.node('slot','sort:'+s['sort']['kind'],'type:'+s['sort']['name'],'def:'+('effect' if isinstance(s['definition'],int) else str(s['definition']))) for s in r['slots']]
    def atom(record,phase,operands):
        call=record.get('call',{})
        kind=record.get('kind','relation')
        operator=next(iter(call.values()),record.get('op','none'))
        node=g.node(phase,'operator:'+str(operator),'kind:'+kind)
        g.columns[node]=[]
        for i,arg in enumerate(operands):
            prop='slot-read' if 'slot' in arg else 'literal'
            port=g.node('port',phase,'index:'+str(i),prop)
            g.columns[node].append(port);g.edge(port,node,0)
            if 'slot' in arg:g.edge(slots[arg['slot']],port,1)
            elif 'literal' in arg:g.labels[port].extend(['sort:'+arg.get('sort',{}).get('kind','unknown'),'value:'+str(arg['literal'])])
        return node
    queries=[atom(op,'query',op.get('args',[])) for op in r['query']]
    g.pivot=queries[entry['pivot']];g.labels[g.pivot].append('anchor')
    for op in r['effects']:
        args=list(op.get('args',[]))
        if 'arg' in op:args.append(op['arg'])
        if 'value' in op:args.append(op['value'])
        node=atom(op,'effect',args);g.effects.append(node)
        if 'dst' in op:
            destination=g.node('port','effect-result','index:'+str(len(args)))
            g.edge(node,destination,0);g.edge(destination,slots[op['dst']],2)
            g.columns[node].append(destination)
    block=entry['block']
    for i,source in enumerate(block['inputs']):
        port=g.node('projected-input','index:'+str(i));g.retained.append(port)
        if source=='PortResult':
            local=block['port'];g.edge(g.columns[queries[local['atom']]][-1],port,2)
        elif 'Anchor' in source:g.edge(g.columns[g.pivot][source['Anchor']],port,2)
        else:raise ValueError(f'unsupported boundary source {source}')
    return g


def composite(left,right,effect):
    graph=deepcopy(left);offset=len(graph.labels)
    graph.labels+=deepcopy(right.labels)
    graph.edges.extend((a+offset,b+offset,k) for a,b,k in right.edges)
    graph.retained.extend(x+offset for x in right.retained)
    output=left.effects[effect];pivot=right.pivot+offset
    graph.labels[output].append('connected-output');graph.labels[pivot].append('connected-input')
    graph.edge(output,pivot,3)
    a,b=left.columns[output],right.columns[right.pivot]
    if len(a)!=len(b):raise ValueError('compiled port arity mismatch')
    for source,target in zip(a,b):graph.edge(source,target+offset,3)
    return graph,output,pivot


class Packed:
    def __init__(self,graphs,symbols):
        self.offsets=[];self.retained=[];names=[];edges=[];owner=[]
        for i,g in enumerate(graphs):
            offset=len(names);self.offsets.append(offset)
            self.retained.append([offset+x for x in g.retained])
            edges.extend((offset+a,offset+b,k) for a,b,k in g.edges)
            names.extend(g.labels);owner.extend([i]*len(g.labels))
        self.x=torch.zeros(len(names),len(symbols))
        for i,labels in enumerate(names):
            for label in labels:self.x[i,symbols[label]]=1
        self.owner=torch.tensor(owner);self.size=torch.bincount(self.owner)[:,None]
        self.edges=[]
        for kind in range(EDGE_TYPES):
            chosen=[(a,b) for a,b,k in edges if k==kind]
            a=torch.tensor([x for x,_ in chosen],dtype=torch.long)
            b=torch.tensor([y for _,y in chosen],dtype=torch.long)
            self.edges.extend([(a,b),(b,a)])
        self.degree=torch.bincount(torch.cat([b for _,b in self.edges]),minlength=len(names)).clamp_min(1)[:,None]

    def mean(self,h):
        return h.new_zeros(len(self.size),h.shape[1]).index_add_(0,self.owner,h)/self.size


class Encoder(nn.Module):
    def __init__(self,symbols):
        super().__init__()
        self.inputs=nn.Linear(len(symbols),WIDTH)
        self.edges=nn.ModuleList(nn.Linear(WIDTH,WIDTH,bias=False) for _ in range(2*EDGE_TYPES))
        self.local=nn.Linear(WIDTH,WIDTH)

    def forward(self,packed):
        hidden=self.inputs(packed.x).tanh()
        for _ in range(2):
            message=torch.zeros_like(hidden)
            for transform,(src,dst) in zip(self.edges,packed.edges):
                if len(src):message.index_add_(0,dst,transform(hidden[src]))
            hidden=(self.local(hidden)+message/packed.degree).tanh()
        return hidden


class Catalog:
    def __init__(self,program,joins):
        self.joins=joins
        leaves=[leaf_graph(program,e) for e in program['spine_blocks']['entries']]
        symbols=sorted({x for g in leaves for labels in g.labels for x in labels}|{'connected-input','connected-output'})
        self.symbols={name:i for i,name in enumerate(symbols)}
        self.leaves=leaves
        self.family=[program['spine_blocks']['entries'][left]['consumer'] for _,left,_,_ in joins]

    def subset(self,indices,kind):
        selected=[self.joins[j] for j in indices]
        if kind=='id':return None
        if kind=='graph':
            shapes=[composite(self.leaves[l],self.leaves[r],f) for _,l,f,r in selected];packed=Packed([x[0] for x in shapes],self.symbols)
            half=[];retained=[];wiring=[]
            for i,((_,left,_,right),(_,output,pivot)) in enumerate(zip(selected,shapes)):
                start=packed.offsets[i];split=len(self.leaves[left].labels)
                half.extend([2*i]*split+[2*i+1]*len(self.leaves[right].labels))
                retained.extend([[start+x for x in self.leaves[left].retained],
                                 [start+split+x for x in self.leaves[right].retained]])
                wiring.append((2*i,2*i+1,start+output,start+pivot))
            packed.owner=torch.tensor(half);packed.size=torch.bincount(packed.owner)[:,None];packed.retained=retained
            return packed,wiring
        leaves=sorted({j[v] for j in selected for v in (1,3)})
        packed=Packed([self.leaves[i] for i in leaves],self.symbols)
        connections=[]
        for _,left,port,right in selected:
            l,r=leaves.index(left),leaves.index(right)
            connections.append((l,r,packed.offsets[l]+self.leaves[left].effects[port],packed.offsets[r]+self.leaves[right].pivot))
        return packed,connections


class TemplateHead(nn.Module):
    def __init__(self,kind,catalog,seen):
        super().__init__()
        self.kind=kind;self.seen={template:i for i,template in enumerate(seen)}
        if kind=='id':self.ids=nn.Parameter(torch.randn(len(seen),WIDTH)*.1)
        else:
            self.encoder=Encoder(catalog.symbols)
            self.combine=nn.Linear(6*WIDTH,WIDTH)
        self.decode=nn.Linear(WIDTH,24)
        self.null=nn.Parameter(torch.zeros(2));self.row_latent=nn.Parameter(torch.zeros(2,8))

    def forward(self,units,pack):
        if self.kind=='id':
            ids=torch.cat([self.ids,self.ids.new_zeros(1,WIDTH)])
            vec=ids[[self.seen.get(i,len(self.seen)) for i in units]]
        else:
            packed,wiring=pack;h=self.encoder(packed);pooled=packed.mean(h)
            ports=torch.stack([h[keep].mean(0) if keep else h.new_zeros(WIDTH) for keep in packed.retained])
            ls,rs,out,anchor=map(list,zip(*wiring))
            vec=self.combine(torch.cat([pooled[ls],pooled[rs],h[out],h[anchor],ports[ls],ports[rs]],dim=1)).tanh()
        return self.decode(vec)

    def leaf_bank(self,catalog):
        """Cache every child template once. Future joins select an effect port and a pivot."""
        packed=Packed(catalog.leaves,catalog.symbols);h=self.encoder(packed)
        pooled=packed.mean(h)
        records=[]
        for i,(g,offset) in enumerate(zip(catalog.leaves,packed.offsets)):
            keep=packed.retained[i]
            retained=h[keep].mean(0) if keep else h.new_zeros(WIDTH)
            records.append((pooled[i].clone(),retained,h[offset+g.pivot].clone(),h[[offset+q for q in g.effects]].clone()))
        return records

    def compile_new(self,catalog,indices,bank):
        if self.kind!='compose':
            return self([catalog.joins[i][0] for i in indices],catalog.subset(indices,self.kind))
        features=[]
        for idx in indices:
            _,l,output,r=catalog.joins[idx];left=bank[l];right=bank[r]
            features.append(torch.cat([left[0],right[0],left[3][output],right[2],left[1],right[1]]))
        return self.decode(self.combine(torch.stack(features)).tanh())
