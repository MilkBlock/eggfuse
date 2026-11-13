import unittest
import numpy as np
from audit_device_match_readout import rows_from_labels

class ReadoutLabels(unittest.TestCase):
    def test_cpu_partition_and_static_copy_are_distinct_obligations(self):
        sort=dict(kind='eq',name='E')
        rule=dict(slots=[dict(sort=sort,definition='query') for _ in range(3)],query=[dict(call=dict(table='F'),args=[dict(slot=0),dict(slot=2)])],effects=[dict(kind='copy',arg=dict(slot=0),dst=1)])
        recipe=dict(rules=[rule]);rows=rows_from_labels(recipe,[0],np.array([[0,0,1]]))
        self.assertEqual(rows[0]['y'].tolist(),[True,False,False])
        self.assertEqual(len(rows[0]['quotient']['representatives']),1)
        for labels in ([[0,1,2]],[[0,0,-1]],[]):
            with self.assertRaises(ValueError):rows_from_labels(recipe,[0],np.array(labels))

if __name__=='__main__':unittest.main()
