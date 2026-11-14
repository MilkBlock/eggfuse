import copy,unittest
from unittest.mock import patch
from finite_boundary_model import build,verify

class Models(unittest.TestCase):
    def fixture(self):
        eq=dict(kind='eq',name='E')
        recipe=dict(tables=[dict(name='F',kind='constructor',schema=[eq,eq])],rules=[dict(slots=[dict(sort=eq) for _ in range(3)],query=[dict(call=dict(table='F'),args=[dict(slot=0),dict(slot=1)]),dict(call=dict(table='F'),args=[dict(slot=1),dict(slot=2)])],effects=[dict(kind='union',args=[dict(slot=1),dict(slot=2)])])])
        snapshot=dict(rows=[dict(table='F',values=[dict(sort='E',eq='a'),dict(sort='E',eq='b')])])
        return recipe,snapshot

    def test_checked_model_and_tampered_totality(self):
        with patch('finite_boundary_model.validate',return_value=self.fixture()):
            cert,status=build({});self.assertTrue(verify({},cert)['valid'])
            broken=copy.deepcopy(cert);broken['facts'].pop()
            with self.assertRaises(ValueError):verify({},broken)
            broken=copy.deepcopy(cert);broken['domains']['E']=[]
            with self.assertRaises(ValueError):verify({},broken)

    def test_ground_rule_violation_is_rejected(self):
        from device_snapshot_import import identity
        recipe,snapshot=self.fixture()
        cert=dict(domains=dict(E=[0,1,2],i64=[3]),scalar_values={'3':0},other_scalar=3,
                  facts=[['F',[0,1]],['F',[1,2]],['F',[2,2]]],seed={identity(snapshot['rows'][0]['values'][0]):0,identity(snapshot['rows'][0]['values'][1]):1})
        with patch('finite_boundary_model.validate',return_value=(recipe,snapshot)):
            with self.assertRaisesRegex(ValueError,'rule union violated'):verify({},cert)

if __name__=='__main__':unittest.main()
