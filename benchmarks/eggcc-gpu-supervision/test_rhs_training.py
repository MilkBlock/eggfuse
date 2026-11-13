import unittest
import tempfile
from pathlib import Path
from collect_rhs_training import select,reusable_records,digest

class TrainingSelection(unittest.TestCase):
    def test_split_and_status_never_reassigned(self):
        def row(case,split,n,status='complete'):
            return dict(case=case,split=split,status=status,summary=dict(observed_bindings=n))
        manifest=dict(cases=[row('test','test',1),row('validation','validation',2),
            row('failed','train',1,'timeout'),row('large','train',9999),
            row('b','train',100),row('a','train',100),row('small','train',20)])
        self.assertEqual([e['case'] for e in select(manifest,200,2)],['small','a'])
        self.assertEqual([e['case'] for e in select(manifest,200,2,'validation')],['validation'])
        self.assertTrue(all(e['split']=='train' for e in select(manifest,200,20)))

    def test_selection_does_not_depend_on_manifest_order(self):
        rows=[dict(case=c,split='train',status='complete',summary=dict(observed_bindings=n))
              for c,n in [('b',30),('a',30),('c',10)]]
        self.assertEqual(select(dict(cases=rows),100,2),select(dict(cases=list(reversed(rows))),100,2))

    def test_reuse_requires_same_split_binary_source_and_immutable_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            trace=Path(directory)/'trace.json';links=Path(directory)/'links.json'
            trace.write_bytes(b'trace');links.write_bytes(b'links')
            row=dict(case='a',status='complete',split='train',trace=str(trace),links=str(links),
                trace_sha256=digest(b'trace'),links_sha256=digest(b'links'))
            previous=dict(manifest_sha256='source',binary_sha256='binary',partition='train',cases=[row])
            self.assertEqual(reusable_records(previous,'source','binary','train'),{'a':row})
            for source,binary,split in [('other','binary','train'),('source','other','train'),('source','binary','test')]:
                with self.assertRaisesRegex(ValueError,'provenance'):reusable_records(previous,source,binary,split)
            links.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'artifact'):reusable_records(previous,'source','binary','train')

if __name__=='__main__':unittest.main()
