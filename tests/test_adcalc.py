import sys,os; sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest
from src.adcalc import calc,apply_to_groups
C=[{"price":p} for p in (10,20,30)]
class T(unittest.TestCase):
    def test_default(self):
        r=calc({"price":20.0,"competitors":C})
        self.assertTrue(r["profitable"]); self.assertEqual(r["margin_pct"],40)
        self.assertEqual(r["breakeven_acos_pct"],40); self.assertEqual(r["target_acos_pct"],28)
        self.assertEqual(r["max_bid"],0.56); self.assertEqual(r["start_bid"],0.39)
        self.assertEqual(r["daily_budget"],16.8); self.assertEqual(r["daily_orders"],3.0)
        self.assertTrue(all(i["source"]=="示例假设" for i in r["inputs"][1:]))
        self.assertEqual(r["price_position"]["comp_median"],20)
    def test_file(self):
        r=calc({"price":30.0,"cost":9,"fee_rate":0.25,"cvr":0.12,"competitors":C})
        self.assertEqual(r["margin_pct"],45); self.assertEqual(r["target_acos_pct"],32)
        self.assertEqual(r["max_bid"],1.13)
        self.assertEqual([i["source"] for i in r["inputs"][1:4]],["表格提供"]*3)
    def test_unprofitable(self):
        r=calc({"price":10.0,"cost":8,"fee_rate":0.3,"competitors":C})
        self.assertFalse(r["profitable"]); self.assertNotIn("max_bid",r); self.assertIn("不盈利",r["message"])
        g=apply_to_groups([{"suggested_bid":"","budget_share":""}],r); self.assertEqual(g[0]["suggested_bid"],"不建议投放")
if __name__=="__main__": unittest.main()
