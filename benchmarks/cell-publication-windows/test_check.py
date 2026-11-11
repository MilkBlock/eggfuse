import copy
import unittest
import check


def eq(n, sort="Expr"):
    return {"eq": f"Cell({n})", "sort": sort}


def row(table, *values):
    return {"table": table, "values": list(values), "subsumed": False}


def fixture():
    before = {"unions": 0, "rows": [
        row("DoWhile", eq(1), eq(2), eq(9)),
        row("is-inv-Expr", eq(2), eq(3), eq(10)),
        row("Base", eq(4, "BaseType"), eq(5, "Type")),
        row("HasType", eq(3), eq(5, "Type"), eq(11)),
        row("Expr-size", eq(3), {"sort": "i64", "value": 3}),
        row("to-hoist-size", eq(1), eq(2), {"sort": "i64", "value": 3}),
    ]}
    after = copy.deepcopy(before)
    after["rows"].append(row("to-hoist", eq(1), eq(2), eq(3)))
    return before, after


class SourceChoiceTests(unittest.TestCase):
    def test_choice_uses_the_read_snapshot_not_a_later_attribute(self):
        before, after = fixture()
        self.assertEqual(len(check.valid_source_choices(before, after)), 1)
        # Later attribute changes cannot retroactively refute a valid source
        # application. Changing the actual input snapshot must refute it.
        after["rows"][4]["values"][1]["value"] = 1
        self.assertEqual(len(check.valid_source_choices(before, after)), 1)
        before["rows"][4]["values"][1]["value"] = 1
        with self.assertRaises(AssertionError):
            check.valid_source_choices(before, after)

    def test_missing_condition_and_hidden_or_duplicate_choices_fail(self):
        for table in ("DoWhile", "is-inv-Expr", "HasType", "Base"):
            before, after = fixture()
            before["rows"] = [r for r in before["rows"] if r["table"] != table]
            with self.assertRaises(AssertionError):
                check.valid_source_choices(before, after)
        for hidden in (True, False):
            before, after = fixture()
            if hidden:
                after["rows"][-1]["subsumed"] = True
            else:
                after["rows"].append(after["rows"][-1])
            with self.assertRaises(AssertionError):
                check.valid_source_choices(before, after)

    def test_unobserved_selection_cannot_enter_between_windows(self):
        _, previous = fixture()
        following = copy.deepcopy(previous)
        roots = {f"Cell({i})": f"Cell({i})" for i in (1, 2, 3, 6)}
        check.carried_choices(previous, following, roots)
        following["rows"][-1]["values"][-1] = eq(6)
        with self.assertRaises(AssertionError):
            check.carried_choices(previous, following, roots)
        roots["Cell(6)"] = "Cell(3)"
        check.carried_choices(previous, following, roots)

    def test_variable_normalization_preserves_effect_order_and_aliases(self):
        a = {"body": [{"var": "x"}, {"var": "y"}], "head": [{"dst": "z", "var": "x"}, {"var": "z"}]}
        b = {"body": [{"var": "a"}, {"var": "b"}], "head": [{"dst": "c", "var": "a"}, {"var": "c"}]}
        self.assertEqual(check.alpha(a), check.alpha(b))
        b["head"].reverse()
        self.assertNotEqual(check.alpha(a), check.alpha(b))


if __name__ == "__main__":
    unittest.main()
