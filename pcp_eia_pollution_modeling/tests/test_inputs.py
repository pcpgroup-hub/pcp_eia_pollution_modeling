import unittest
from pcp_eia_pollution_modeling.core import grid, aermod_input as ai, aermod_io

SRC = [dict(id="S1", x=500000, y=2300000, z=5, emis=1.5, height=30, temp=400, vel=10, diam=1.2)]


class T(unittest.TestCase):
    def test_utm(self):
        self.assertEqual(grid.utm_epsg_for_lonlat(105.8, 21.0), 32648)
        self.assertEqual(grid.utm_epsg_for_lonlat(109.2, 13.7), 32649)
        self.assertEqual(grid.utm_epsg_for_lonlat(-70, -33), 32719)

    def test_grid(self):
        g = grid.make_grid(0, 0, 100, 50, 50)
        self.assertEqual(len(g), 6)
        self.assertEqual(g[0], (0, 0))
        with self.assertRaises(ValueError):
            grid.make_grid(0, 0, 1e6, 1e6, 10)
        self.assertEqual(grid.extent_around([(1, 2), (3, 4)], 10), (-9, -8, 13, 14))

    def test_nested(self):
        g = grid.make_nested_grid((-1000, -1000, 1000, 1000), 500, (-200, -200, 200, 200), 100)
        inner = [p for p in g if abs(p[0]) <= 200 and abs(p[1]) <= 200]
        self.assertEqual(len(inner), 25)           # 5 x 5 at 100 m
        self.assertEqual(len(set(g)), len(g))      # no duplicates
        self.assertIn((-1000, -1000), g)
        with self.assertRaises(ValueError):
            grid.make_nested_grid((0, 0, 10, 10), 5, (-5, 0, 5, 5), 1)

    def test_inp(self):
        t = ai.build_inp("test", "SO2", SRC, [(1, 2), (3, 4, 9)], "a.sfc", "a.pfl", "HN", 2020, "HN", 2020, 5)
        self.assertIn("MODELOPT  DFAULT CONC", t)
        self.assertIn("SRCPARAM  S1 1.5 30 400 10 1.2", t)
        self.assertEqual(t.count("DISCCART"), 2)
        self.assertEqual(ai.check_inp_lengths(t), [])
        self.assertTrue(aermod_io.uses_dfault(t))
        self.assertIn("PLOTFILE  PERIOD ALL plot_period.plt", t)

    def test_precision(self):
        src = [dict(SRC[0], x=588324.123, y=2325712.456)]
        t = ai.build_inp("t", "SO2", src, [(586324.5, 2323703.25)], "a", "b", "H", 1, "H", 1, 0)
        self.assertIn("POINT 588324.123 2325712.456 5", t)
        self.assertIn("DISCCART  586324.5 2323703.25 0", t)
        self.assertNotIn("e+", t)

    def test_inp_errors(self):
        with self.assertRaises(ValueError):
            ai.build_inp("t", "SO2", [], [(1, 2)], "a", "b", "H", 1, "H", 1, 0)
        with self.assertRaises(ValueError):
            ai.build_inp("t", "SO2", SRC + SRC, [(1, 2)], "a", "b", "H", 1, "H", 1, 0)
        bad = [dict(SRC[0], id="TOOLONGID1")]
        with self.assertRaises(ValueError):
            ai.build_inp("t", "SO2", bad, [(1, 2)], "a", "b", "H", 1, "H", 1, 0)
        with self.assertRaises(ValueError):
            ai.build_inp("t", "SO2", [dict(SRC[0], emis=None)], [(1, 2)], "a", "b", "H", 1, "H", 1, 0)


if __name__ == "__main__":
    unittest.main()


class TestQual2kwBridge(unittest.TestCase):
    def test_reaches_and_chainage(self):
        from pcp_eia_pollution_modeling.core import qual2kw_io as q
        pts = [(0.0, 0.0), (10000.0, 0.0)]
        rows = q.build_reach_rows(pts, lambda x, y: (105.0 + x / 1e5, 21.0), 2.5, 100.0, 90.0)
        self.assertEqual(len(rows), 5)
        self.assertAlmostEqual(rows[0]["down_km"], 10.0)
        self.assertAlmostEqual(rows[-1]["down_km"], 0.0)
        self.assertAlmostEqual(rows[-1]["elev_down"], 90.0)
        s, off = q.chainage_of(pts, 4000.0, 30.0)
        self.assertAlmostEqual(s, 4000.0)
        self.assertAlmostEqual(off, 30.0)
        self.assertEqual(q.dms(105.5), (105, 30, 0.0))

    def test_interpolate_and_names(self):
        from pcp_eia_pollution_modeling.core import qual2kw_io as q
        rows = [{"label": "", "km": 10, "values": {"DO": 8.0}}, {"label": "", "km": 0, "values": {"DO": 4.0}}]
        self.assertAlmostEqual(q.interpolate_km(rows, "DO", 5), 6.0)
        self.assertEqual(q.field_name("Dissolved oxygen (mgO2/L)"), "Dissolved_oxygen_mgO2_L")


class TestVn2000(unittest.TestCase):
    def test_table(self):
        from pcp_eia_pollution_modeling.core import vn2000 as v
        self.assertEqual(len(v.PROVINCES), 61)
        self.assertEqual(v.central_meridian("Bình Thuận"), 108.5)
        self.assertEqual(v.central_meridian("Đà Nẵng"), 107.75)
        self.assertEqual(v.epsg_for("Hải Phòng"), 9210)
        self.assertEqual(v.dms_label(105.75), "105°45′")
        for _, m in v.PROVINCES:
            self.assertIn(m, v.EPSG_BY_MERIDIAN)
        self.assertIn("lon_0=108.5", v.proj_string(108.5))


class TestMethodSheet(unittest.TestCase):
    def test_sheet(self):
        import os, tempfile
        from pcp_eia_pollution_modeling.core import method_sheet as ms
        d = tempfile.mkdtemp()
        open(os.path.join(d, "aermod.inp"), "w").write("CO STARTING\n   POLLUTID  SO2\n   AVERTIME  1 24 PERIOD\nSO STARTING\n   SRCPARAM  LD1 0.15 30 453.15 19.6 0.6\nRE STARTING\n   DISCCART  1 2 0\n   DISCCART  3 4 0\nME STARTING\n   SURFFILE  a.sfc\n   PROFFILE  a.pfl\n   SURFDATA  99999 2024\n")
        open(os.path.join(d, "aermod.out"), "w").write("*** AERMOD - VERSION 26135 ***\n")
        c = ms.read_aermod_context(os.path.join(d, "plot_1h.plt"))
        self.assertEqual((c["version"], c["pollutant"], c["year"], c["n_receptors"], len(c["sources"])), ("26135", "SO2", "2024", 2, 1))
        self.assertEqual(ms.parse_thresholds("93=EPA; 40,5=ví dụ"), [(93.0, "EPA"), (40.5, "ví dụ")])
        t = ms.build_sheet({"id": "x", "title": "T", "sources": c["sources"], "thresholds": [(93.0, "EPA")], "notes": "a|b", "hashes": [("f", "abc")]})
        for k in ("Phiếu phương pháp: x", "LD1", "93.0", "- a", "`abc`", "chịu trách nhiệm"):
            self.assertIn(k, t)
        self.assertEqual(len(ms.sha256_of(os.path.join(d, "aermod.inp"))), 64)
