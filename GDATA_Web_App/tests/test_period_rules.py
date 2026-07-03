import unittest
import sys
from datetime import date, timedelta
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from GDATA_Web_App.feishu_sync import TableConfig, convert_record
from GDATA_Web_App.gdata_core import (
    DailyMetric,
    DailyPrivateRecord,
    build_conversion_results,
    build_private_monthly_rows,
)
from GDATA_Web_App.server import period_counts, sync_preview


def daily_metrics(start_day, values):
    return [DailyMetric(start_day + timedelta(days=index), value) for index, value in enumerate(values)]


class PeriodRulesTest(unittest.TestCase):
    def test_incomplete_week_is_skipped_and_month_uses_actual_dates(self):
        start_day = date(2026, 6, 22)
        gdata = daily_metrics(start_day, [10, 11, 12, 13, 14, 15])
        scrm = daily_metrics(start_day, [20, 21, 22, 23, 24, 25])

        results = build_conversion_results(gdata, scrm)

        self.assertFalse([result for result in results if result.period_type == "周"])
        monthly_results = [result for result in results if result.period_type == "月"]
        self.assertEqual(1, len(monthly_results))
        self.assertEqual("6.22-6.27", monthly_results[0].period)
        self.assertEqual(date(2026, 6, 22), monthly_results[0].start_day)
        self.assertEqual(date(2026, 6, 27), monthly_results[0].end_day)
        self.assertEqual(sum([10, 11, 12, 13, 14, 15]), monthly_results[0].gdata_sum)

    def test_zero_values_are_valid_for_complete_week(self):
        start_day = date(2026, 6, 22)
        gdata = daily_metrics(start_day, [0, 11, 12, 13, 14, 15, 16])
        scrm = daily_metrics(start_day, [20, 0, 22, 23, 24, 25, 26])

        results = build_conversion_results(gdata, scrm)

        weekly_results = [result for result in results if result.period_type == "周"]
        self.assertEqual(1, len(weekly_results))
        self.assertEqual("6.22-6.28", weekly_results[0].period)

    def test_private_month_uses_actual_dates(self):
        records = [
            DailyPrivateRecord(date(2026, 6, 22), 10, 5, 100),
            DailyPrivateRecord(date(2026, 6, 27), 20, 10, 200),
        ]

        rows = build_private_monthly_rows(records)

        self.assertEqual(1, len(rows))
        self.assertEqual("6.22-6.27", rows[0]["统计周期"])
        self.assertEqual("2026-06-22", rows[0]["开始日期"])
        self.assertEqual("2026-06-27", rows[0]["结束日期"])
        self.assertEqual(30, rows[0]["新加好友"])

    def test_month_sync_id_is_stable_when_month_data_extends(self):
        table = TableConfig(
            report_id="conversion",
            name="新用户转化率",
            table_id="table",
            integer_fields=frozenset({"新增客户数_SCRM", "新登账号_GDATA"}),
            numeric_fields=frozenset(),
            percentage_fields=frozenset({"新用户转化率"}),
            date_fields=frozenset({"开始日期", "结束日期"}),
        )
        earlier = {
            "周期类型": "月",
            "统计周期": "6.22-6.27",
            "开始日期": "2026-06-22",
            "结束日期": "2026-06-27",
            "新增客户数_SCRM": 100,
            "新登账号_GDATA": 50,
            "新用户转化率": "50.00%",
        }
        later = earlier | {"统计周期": "6.22-6.30", "结束日期": "2026-06-30"}

        self.assertEqual(convert_record(earlier, table)["__sync_id"], convert_record(later, table)["__sync_id"])

    def test_period_counts_count_day_week_month_rows(self):
        rows = [
            {"周期类型": "日"},
            {"周期类型": "日"},
            {"周期类型": "周"},
            {"周期类型": "月"},
            {"周期类型": ""},
        ]

        self.assertEqual({"日": 2, "周": 1, "月": 1}, period_counts(rows))

    def test_sync_preview_summarizes_reports_and_period_counts(self):
        reports = [
            {
                "title": "新用户转化率",
                "rows": [{"周期类型": "日"}, {"周期类型": "周"}],
            },
            {
                "title": "活跃用户关注私域占比",
                "rows": [{"周期类型": "日"}, {"周期类型": "日"}, {"周期类型": "月"}],
            },
        ]

        preview = sync_preview(reports)

        self.assertEqual(5, preview["totalRows"])
        self.assertEqual("新用户转化率：共 2 行（日 1 / 周 1 / 月 0）", preview["reports"][0]["summary"])
        self.assertEqual("活跃用户关注私域占比：共 3 行（日 2 / 周 0 / 月 1）", preview["reports"][1]["summary"])


if __name__ == "__main__":
    unittest.main()
