import unittest

from txn_policy import ReadPlan, request_frontier


class ReceiptFrontierTest(unittest.TestCase):
    def test_computation_is_available_before_external_reference(self):
        rule = {
            "inputs": [{"atom": 0}, {"atom": 2}],
            "computations": [
                {
                    "atom": 1,
                    "operands": [
                        {"fields": [[0, 1]], "local_results": []},
                        {"literal_operand": 1},
                    ],
                    "target_fields": [[2, 0]],
                }
            ],
        }
        f = request_frontier(rule, ["available", "unbound"])
        self.assertEqual(f["computations"][1], [ReadPlan(1, ((0, 1), None), 0)])
        self.assertEqual(f["address_roles"], (1,))
        self.assertFalse(f["can_issue"])
        self.assertTrue(request_frontier(rule, ["available", "available"])["can_issue"])
        self.assertEqual(
            request_frontier(rule, ["available", "pending"])["await_roles"], (1,)
        )
        for state in ("absent", "retired"):
            stopped = request_frontier(rule, [state, "unbound"])
            self.assertEqual(stopped["failed_roles"], (0,))
            self.assertFalse(stopped["address_roles"])

    def test_failed_operand_alternative_leaves_no_local_request(self):
        field = {"fields": [[0, 2]], "local_results": []}

        def primitive(pc, *operands, target=False):
            return {
                "atom": pc,
                "operands": operands,
                "target_fields": [[5, 1]] if target else [],
            }

        def local(*pcs):
            return {"fields": [], "local_results": pcs}

        rule = {
            "inputs": [{"atom": 0}, {"atom": 5}],
            "computations": [
                primitive(1, field),
                primitive(2, field),
                primitive(3, local(2), local()),
                primitive(4, local(1, 3), target=True),
            ],
        }
        result = request_frontier(rule, ["available", "unbound"], chains=True)
        self.assertEqual(
            result["computations"][1][0].steps, ((1, ((0, 2),)), (4, (("local", 0),)))
        )
