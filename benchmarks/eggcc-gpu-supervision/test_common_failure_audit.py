import unittest
from copy import deepcopy
from audit_common_failures import category,joined


def row(**changes):
    r=dict(identity='a',exact_target=False,stopped=True,initially_novel=True,emissions=[False]*2)
    r.update(changes);return r


def report():
    return dict(manifest_sha256='h',rounds=2,numerical_audit=dict(passed=True),cases=[row()])


class CommonFailureAudit(unittest.TestCase):
    def test_categories_distinguish_missing_and_wrong_completion(self):
        self.assertEqual(category(row()),'missed_initial_emission')
        self.assertEqual(category(row(emissions=[True,False])),'wrong_target_stopped')
        self.assertEqual(category(row(stopped=False,emissions=[True,True])),'still_active')
        self.assertEqual(category(row(exact_target=True)),'success')

    def test_join_requires_matching_complete_valid_audits(self):
        a=report();self.assertEqual(len(joined(a,deepcopy(a),'h')),1)
        for mutate in (lambda x:x.update(rounds=3),lambda x:x.update(manifest_sha256='bad'),lambda x:x['cases'].append(row()),lambda x:x['cases'].clear(),lambda x:x['numerical_audit'].update(passed=False)):
            b=deepcopy(a);mutate(b)
            with self.assertRaises(ValueError):joined(a,b,'h')

if __name__=='__main__':unittest.main()
