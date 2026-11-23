import unittest
from types import SimpleNamespace

import torch

from field_wiring import RouteBank, routes, rule_fields
from live_ripsat import RunPorts
from ripsat_boundary import fields


def atom(*args):
    return dict(call=dict(table='T'),args=[dict(slot=x) for x in args])


class FieldWiringTests(unittest.TestCase):
    def test_fields_follow_wired_return_and_copy_across_scopes(self):
        producer = dict(query=[atom(0,1)],effects=[
            dict(op='copy',dst=2,arg=dict(slot=0)),dict(op='let',dst=3,**atom(2))])
        consumer = dict(query=[atom(5,6),atom(4,5)],effects=[])
        layout=[(0,0,[(-1,0)]),(1,1,[(0,1),(-1,1)])]
        self.assertEqual(routes(layout,list(map(rule_fields,[producer,consumer]))),
                         ((),((0,0,1),)))

    def test_mutable_set_routes_only_keys_and_union_creates_no_field_alias(self):
        producer=dict(query=[atom(0,1)],effects=[
            dict(op='union',args=[dict(slot=0),dict(slot=1)]),
            dict(op='set',value=dict(slot=1),**atom(0))])
        consumer=dict(query=[atom(3,4),atom(4,3)],effects=[])
        layout=[(0,0,[(-1,0)]),(1,1,[(0,1),(-1,1)])]
        self.assertEqual(routes(layout,list(map(rule_fields,[producer,consumer]))),
                         ((),((0,0,1),)))

    def test_scores_keep_every_address_and_follow_row_order(self):
        bank=RouteBank(dict(bank=[[],[(0,1,0)]],uses=[[0,1]]))
        prior={0:[0,0xf0f0]}
        values=[(0xf0f0,), (0,), (0xf0f0,)]
        x=bank.features(0,1,prior,values)
        self.assertEqual(tuple(x.shape),(3,3))
        torch.testing.assert_close(x[0],torch.ones(3))
        self.assertLess(x[1,0].item(),1)
        torch.testing.assert_close(x,bank.features(0,1,prior,values[::-1]).flip(0))

    def test_shared_columns_end_at_the_snapshot_boundary(self):
        ports=[SimpleNamespace(table=5,hashes=(word,)) for word in (43,21,43)]
        snapshot=RunPorts(ports)
        rows,encoded=snapshot.encoded(5,32)
        self.assertIs(encoded,snapshot.encoded(5,32)[1])
        prior=[(17,43)]
        for a,b in zip(fields(prior,rows,32),fields(prior,rows,32,encoded),strict=True):
            torch.testing.assert_close(a,b,rtol=0,atol=0)
        bank=RouteBank(dict(bank=[[(0,1,0)]],uses=[[0]]))
        torch.testing.assert_close(bank.features(0,0,{0:prior[0]},rows),
                                   bank.features(0,0,{0:prior[0]},rows,encoded),rtol=0,atol=0)
        later=RunPorts([SimpleNamespace(table=5,hashes=(91,))])
        new_rows,new_encoding=later.encoded(5,32)
        self.assertEqual(new_rows,[(91,)])
        self.assertIsNot(encoded,new_encoding)


if __name__=='__main__':
    unittest.main()
