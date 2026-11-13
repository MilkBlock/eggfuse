import gzip
import tempfile
from pathlib import Path
import unittest
from collect_observed_corpus import role_features,split,read_bytes,digest
from test_cell_token_successors import rule,atom,make


class Corpus(unittest.TestCase):
    def test_archived_bytes_keep_original_fingerprint(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'program.json';path.write_bytes(b'{"sample": 1}')
            before=digest(path);path.with_suffix('.json.gz').write_bytes(gzip.compress(path.read_bytes()));path.unlink()
            self.assertEqual(read_bytes(path),b'{"sample": 1}');self.assertEqual(digest(path),before)

    def test_historical_holdouts_remain_held_out(self):
        self.assertEqual(split('010-dot-product'),'test')
        self.assertEqual(split('012-fact'),'test')
        self.assertEqual(split('016-gcd'),'validation')
        self.assertEqual(split('032-sum-bits'),'train')

    def test_copy_alias_has_same_effect_roles(self):
        direct=rule([atom('F',0,1)],[make('G',2,1)])
        copied=rule([atom('F',0,1)],[dict(kind='copy',dst=2,arg=dict(slot=1)),make('G',3,2)])
        inputs=[(0,('input',0)),(1,('input',1))]
        self.assertEqual(role_features(direct,inputs),role_features(copied,inputs))
        self.assertEqual(role_features(direct,inputs,True),role_features(copied,inputs,True))

    def test_actual_alias_groups_combine_roles(self):
        r=rule([atom('F',0,1)],[make('G',2,1)])
        distinct=role_features(r,[(0,('input',0)),(1,('input',1))])
        shared=role_features(r,[(0,('input',0)),(1,('input',0))])
        self.assertEqual(len(distinct),2);self.assertEqual(len(shared),1)
        self.assertEqual(sum(len(v['roles']) for v in distinct),len(shared[0]['roles']))

    def test_occurrence_roles_distinguish_swapped_scalar_attachments(self):
        r=rule([atom('F',0,1),atom('F',2,3)],[make('G',4,1),make('G',5,3)])
        left=[(0,('input',0)),(1,('literal','2')),(2,('input',1)),(3,('literal','3'))]
        right=[(0,('input',0)),(1,('literal','3')),(2,('input',1)),(3,('literal','2'))]
        self.assertEqual(role_features(r,left),role_features(r,right))
        self.assertNotEqual(role_features(r,left,True),role_features(r,right,True))

    def test_effect_result_is_not_confused_with_matched_input(self):
        r=rule([atom('F',0,1)],[make('G',1,0),make('G',2,1)])
        roles=role_features(r,[(0,('input',0)),(1,('input',1))])
        old=next(v for v in roles if v['port']==['input',1])
        self.assertTrue(all(v[0]=='query' for v in old['roles']))

if __name__=='__main__':unittest.main()
