import unittest
from pcp_eia_pollution_modeling.core import gauss

S = dict(x=0, y=0, emis=1.0, height=30, temp=400, vel=10, diam=1.2)


class T(unittest.TestCase):
    def test_linear_in_emission(self):
        a = gauss.ground_conc(S, 0, 1000, 3, 180)
        b = gauss.ground_conc(dict(S, emis=2.0), 0, 1000, 3, 180)
        self.assertAlmostEqual(b / a, 2.0, places=9)

    def test_upwind_is_zero_and_downwind_positive(self):
        # wind from the south (180) blows toward the north: point north is downwind
        self.assertGreater(gauss.ground_conc(S, 0, 1000, 3, 180), 0)
        self.assertEqual(gauss.ground_conc(S, 0, -1000, 3, 180), 0)

    def test_centreline_max_and_symmetry(self):
        c0 = gauss.ground_conc(S, 0, 1000, 3, 180)
        self.assertGreater(c0, gauss.ground_conc(S, 200, 1000, 3, 180))
        self.assertAlmostEqual(gauss.ground_conc(S, 200, 1000, 3, 180), gauss.ground_conc(S, -200, 1000, 3, 180), places=9)

    def test_peak_then_decay(self):
        cs = [gauss.ground_conc(S, 0, d, 3, 180) for d in (100, 500, 1000, 3000, 20000)]
        i = cs.index(max(cs))
        self.assertTrue(0 < i < 4)

    def test_wind_rotation(self):
        # wind from the west (270) blows toward the east
        self.assertGreater(gauss.ground_conc(S, 1000, 0, 3, 270), 0)
        self.assertEqual(gauss.ground_conc(S, -1000, 0, 3, 270), 0)

    def test_errors_and_rise(self):
        with self.assertRaises(ValueError):
            gauss.ground_conc(S, 0, 1, 0, 0)
        with self.assertRaises(ValueError):
            gauss.ground_conc(S, 0, 1, 3, 0, "Z")
        self.assertEqual(gauss.plume_rise(10, 1, 290, 298, 3, "D"), 0.0)
        self.assertGreater(gauss.plume_rise(10, 1.2, 400, 298, 3, "D"), 0)


    def test_grid_too_coarse(self):
        self.assertTrue(gauss.grid_too_coarse(800, 1e8, "D")[0])
        self.assertFalse(gauss.grid_too_coarse(27889, 2500.0 * 2500.0, "D")[0])


if __name__ == "__main__":
    unittest.main()


class TestLevels(unittest.TestCase):
    def test_levels(self):
        from pcp_eia_pollution_modeling.core.levels import fmt_vi, levels_from_limit
        lv = levels_from_limit(200)
        self.assertEqual(lv[5], 200.0)
        self.assertEqual(lv, sorted(lv))
        self.assertEqual(fmt_vi(36.04, 2), "36,04")
        self.assertEqual(fmt_vi(0.5), "0,5")
        with self.assertRaises(ValueError):
            levels_from_limit(0)


class TestRose(unittest.TestCase):
    def test_uniform_rose_is_isotropic(self):
        from pcp_eia_pollution_modeling.core.gauss import sector_conc, parse_rose
        rose = parse_rose(" ".join(["6.25"] * 16))
        a = sector_conc(S, 0, 1000, 3, rose)
        b = sector_conc(S, 1000, 0, 3, rose)
        c = sector_conc(S, -707.1, -707.1, 3, rose)
        self.assertGreater(a, 0)
        self.assertAlmostEqual(a, b, delta=a * 0.02)
        self.assertAlmostEqual(a, c, delta=a * 0.02)

    def test_rose_errors(self):
        from pcp_eia_pollution_modeling.core.gauss import parse_rose
        with self.assertRaises(ValueError):
            parse_rose("1 2 3")


class TestEnvelope(unittest.TestCase):
    def test_matches_scalar_and_envelope_is_max(self):
        import numpy as np
        from pcp_eia_pollution_modeling.core import gauss_np
        X = np.array([0.0, 500.0, 1200.0])
        Y = np.array([1000.0, 400.0, -300.0])
        for xi, yi, c in zip(X, Y, gauss_np.conc_field([S], X, Y, 3, 180)):
            self.assertAlmostEqual(c, gauss.ground_conc(S, xi, yi, 3, 180), delta=abs(c) * 1e-9 + 1e-12)
        env = gauss_np.first_high([S], X, Y, [0, 90, 180, 270], [3], ["D"])
        one = gauss_np.conc_field([S], X, Y, 3, 180)
        self.assertTrue(all(env >= one - 1e-12))

    def test_report_levels(self):
        from pcp_eia_pollution_modeling.core.levels import report_levels
        lv = report_levels(105, 2401)
        self.assertEqual(lv, sorted(set(lv)))
        self.assertTrue(8 <= len(lv) <= 9)
        self.assertTrue(all(105 < v < 2401 for v in lv))
        lv2 = report_levels(0.03, 2.53)
        self.assertTrue(all(0.03 <= v < 2.53 for v in lv2))


