import copy
import unittest

from collect import analyze, distribution


def eq(n): return {"Eq": n}
def integer(n): return {"Int": n}
def slot(n): return {"slot": n}


class EvidenceTests(unittest.TestCase):
    def fixture(self):
        rule = {"query": [
            {"call":{"table":"Get"},"args":[slot(0),slot(1),slot(2)]},
            {"call":{"table":"Expr-size"},"args":[slot(0),slot(3)]}],
            "effects":[{"op":"set","call":{"table":"Expr-size"},"args":[slot(2)],"value":slot(3)}]}
        before = [
            {"table":"Get","values":[eq(1),integer(0),eq(2)],"epoch":1,"hidden":False,"witness":{"Fact":{"cell":10,"op":0}}},
            {"table":"Get","values":[eq(1),integer(1),eq(3)],"epoch":1,"hidden":False,"witness":{"Fact":{"cell":11,"op":0}}},
            {"table":"Expr-size","values":[eq(1),integer(5)],"epoch":4,"hidden":False,"witness":{"Function":0}},
            {"table":"Expr-size","values":[eq(2),integer(3)],"epoch":1,"hidden":False,"witness":{"Function":1}},
        ]
        after = copy.deepcopy(before) + [
            {"table":"Expr-size","values":[eq(3),integer(5)],"epoch":5,"hidden":False,"witness":{"Function":2}}]
        matches = [{"rule":0,"ordinal":i,"watermark":3,"direct":False,
            "values":{"0":eq(1),"1":integer(i),"2":eq(2+i),"3":integer(5)}} for i in range(2)]
        write = {"epoch":5,"source":[1,0],"key":[eq(3)],"old":None,"new":integer(5),"index":2}
        return {"rules":[rule]}, {"run":5,"before":before,"after":after,
            "unions_before":0,"unions_after":0,"capture":{"matches":matches,
                "watermarks":{"0":3},"effective_writes":[write]}}

    def test_one_delta_two_consumers_one_absorbed(self):
        recipe, window = self.fixture()
        result, samples = analyze(window, recipe, 0, {})
        self.assertEqual(result["rules"]["0"]["absorbed_before_run"], 1)
        self.assertEqual(result["rules"]["0"]["effective_updates"], 1)
        self.assertEqual(samples["successful_get_uses"], [2])
        self.assertEqual(samples["changed_get_outputs"], [1])
        self.assertEqual(samples["constructor_storage_cells"], [2])
        self.assertEqual(result["get_delta"], {"+attribute":2})

    def test_missing_visible_input_rejected(self):
        recipe, window = self.fixture()
        window["before"][0]["hidden"] = True
        with self.assertRaises(KeyError): analyze(window, recipe, 0, {})

    def test_wrong_committed_value_rejected(self):
        recipe, window = self.fixture()
        window["capture"]["effective_writes"][0]["new"] = integer(4)
        with self.assertRaises(AssertionError): analyze(window, recipe, 0, {})

    def test_omitted_effect_rejected(self):
        recipe, window = self.fixture()
        window["capture"]["effective_writes"] = []
        with self.assertRaises(AssertionError): analyze(window, recipe, 0, {})

    def test_unobserved_consumer_cannot_lower_fanout(self):
        recipe, window = self.fixture()
        window["capture"]["matches"] = window["capture"]["matches"][1:]
        # The omitted consumer is absorbed, so state and write replay still
        # agree. Complete fresh-input neighbor coverage must catch its absence.
        with self.assertRaises(AssertionError): analyze(window, recipe, 0, {})

    def test_unproven_effect_rejected(self):
        recipe, window = self.fixture()
        recipe["rules"][0]["effects"].append({"op":"union"})
        with self.assertRaises(AssertionError): analyze(window, recipe, 0, {})

    def test_repair_does_not_receive_rhs_credit(self):
        recipe, window = self.fixture()
        window["unions_after"] = 1
        window["capture"]["effective_writes"].append({"source":None,"key":[eq(3)],"old":integer(5),"new":integer(3)})
        result, _ = analyze(window, recipe, 0, {})
        self.assertEqual(result["repair_attribute_changes"], 1)
        self.assertFalse(result["union_free_post_state_checked"])
        self.assertEqual(result["rules"]["0"]["effective_updates"], 1)

    def test_zeros_and_weighted_tail(self):
        d = distribution([0]*99 + [100])
        self.assertEqual((d["p50"],d["p99"],d["max"],d["top_one_percent_share"]), (0,0,100,1))


if __name__ == "__main__": unittest.main()
