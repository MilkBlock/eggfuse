"""Offline shared template/projection compiler; no per-instance graph expansion."""
from dataclasses import dataclass
from typing import Tuple
import numpy as np

# References are (row, token_position, template_port, generation).
# A leaf is (-1, opaque_value, 0, 0); (-2,0,0,0) is absent.
ABSENT=(-2,0,0,0)

def leaf(value):return (-1,int(value),0,0)
def ref(row,position,port,generation=1):return (int(row),int(position),int(port),int(generation))

@dataclass(frozen=True)
class Port:
    name:str
    binding:int=-1
    opcode:int=-1
    arguments:Tuple[int,...]=()
    run:int=0

@dataclass(frozen=True)
class Template:
    name:str
    parameters:Tuple[str,...]
    ports:Tuple[Port,...]

@dataclass(frozen=True)
class Composition:
    left:int
    right:int
    target:int
    # All target boundary values come from an original source parameter.
    boundary_sources:Tuple[Tuple[int,int],...]
    # A right parameter must name this left virtual port (after forwarding).
    wires:Tuple[Tuple[int,int],...]
    left_projection:Tuple[int,...]
    right_projection:Tuple[int,...]

class Catalog:
    def __init__(self):self.templates=[];self.compositions=[];self.arities={}

    def add(self,name,parameters,operations):
        arities=dict(self.arities)
        params=tuple(parameters);ports=[Port(p,binding=i) for i,p in enumerate(params)]
        names={p:i for i,p in enumerate(params)}
        if len(names)!=len(params):raise ValueError('duplicate parameter')
        for member,opcode,args,run in operations:
            if member in names or opcode<0 or run<1:raise ValueError('invalid constructor declaration')
            if any(a not in names for a in args):raise ValueError('non-topological member')
            if opcode in arities and arities[opcode]!=len(args):raise ValueError('opcode arity mismatch')
            arities[opcode]=len(args)
            ids=tuple(names[a] for a in args)
            if any(ports[a].run>run for a in ids):raise ValueError('consumer precedes producer Run')
            names[member]=len(ports);ports.append(Port(member,opcode=int(opcode),arguments=ids,run=int(run)))
        if len(ports)>32:raise ValueError('completion bitset capacity exceeded')
        self.arities=arities
        self.templates.append(Template(name,params,tuple(ports)));return len(self.templates)-1

    def port(self,template,name):
        return next(i for i,p in enumerate(self.templates[template].ports) if p.name==name)

    def compose(self,left,right,wires,name):
        a,b=self.templates[left],self.templates[right]
        # Map right parameter names to left port names. No observed endpoint rows.
        links={b.parameters.index(k):self.port(left,v) for k,v in wires.items()}
        ports=[Port(f'L.{p.name}',p.binding,p.opcode,p.arguments,p.run) for p in a.ports];params=[f'L.{p}' for p in a.parameters]
        sources=[(0,i) for i in range(len(a.parameters))]
        lm=list(range(len(a.ports)));rm=[]
        for old,p in enumerate(b.ports):
            if p.binding>=0:
                if p.binding in links:rm.append(lm[links[p.binding]])
                else:
                    rm.append(len(ports));ports.append(Port(f'R.{p.name}',binding=len(params)))
                    params.append(f'R.{p.name}');sources.append((1,p.binding))
            else:
                args=tuple(rm[v] for v in p.arguments)
                if any(ports[v].run>p.run for v in args):raise ValueError('composition exposes future producer')
                rm.append(len(ports));ports.append(Port(f'R.{p.name}',opcode=p.opcode,arguments=args,run=p.run))
        if len(ports)>32:raise ValueError('composed template exceeds supported bitset')
        self.templates.append(Template(name,tuple(params),tuple(ports)));target=len(self.templates)-1
        self.compositions.append(Composition(left,right,target,tuple(sources),tuple(sorted(links.items())),tuple(lm),tuple(rm)))
        return len(self.compositions)-1

    def arrays(self):
        t=len(self.templates);p=max(len(x.ports) for x in self.templates)
        b=max(1,max(len(x.parameters) for x in self.templates))
        ar=max(1,max(len(p.arguments) for x in self.templates for p in x.ports))
        kinds=np.zeros((t,p),np.int32);fields=np.full((t,p),-1,np.int32)
        args=np.full((t,p,ar),-1,np.int32);runs=np.zeros((t,p),np.int32)
        for i,template in enumerate(self.templates):
            for j,port in enumerate(template.ports):
                kinds[i,j]=1 if port.binding>=0 else 2
                fields[i,j]=port.binding if port.binding>=0 else port.opcode
                args[i,j,:len(port.arguments)]=port.arguments;runs[i,j]=port.run
        projections=np.full((max(1,2*len(self.compositions)),p),-1,np.int32)
        src=np.full((max(1,len(self.compositions)),b,2),-1,np.int32)
        wire=np.full((max(1,len(self.compositions)),b,2),-1,np.int32)
        plans=np.full((max(1,len(self.compositions)),3),-1,np.int32)
        for i,plan in enumerate(self.compositions):
            plans[i]=plan.left,plan.right,plan.target
            src[i,:len(plan.boundary_sources)]=plan.boundary_sources
            wire[i,:len(plan.wires)]=plan.wires
            projections[2*i,:len(plan.left_projection)]=plan.left_projection
            projections[2*i+1,:len(plan.right_projection)]=plan.right_projection
        return dict(kind=kinds,field=fields,args=args,run=runs,
                    port_count=np.array([len(x.ports) for x in self.templates],np.int32),
                    parameter_count=np.array([len(x.parameters) for x in self.templates],np.int32),
                    projection=projections,plan=plans,boundary_source=src,wires=wire)
