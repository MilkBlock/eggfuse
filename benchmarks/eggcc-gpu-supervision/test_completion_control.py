import unittest
from completion_control import capture_control,require_head_control


class CompletionControl(unittest.TestCase):
    def meta(self,stages):
        return dict(original_recipe=dict(rules=[dict(metadata=dict(source_set=s)) for s in stages]))

    def test_legacy_single_stage_is_explicitly_resolved(self):
        control=dict(saturate=dict(run='context'))
        self.assertEqual(capture_control(self.meta(['context','context'])),control)
        require_head_control({},control,['context'])
        with self.assertRaises(ValueError):require_head_control({},dict(run='context'),['context'])

    def test_multistage_requires_matching_contract(self):
        forward=[dict(saturate=dict(run=s)) for s in ['context','canon']]
        meta=self.meta(['context','canon'])
        with self.assertRaises(ValueError):capture_control(meta)
        self.assertEqual(capture_control(dict(meta,source_control=forward)),forward)
        require_head_control(dict(completion_control=forward),forward,['context','canon'])
        with self.assertRaises(ValueError):require_head_control(dict(completion_control=forward),forward[::-1],['context','canon'])
        with self.assertRaises(ValueError):require_head_control({},forward,['context','canon'])
        with self.assertRaises(ValueError):capture_control(dict(meta,source_control=dict(run='unknown')))

if __name__=='__main__':unittest.main()
