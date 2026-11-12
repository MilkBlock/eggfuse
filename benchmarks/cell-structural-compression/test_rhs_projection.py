import unittest
from analyze_rhs_projection import analyze


def fixture():
    e={'run':1,'rule':0,'cell':1,'union_revision':0,'values':[{'Eq':1}],
       'output_versions':[2],'facts':1,'updates':0,'union_requests':0,'constructor_requests':1}
    events=[e,{**e,'cell':2,'facts':0},{**e,'run':2,'cell':3,'facts':0},
            {**e,'run':2,'cell':4,'facts':0,'output_versions':[3]}]
    return {'all_saved_run_checks_equal':True,'program_sha256':'fixture','runs':2,
        'rhs_projection_trace':{'schema':'cell-rhs-projection-trace/v1','complete_archive':True,
        'trace':{'dropped':0,'unsupported_completions':0,'plans':[{'rule':0,'slots':[0],'tables':[1]}],'events':events}}}

class ProjectionTests(unittest.TestCase):
    def test_versions_and_runs_separate_candidates(self):
        r=analyze(fixture())['counts']
        self.assertEqual((r['first'],r['within_run'],r['cross_run']),(2,1,1))
        self.assertEqual(r['mutation_free_repeats'],2)
        self.assertEqual(analyze(fixture())['changed_revision_candidates']['table_version_changed'],1)
    def test_unknown_inputs_never_establish_reuse(self):
        f=fixture()
        for e in f['rhs_projection_trace']['trace']['events']:e['values']=None
        r=analyze(f)['counts'];self.assertEqual(r['unavailable_inputs'],4)
        self.assertNotIn('within_run',r)
    def test_incomplete_or_misaligned_archive_rejected(self):
        for which in ['drop','width']:
            f=fixture();trace=f['rhs_projection_trace']['trace']
            if which=='drop':trace['dropped']=1
            else:trace['events'][0]['output_versions']=[]
            with self.assertRaises(ValueError):analyze(f)

if __name__=='__main__':unittest.main()
