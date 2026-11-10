import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import tdcc_holders as t

# 長榮航（2618）2026-11-06 集保開放資料 1-5 原值（2026-11-10 GitHub 實抓）
EVA = {1: (63387, 11023257, 0.20), 2: (90141, 187465610, 3.47), 3: (14205, 112355447, 2.08), 4: (4378, 55564457, 1.02),
       5: (2683, 49463512, 0.91), 6: (2383, 60706032, 1.12), 7: (1115, 39985910, 0.74), 8: (743, 34631951, 0.64),
       9: (1345, 97030334, 1.79), 10: (600, 85387292, 1.58), 11: (331, 94195012, 1.74), 12: (135, 67263997, 1.24),
       13: (81, 56219536, 1.04), 14: (51, 46420066, 0.85), 15: (407, 4402731922, 81.52), 16: (0, 0, 0.0), 17: (181985, 5400444335, 100.0)}


class SummaryTests(unittest.TestCase):
    def test_eva_summary(self):
        s, err = t.summarize(EVA)
        self.assertIsNone(err)
        self.assertEqual((s["holders"], s["ge1000_holders"], s["ge1000_pct"]), (181985, 407, 81.52))
        self.assertEqual(s["ge400_pct"], 84.65)
        self.assertEqual(s["le50_pct"], 10.18)

    def test_mismatch_is_rejected(self):
        bad = dict(EVA)
        bad[17] = (181984, 5400444335, 100.0)
        self.assertIsNone(t.summarize(bad)[0])
        missing = {k: v for k, v in EVA.items() if k != 15}
        self.assertIsNone(t.summarize(missing)[0])

    def test_query_page_table_is_parsed(self):
        rows = "".join(f"<tr><td>{k}</td><td>x</td><td>{h:,}</td><td>{s:,}</td><td>{p:.2f}</td></tr>" for k, (h, s, p) in EVA.items() if k <= 15)
        rows += "<tr><td>16</td><td>差異數調整（說明4）</td><td>0</td><td>0</td><td>0.00</td></tr>"
        rows += f"<tr><td></td><td>合　計</td><td>{EVA[17][0]:,}</td><td>{EVA[17][1]:,}</td><td>100.00</td></tr>"
        body = f"<html><span>資料日期：20261106</span><table>{rows}</table></html>"
        s, err = t.parse_result(body, "2618", "20261106")
        self.assertIsNone(err)
        self.assertEqual(s["ge1000_pct"], 81.52)
        self.assertEqual(t.parse_result(body, "2618", "20261030")[0], None, "頁面日期不符就不收")


if __name__ == "__main__":
    unittest.main()
