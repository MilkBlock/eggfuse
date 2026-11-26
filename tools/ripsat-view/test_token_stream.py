import gzip
import hashlib
import json
import re
import tempfile
import unittest
from pathlib import Path

from ripsat_view import render, suite_html


def payload(html, tag):
    raw = re.search(r'<script type="application/json" id="' + tag + r'">(.*?)</script>', html, re.S)
    return json.loads(raw.group(1))


class TokenStreamTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.program = self.root / "program.json"
        rule = {"metadata": {"name": "with input", "source_set": 0}, "effects": [], "query": []}
        self.recipe = {"recipe": {"rules": [rule], "tables": [{"name": "Input"}]},
                       "receipt_contract": {"rules": [{"recipe_rule": 0, "inputs": [{"table": 0}]}]}}
        self.program.write_text(json.dumps(self.recipe))
        self.trace = {"program": hashlib.sha256(self.program.read_bytes()).hexdigest(),
                      "events": [{"frame": {"run": 1, "epoch": 0, "updates": [], "retired": []},
                                  "generated": [[0, False, []]], "response": [[2**61, 0, -1, 0]],
                                  "signed_gain": [1], "assisted": [], "assisted_response": [],
                                  "random_count": 0, "omitted": [], "stable": True}],
                      "note": "</script><script>alert(1)</script>/*CATALOGS*/"}

    def test_file_formats_and_program_crosslink(self):
        for packed in (False, True):
            trace = self.root / ("trace.gz" if packed else "trace.json")
            data = json.dumps(self.trace).encode()
            trace.write_bytes(gzip.compress(data) if packed else data)
            html = render([], self.root / "viewer.html", self.program, stream=trace).read_text()
            self.assertEqual(payload(html, "ts-data")["trace"], self.trace)
            self.assertNotIn(self.trace["note"], html)
            cat, = payload(html, "data")
            self.assertEqual(cat["program_sha"], self.trace["program"])
            self.assertEqual(cat["rules"]["0"]["atoms"], ["Input"])

    def test_mismatch_refused(self):
        self.trace["program"] = "different"
        file = self.root / "trace.json"
        file.write_text(json.dumps(self.trace))
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            suite_html([], self.program, stream=file)

    def test_old_catalog_and_old_program(self):
        catalog = self.root / "catalog.json"
        catalog.write_text("[[[0,0,[]]]]")
        self.assertEqual(payload(suite_html([catalog]), "data")[0]["layouts"], [[[0, 0, []]]])
        del self.recipe["receipt_contract"]
        self.program.write_text(json.dumps(self.recipe))
        html = suite_html([], self.program, start_stream=True, egraph_link=True)
        self.assertEqual(payload(html, "data"), [])
        self.assertIn('href="/"', html)
