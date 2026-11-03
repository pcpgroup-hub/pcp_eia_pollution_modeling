# -*- coding: utf-8 -*-
"""Tests for the parts that do not need QGIS. Run: python3 -m unittest discover -s tests -t .. (from the plugin folder's parent)
Sample texts below are SYNTHETIC, written to exercise the parsers; replace with real EPA test-case files (docs/TESTING_vi.md)."""
import json
import os
import tempfile
import unittest

from pcp_eia_pollution_modeling.core import aermod_io, approval, audit, cards

INP = """** comment
CO STARTING
   TITLEONE test
   MODELOPT DFAULT CONC
   AVERTIME 1 PERIOD
   POLLUTID SO2
CO FINISHED
ME STARTING
   SURFFILE met.sfc
   PROFFILE "met.pfl"
ME FINISHED
"""
PLT = """* AERMOD ( 26135): synthetic
* FORMAT: x y conc
   100.0   200.0   12.34567  10.0  10.0  0.0  1-HR  ALL  8760  NA  99123124
   150.0   200.0    9.00000  10.0  10.0  0.0  1-HR  ALL  8760  NA  99123124
"""


class Core(unittest.TestCase):
    def test_cards_load_and_flag_unverified(self):
        self.assertEqual(set(cards.list_cards()), {"aermod", "qual2kw", "vn_tt95_2025_river_load_capacity"})
        for cid in cards.list_cards():
            c = cards.load_card(cid)
            self.assertEqual(c["id"], cid)
        self.assertGreater(len(cards.unverified_fields(cards.load_card("aermod"))), 0)

    def test_dfault(self):
        self.assertTrue(aermod_io.uses_dfault(INP))
        self.assertFalse(aermod_io.uses_dfault(INP.replace("DFAULT ", "")))
        self.assertFalse(aermod_io.uses_dfault("** MODELOPT DFAULT\nCO STARTING\n"))

    def test_referenced_files(self):
        got = aermod_io.referenced_files(INP, "/w")
        self.assertEqual([os.path.basename(p) for p in got], ["met.sfc", "met.pfl"])

    def test_plotfile(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.plt")
            open(p, "w").write(PLT)
            rows = aermod_io.read_plotfile(p)
        self.assertEqual(len(rows), 2)
        self.assertAlmostEqual(rows[0]["conc"], 12.34567)
        self.assertEqual(rows[0]["ave"], "1-HR")

    def test_run_failed(self):
        self.assertTrue(aermod_io.run_failed("... Un-successfully ..."))
        self.assertFalse(aermod_io.run_failed("*** AERMOD Finishes Successfully ***"))

    def test_audit_chain(self):
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "x.txt")
            open(f, "w").write("hello")
            log = audit.AuditLog(d)
            log.append("s1", "B", "aermod", "0.1", {"a": 1}, approval={"by": "t"}, files=[f])
            log.append("s2", "A", "aermod", "0.1", {"b": 2})
            self.assertEqual(log.verify(), (True, "chain ok"))
            lines = open(log.path).read().splitlines()
            e = json.loads(lines[0])
            e["parameters"] = {"a": 999}
            lines[0] = json.dumps(e, sort_keys=True)
            open(log.path, "w").write("\n".join(lines) + "\n")
            ok, msg = log.verify()
            self.assertFalse(ok)

    def test_approval_levels(self):
        self.assertEqual(approval.require("A", "t", "s")["by"], "auto")
        rec = approval.require("B", "t", "s", ask=lambda *a: ("", True))
        self.assertEqual(rec["level"], "B")
        with self.assertRaises(approval.ApprovalRefused):
            approval.require("B", "t", "s", ask=lambda *a: ("", False))
        rec = approval.require("C", "t", "s", ask=lambda lvl, t, s, need: ("because", True))
        self.assertEqual(rec["reason"], "because")
        # headless: real Qt ask must refuse because qgis is not importable/running here
        with self.assertRaises(Exception):
            approval.require("B", "t", "s")


if __name__ == "__main__":
    unittest.main()
