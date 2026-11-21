import copy
import unittest
from fragments import occurrences


def ctor(op, dst, *args):
    return dict(op="let",kind="construct",call={"table":op},dst=dst,args=[{"slot":x} for x in args])


def compiled(effects):
    tables = [dict(name=n,kind="constructor",schema=[{"name":"E"}]*(arity+1))
              for n,arity in [("A",1),("B",1),("Pair",2)]]
    rule = dict(metadata={"source_set":"run"},effects=effects)
    return dict(recipe=dict(tables=tables,rules=[rule]))


def rooted(effects):
    return next(shape for shape,(_,_,_,ops) in occurrences(compiled(effects))
                if len(ops)==len([e for e in effects if e["op"]=="let"]))


class Projection(unittest.TestCase):
    def test_independent_order_copy_and_alpha(self):
        first = [ctor("A",10,0),ctor("B",11,1),ctor("Pair",12,10,11)]
        second = [ctor("B",50,21),dict(op="copy",dst=33,arg={"slot":20}),
                  ctor("A",51,33),ctor("Pair",52,51,50)]
        self.assertEqual(rooted(first),rooted(second))
        other = copy.deepcopy(first)
        other[-1]["args"].reverse()
        self.assertNotEqual(rooted(first),rooted(other))

    def test_shared_boundary_and_shared_return(self):
        independent = [ctor("A",10,0),ctor("B",11,1),ctor("Pair",12,10,11)]
        shared = [ctor("A",10,0),ctor("B",11,0),ctor("Pair",12,10,11)]
        self.assertNotEqual(rooted(independent),rooted(shared))
        shape=rooted([ctor("A",10,0),ctor("Pair",11,10,10)])
        self.assertEqual(shape[1][-1][-1], [["result",0],["result",0]])

    def test_effect_barrier(self):
        effects=[ctor("A",10,1),dict(op="union"),ctor("B",12,10)]
        self.assertEqual(list(occurrences(compiled(effects))),[])


if __name__=="__main__":
    unittest.main()
