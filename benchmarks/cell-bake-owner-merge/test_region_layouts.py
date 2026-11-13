import copy
import unittest
from region_layouts import analyze


def fixture():
    def source(cell, epoch):
        return dict(cell=cell, started_epoch=epoch, completed=True, retainers=0,
                    facts=[dict(op=0, born=epoch, epoch=epoch, hidden=False)])
    return dict(source_storage=dict(fact_lifecycle=dict(frames=[source(1, 3), source(2, 8)])),
        ownership_storage=dict(programs=[dict(fields=[[0]])],
            shapes=[dict(programs=[0, 0])],
            components=[dict(shape=0, frames=[1, 2], frame_codes=[7, 7], live_facts=2)]))


class Regions(unittest.TestCase):
    def test_instance_ids_and_epochs_do_not_duplicate_static_membership(self):
        r = fixture()
        extra = copy.deepcopy(r['source_storage']['fact_lifecycle']['frames'])
        for f in extra:
            f['cell'] += 10
            f['started_epoch'] += 20
            for fact in f['facts']:
                fact['born'] += 20
                fact['epoch'] += 20
        r['source_storage']['fact_lifecycle']['frames'] += extra
        r['ownership_storage']['components'].append(dict(shape=0, frames=[11, 12], frame_codes=[7, 7], live_facts=2))
        c = analyze(r)['counts']
        self.assertEqual((c['regions'], c['membership_layouts'], c['cross_epoch_regions']), (2, 1, 2))
        r['ownership_storage']['components'][1]['frame_codes'][0] = 9
        self.assertEqual(analyze(r)['counts']['membership_layouts'], 2)

    def test_missing_storage_keeps_wiring_obligation(self):
        r = fixture()
        r['source_storage']['fact_lifecycle']['frames'].pop()
        r['ownership_storage']['components'][0]['live_facts'] = 1
        self.assertEqual(analyze(r)['counts']['wiring_only_sources'], 1)

    def test_reject_inconsistent_liveness_and_duplicate_identity(self):
        r = fixture()
        r['ownership_storage']['components'][0]['live_facts'] = 1
        with self.assertRaises(ValueError):
            analyze(r)
        r = fixture()
        r['ownership_storage']['components'][0]['frames'] = [1, 1]
        with self.assertRaises(ValueError):
            analyze(r)


if __name__ == '__main__':
    unittest.main()
