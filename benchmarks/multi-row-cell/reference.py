"""Independent expanded source-term oracle, used after device work only."""
from catalog import ref

class SourceGraph:
    def __init__(self,catalog,instances):
        # Preserve source instances. Never consume composition targets or redirects.
        self.catalog=catalog
        self.instances={(r,p):(t,tuple(bindings),1) for r,p,t,bindings,_ in instances}

    def term(self,address,run,stack=()):
        r,p,port,g=map(int,address);key=(r,p,port,g)
        if r==-1:return ('leaf',p) if port==0 and g==0 else None
        if key in stack or (r,p) not in self.instances:return None
        tpl,bindings,gen=self.instances[r,p]
        if g!=gen or port<0 or port>=len(self.catalog.templates[tpl].ports):return None
        node=self.catalog.templates[tpl].ports[port]
        if node.binding>=0:return self.term(bindings[node.binding],run,stack+(key,))
        if node.run>run:return None
        args=[self.term(ref(r,p,a,g),run,stack+(key,)) for a in node.arguments]
        if any(x is None for x in args):return None
        return ('constructor',node.opcode,tuple(args))


def packet_term(packet,address,length,stack=()):
    """Decode only GPU-produced view packets; never read the source program here."""
    r,t,p,g=map(int,address);key=(r,t,p,g)
    if r==-1:return ('leaf',t) if p==0 and g==0 else None
    if key in stack or r<0 or t<0:return None
    i=r*length+t
    if i>=packet['valid'].shape[0] or p<0 or p>=packet['valid'].shape[1]:return None
    if tuple(map(int,packet['query'][i,p]))!=key or not packet['valid'][i,p]:return None
    if packet['opcode'][i,p]==-1:return ('leaf',int(packet['value'][i,p]))
    arity=int(packet['arity'][i,p])
    args=[packet_term(packet,a,length,stack+(key,)) for a in packet['arguments'][i,p,:arity]]
    if any(x is None for x in args):return None
    return ('constructor',int(packet['opcode'][i,p]),tuple(args))
