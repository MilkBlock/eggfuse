"""A shared typed declaration graph; opaque symbol spellings are optional model inputs."""
import hashlib
import json

import torch
from torch import nn

from actor import InstructionActor, ints, row_features
from catalog import Catalog, symbol


class SemanticCatalog(Catalog):
    def __init__(self, program):
        self.factors=[]
        self.names=[]
        self.constants=[]
        self.sorts={}
        self.table_uses=[]
        self.declarations={t['name']:t for t in program['recipe']['tables']}
        super().__init__(program)
        for desc in self.declarations.values():
            # The existing initial port is the unique declaration for this table.
            table=self.roots['initial',self.tables[desc['name']]]
            for i,sort in enumerate(desc['schema']):
                self.link(table,self.sort_node(sort),i+2)
        for node,name in self.table_uses:
            self.link(node,self.roots['initial',self.tables[name]],-1)

    def add(self, factors, name=None, literal=None):
        idx=len(self.factors)
        self.nodes.append(idx)
        self.factors.append(factors)
        if name is not None:
            self.names.append((idx,name))
        if literal is not None:
            data=json.dumps(literal,sort_keys=True,separators=(',',':')).encode()
            self.constants.append((idx,int.from_bytes(hashlib.sha256(data).digest()[:8],'little')))
        return idx

    def sort_node(self,sort):
        name=sort['name']
        if name not in self.sorts:
            self.sorts[name]=self.add(['sort-declaration','sort/'+sort['kind']],
                                      ('sort',name) if sort['kind']=='eq' else None)
        return self.sorts[name]

    def slot_node(self,label,sort):
        n=self.node(label)
        self.link(n,self.sort_node(sort),-2)
        return n

    def node(self,label):
        if isinstance(label,str):
            return self.add([label])
        kind,*args=label
        if kind=='input':
            name,=args
            return self.add([kind,'table/'+self.declarations[name]['kind']],('table',name))
        if kind=='literal':
            arg,=args
            n=self.add([kind,'sort/'+arg['sort']['kind']],literal=arg['literal'])
            self.link(n,self.sort_node(arg['sort']),-2)
            return n
        if kind in ('slot','operand','merge'):
            return self.add([kind]+[f'{kind}/{x}' for x in args])
        call,opkind=args
        factors=['instruction/'+kind]
        if opkind is not None:
            factors.append('operation/'+opkind)
        if call and 'primitive' in call:
            factors.append('primitive/'+call['primitive'])
        if call and 'table' in call:
            factors.append('table/'+self.declarations[call['table']]['kind'])
        n=self.add(factors)
        if call and 'table' in call:
            self.table_uses.append((n,call['table']))
        return n


class SemanticActor(InstructionActor):
    catalog_type=SemanticCatalog

    def __init__(self, vocabulary, names='structural', width=32):
        super().__init__(width=width,field_pointer=True)
        if names not in ('structural','named','renamed'):
            raise ValueError('unknown symbol mode')
        self.name_mode=names
        self.vocabulary={v:i+1 for i,v in enumerate(vocabulary)}
        self.static=nn.Embedding(len(vocabulary)+1,width,padding_idx=0)
        self.user_names=nn.Embedding(8192,width) if names!='structural' else None
        self.rename_seed=0

    def node_features(self,cat):
        device=self.static.weight
        roles=[(i,self.vocabulary.get(v,0)) for i,vs in enumerate(cat.factors) for v in vs]
        owner,kind=ints(device,roles).T
        h=device.new_zeros((len(cat.nodes),self.width)).index_add(0,owner,self.static(kind))
        if cat.constants:
            indices,values=zip(*cat.constants)
            literal=row_features([(v,) for v in values],self.width,device.device)
            h=h.index_add(0,ints(device,indices),literal)
        if self.user_names is not None and cat.names:
            indices,names=zip(*cat.names)
            # A seeded pseudonym of a name is shared at all its uses, and changes
            # on the next training exposure. These indices never identify ports.
            labels=[symbol((self.rename_seed,n) if self.name_mode=='renamed' else n) for n in names]
            h=h.index_add(0,ints(device,indices),self.user_names(ints(device,labels)))
        return h
