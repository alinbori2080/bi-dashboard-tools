from __future__ import annotations

import sys
import unittest
import zipfile
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

import retention30_core as core  # noqa: E402


def make_daily(day: date, users: int, retention: dict[int, float]) -> core.DailyRetention:
    login_counts = {target: int(users * retention.get(target, 0)) for target in core.RETENTION_DAYS}
    return core.DailyRetention(
        day=day,
        users=users,
        login_counts=login_counts,
        mature={target: target <= 14 for target in core.RETENTION_DAYS},
    )


class SummaryFieldTests(unittest.TestCase):
    def test_summary_rows_keep_base_fields_without_enhanced_comparisons(self) -> None:
        start = date(2026, 1, 5)
        items = [
            make_daily(start + timedelta(days=offset), 10, {2: 0.2, 3: 0.1, 7: 0.1, 14: 0.0})
            for offset in range(7)
        ]
        market = {
            start + timedelta(days=offset): core.MarketDaily(new_accounts=100, rates={2: 0.1, 3: 0.05, 7: 0.05})
            for offset in range(7)
        }

        rows = core.summary_rows(items, market, start + timedelta(days=20))
        weekly = rows[0]

        self.assertEqual("周", weekly["周期类型"])
        self.assertEqual(70, weekly["用户数"])
        self.assertEqual("20.00%", weekly["次留"])
        self.assertEqual("10.00%", weekly["大盘次留"])
        self.assertNotIn("次留成熟用户数", weekly)
        self.assertNotIn("用户数较上期", weekly)
        self.assertNotIn("次留较前4周", weekly)

    def test_summary_fieldnames_exclude_enhanced_fields(self) -> None:
        fields = core.summary_fieldnames()

        self.assertIn("次留", fields)
        self.assertIn("30日留", fields)
        self.assertIn("次留-大盘次留", fields)
        self.assertNotIn("次留成熟用户数", fields)
        self.assertNotIn("用户数较上期", fields)
        self.assertNotIn("次留较前4周", fields)

    def test_summary_rows_include_partial_months(self) -> None:
        days = [
            date(2026, 4, 26),
            date(2026, 5, 26),
            date(2026, 5, 27),
            date(2026, 6, 1),
        ]
        items = [make_daily(day, 10, {2: 0.2, 3: 0.1, 7: 0.1, 14: 0.0}) for day in days]

        rows = core.summary_rows(items, {}, date(2026, 6, 30))
        monthly = [row for row in rows if row["周期类型"] == "月"]

        self.assertEqual(["4.26", "5.26-5.27", "6.01"], [row["统计周期"] for row in monthly])
        self.assertEqual(date(2026, 4, 26).isoformat(), monthly[0]["开始日期"])
        self.assertEqual(date(2026, 4, 26).isoformat(), monthly[0]["结束日期"])
        self.assertEqual(date(2026, 5, 26).isoformat(), monthly[1]["开始日期"])
        self.assertEqual(date(2026, 5, 27).isoformat(), monthly[1]["结束日期"])

    def test_summary_rows_include_partial_weeks(self) -> None:
        days = [
            date(2026, 5, 26),
            date(2026, 5, 27),
            date(2026, 6, 1),
        ]
        items = [make_daily(day, 10, {2: 0.2, 3: 0.1, 7: 0.1, 14: 0.0}) for day in days]

        rows = core.summary_rows(items, {}, date(2026, 6, 30))
        weekly = [row for row in rows if row["周期类型"] == "周"]

        self.assertEqual(["5.26-5.27", "6.01"], [row["统计周期"] for row in weekly])
        self.assertEqual(date(2026, 5, 26).isoformat(), weekly[0]["开始日期"])
        self.assertEqual(date(2026, 5, 27).isoformat(), weekly[0]["结束日期"])

    def test_daily_rows_include_period_fields(self) -> None:
        day = date(2026, 6, 1)
        rows = core.detail_rows([make_daily(day, 10, {2: 0.2})], {}, date(2026, 6, 30))

        self.assertEqual("日", rows[0]["周期类型"])
        self.assertEqual("6.01", rows[0]["统计周期"])
        self.assertEqual("2026-06-01", rows[0]["开始日期"])
        self.assertEqual("2026-06-01", rows[0]["结束日期"])
        self.assertNotIn("汇总周期", rows[0])
        self.assertNotIn("日期", rows[0])
        self.assertNotIn("日期值", rows[0])
        self.assertNotIn("天数", rows[0])

    def test_write_all_reports_outputs_single_daily_sheet(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "result.xlsx"
            report = {
                "id": "daily",
                "rows": [
                    {
                        "统计周期": "6.01",
                        "周期类型": "日",
                        "开始日期": "2026-06-01",
                        "结束日期": "2026-06-01",
                        "用户数": 10,
                    }
                ],
            }

            with patch.object(core, "DEFAULT_OUTPUT", output):
                core.write_all_reports([report])

            with zipfile.ZipFile(output) as workbook:
                workbook_xml = workbook.read("xl/workbook.xml").decode("utf-8")

        self.assertIn('name="每日结果"', workbook_xml)
        self.assertNotIn('name="汇总结果"', workbook_xml)


if __name__ == "__main__":
    unittest.main()
