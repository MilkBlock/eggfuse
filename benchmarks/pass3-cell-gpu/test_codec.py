import unittest
from collections import Counter

from codec import canonical, encode, members, primitive


def table(name,sig):
    return dict(name=name,schema=[dict(name=s,kind='eq' if s=='Expr' else s) for s in sig])


class CellIngress(unittest.TestCase):
    def test_ports_provenance_visibility_and_permutation(self):
        ts=[table('Get',['Expr','i64','Expr']),table('Single',['Expr','Expr']),table('Alias',['Expr'])]
        eq=lambda v:dict(sort='Expr',eq=v)
        def fact(t,values,hidden=False):return dict(table=t,values=values,subsumed=hidden)
        get=fact('Get',[eq('x'),dict(sort='i64',value=0),eq('u')]);single=fact('Single',[eq('u'),eq('v')])
        for rows in ([get,single],[get,single,fact('Alias',[eq('u')],True)]):
            t,ins,s=encode(rows,ts)
            packet=dict(tables=ts,templates=t,instances=ins,symbols=s)
            decoded=[r for _,_,r in members(packet)]
            self.assertEqual(Counter(map(canonical,decoded)),Counter(map(canonical,rows)))
            self.assertEqual((t,ins,s),encode(list(reversed(rows)),ts))
            if len(rows)==2:
                self.assertEqual(t[0][1][1][0],-1) # use first member's result class
            else:
                self.assertTrue(all(len(prog)==1 for prog in t))
                self.assertEqual(sum(r['values'][-1]==eq('u') for r in decoded),2)
        with self.assertRaises(ValueError):encode([get,get],ts)

    def test_numeric_and_equality_signatures_are_distinct(self):
        def signature(op,kind,out):
            return {'primitive':op,'inputs':[kind,kind],'output':out}
        self.assertEqual(primitive(signature('!=','Expr','Unit'),{'Expr'}),'eq-id-!=')
        self.assertEqual(primitive(signature('!=','i64','Unit'),{'Expr'}),'!=')
        for args in [('+','String','String'),('!=','SetExpr','Unit'),('min','f64','f64')]:
            with self.assertRaises(ValueError):primitive(signature(*args),{'Expr'})

    def test_missing_argument_is_not_the_result_port(self):
        import torch
        # The example is intentionally asymmetric: same member, two ordered roles.
        from ports import mapping
        from pathlib import Path
        import tempfile
        from ports import train,load
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'port.pt';train(path);m=load(path,'mps')
            self.assertEqual(mapping(m,3,'mps').tolist(),[0,1,2])
            widths=torch.tensor([3,3],device='mps');q=torch.tensor([-1,2],device='mps')
            c=torch.arange(-1,4,device='mps')
            self.assertEqual(c[m(widths,q,c).argmax(-1)].tolist(),[2,-1])