class TestLimitLevels(unittest.TestCase):
    def test_limit_levels_shape(self):
        from pcp_eia_pollution_modeling.core.levels import levels_from_limit
        lv = [v for v in levels_from_limit(300) if v < 51]
        self.assertLess(len(lv), 6)  # too few classes: the contour step falls back to data-based levels


class TestAqi(unittest.TestCase):
    def setUp(self):
        import importlib.util as u, os
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "core", "aqi.py")
        sp = u.spec_from_file_location("aqi_t", p)
        self.m = u.module_from_spec(sp)
        sp.loader.exec_module(self.m)

    def test_edges_increase_and_match_colours(self):
        for k in self.m.keys():
            c = self.m.classes(k)
            self.assertEqual(c["levels"], sorted(c["levels"]))
            self.assertEqual(len(c["colors"]), len(c["levels"]) + 1)
            self.assertEqual(len(c["names"]), len(c["colors"]))

    def test_unit_conversion(self):
        self.assertAlmostEqual(self.m.to_ugm3(53, "ppb", 46.0055), 99.7, delta=0.2)
        self.assertEqual(self.m.to_ugm3(35.4, "ug/m3", None), 35.4)


class TestHourly(unittest.TestCase):
    ROW = "2024,Jan,1,1,%d,-40.1,0.2,0.0,-3000,0.0,173.0,2.01,-1.0,1.0,%s,%s,10.0,25.0,0.0,0.0,98.3,1004.0,0.0,10.0,%s"

    def _csv(self, rows):
        import os, tempfile
        fd, p = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("Year,Month,Day,Julian_Day,Hour\n" + "\n".join(rows) + "\n")
        return p

    def test_parse_from_right_with_trailing_empties(self):
        from pcp_eia_pollution_modeling.core import met_hourly as m
        p = self._csv([self.ROW % (1, "1.4", "90.0", ""), self.ROW % (2, "2.0", "180.0", ",,")])
        r = m.read_csv(p)
        self.assertEqual(len(r["hours"]), 2)
        self.assertEqual((r["hours"][1]["ws"], r["hours"][1]["wd"]), (2.0, 180.0))

    def test_missing_wind_is_skipped(self):
        from pcp_eia_pollution_modeling.core import met_hourly as m
        r = m.read_csv(self._csv([self.ROW % (1, "-999", "90.0", ""), self.ROW % (2, "2.0", "180.0", "")]))
        self.assertEqual((len(r["hours"]), r["missing"]), (1, 1))

    def test_stability_classes(self):
        from pcp_eia_pollution_modeling.core.met_hourly import stability_from_L as f
        self.assertEqual([f(-5), f(-20), f(-60), f(500), f(60), f(10), f(None)], ["A", "B", "C", "D", "E", "F", "D"])

    def test_identical_hours_give_equal_statistics(self):
        import numpy as np
        from pcp_eia_pollution_modeling.core import hourly
        h = dict(month=1, day=1, hour=1, ws=3.0, wd=225.0, zref=10.0, ta_c=25.0, cls="D")
        hours = [dict(h, hour=i, day=1 + i // 24) for i in range(48)]
        S = [dict(x=0, y=0, emis=10, height=50, temp=420, vel=10, diam=2)]
        X = np.array([1000.0, 2000.0]); Y = np.array([1000.0, 2000.0])
        a = hourly.run(S, X, Y, hours, "max1h")["field"]
        b = hourly.run(S, X, Y, hours, "max24h")["field"]
        c = hourly.run(S, X, Y, hours, "mean")["field"]
        self.assertTrue(np.allclose(a, b) and np.allclose(a, c))
        self.assertGreater(a.max(), 0)

    def test_month_filter(self):
        import numpy as np
        from pcp_eia_pollution_modeling.core import hourly
        h = dict(month=1, day=1, hour=1, ws=3.0, wd=225.0, zref=10.0, ta_c=25.0, cls="D")
        S = [dict(x=0, y=0, emis=10, height=50, temp=420, vel=10, diam=2)]
        with self.assertRaises(ValueError):
            hourly.run(S, np.array([1000.0]), np.array([1000.0]), [h], "mean", months={7})


class TestMeanderAndHeader(unittest.TestCase):
    def test_header_driven_columns(self):
        import os, tempfile
        from pcp_eia_pollution_modeling.core import met_hourly as m
        hdr = "Year,Month,Day,Julian_Day,Hour,Heat_Flux,Friction_Velocity,Convective_Velocity_Scale,Temperature_Scale,Height_Convective_BL,Height_Mechanical_BL,Wind_Speed,Wind_Direction,Reference_Height_Wind,Surface_Temp,Precipitation_Code,Precipitation_Rate,Relative_Humidity,Pressure,Cloud_Cover"
        fd, p = tempfile.mkstemp(suffix=".csv"); os.close(fd)
        open(p, "w").write(hdr + "\n2024,Jan,1,1,1,-40.0,0.2,0.0,-3000,0,150,1.1,132,10.0,24.0,0,0.0,98.0,1004.0,10\n")
        h = m.read_csv(p)["hours"][0]
        self.assertEqual((h["ws"], h["wd"], h["ta_c"]), (1.1, 132.0, 24.0))

    def test_meander_widens_and_conserves_roughly(self):
        import numpy as np
        from pcp_eia_pollution_modeling.core.gauss_np import conc_field
        S = [dict(x=0, y=0, emis=10, height=30, temp=400, vel=8, diam=1.5)]
        g = np.arange(-3000, 3001, 50.0)
        X, Y = np.meshgrid(g, g)
        a = conc_field(S, X.ravel(), Y.ravel(), 3.0, 180.0, "D")
        b = conc_field(S, X.ravel(), Y.ravel(), 3.0, 180.0, "D", meander=True)
        self.assertLess(b.max(), a.max())
        self.assertAlmostEqual(b.sum() / a.sum(), 1.0, delta=0.12)


class TestSimpleMetFormat(unittest.TestCase):
    def test_simple_format_with_stability_column(self):
        import os, tempfile
        from pcp_eia_pollution_modeling.core import met_hourly as m
        fd, p = tempfile.mkstemp(suffix=".csv"); os.close(fd)
        open(p, "w", encoding="utf-8-sig").write("Year,Month,Day,Hour,Wind_Speed,Wind_Direction,Surface_Temp,Relative_Humidity,Pressure,Stability_Class,Mixing_Height\n2024,Jan,1,1,0.5,357.8,19.7,100.0,1008.3,F,220.0\n2024,Feb,3,5,2.0,10,20,80,1010,c,500\n")
        r = m.read_csv(p)["hours"]
        self.assertEqual([(h["month"], h["hour"], h["cls"], h["wd"]) for h in r], [(1, 1, "F", 357.8), (2, 5, "C", 10.0)])


class TestAermetSynth(unittest.TestCase):
    def test_files_have_one_record_per_hour_and_sane_values(self):
        from pcp_eia_pollution_modeling.core import aermet_synth as a
        hrs = [dict(month=1, day=1, hour=1, ws=0.5, wd=357.8, ta_c=19.7, cls="F", rh=100.0, pres=1008.3, mixh=220.0),
               dict(month=1, day=1, hour=13, ws=3.0, wd=90.0, ta_c=30.0, cls="B", rh=50.0, pres=1008.0, mixh=1500.0)]
        sfc, pfl = a.make_files(hrs, 2024, 12.0, 109.0, "12345")
        lines = sfc.strip().splitlines()
        self.assertEqual(len(lines), 3)
        self.assertIn("VERSION: 24142", lines[0])
        self.assertEqual(len(pfl.strip().splitlines()), 2)
        f = lines[1].split()
        self.assertEqual((f[0], f[3], f[4]), ("24", "1", "01"))
        self.assertLess(float(f[5]), 0)            # stable night: negative heat flux
        self.assertGreater(float(lines[2].split()[5]), 0)  # convective day: positive
        self.assertEqual(len(f), 26)


class TestHourZero(unittest.TestCase):
    def test_hour_zero_becomes_hour_24_of_previous_day(self):
        import os, tempfile
        from pcp_eia_pollution_modeling.core import met_hourly as m
        fd, p = tempfile.mkstemp(suffix=".csv"); os.close(fd)
        open(p, "w").write("Year,Month,Day,Hour,Wind_Speed,Wind_Direction,Surface_Temp,Relative_Humidity,Pressure,Stability_Class,Mixing_Height\n"
                           "2024,Jan,2,0,1.0,10,20,80,1010,D,500\n2025,Jan,1,0,1.0,10,20,80,1010,D,500\n")
        r = m.read_csv(p)["hours"]
        self.assertEqual([(h["month"], h["day"], h["hour"]) for h in r], [(1, 1, 24), (12, 31, 24)])


class TestWhenMax(unittest.TestCase):
    def test_time_of_maximum_strings(self):
        import numpy as np
        from pcp_eia_pollution_modeling.core import hourly
        base = dict(year=2024, month=3, day=26, hour=18, ws=3.0, wd=90.0, zref=10.0, ta_c=25.0, cls="D")
        hrs = [dict(base, hour=i) for i in range(1, 25)]
        hrs[19] = dict(base, hour=20, wd=225.0)  # only hour with the wind towards the receptor
        S = [dict(x=0, y=0, emis=10, height=50, temp=420, vel=10, diam=2)]
        X = np.array([1500.0]); Y = np.array([1500.0])
        self.assertEqual(hourly.run(S, X, Y, hrs, "max1h")["when_max"], "3/26/2024 20 hr")
        self.assertEqual(hourly.run(S, X, Y, hrs, "max24h")["when_max"], "3/26/2024 24 hr")
        self.assertEqual(hourly.run(S, X, Y, hrs, "mean")["when_max"], "")
