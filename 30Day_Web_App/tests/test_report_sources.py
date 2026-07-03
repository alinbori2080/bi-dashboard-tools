from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

import server  # noqa: E402
import feishu_sync  # noqa: E402


class MissingPath:
    def exists(self) -> bool:
        return False


class ReportSourceTests(unittest.TestCase):
    def test_default_source_is_feishu(self) -> None:
        with patch("server.feishu_sync.fetch_reports_from_feishu", return_value=[{"id": "daily", "rows": []}]):
            payload = server.reports_payload()

        self.assertEqual("feishu", payload["dataSource"])
        self.assertEqual("飞书结果表", payload["sourceName"])
        self.assertEqual([], payload["errors"])

    def test_local_source_requires_existing_result_file(self) -> None:
        with patch("server.feishu_sync.LOCAL_XLSX", MissingPath()):
            payload = server.reports_payload(source="local")

        self.assertEqual("local", payload["dataSource"])
        self.assertEqual([], payload["reports"])
        self.assertEqual("请先刷新数据。", payload["errors"][0]["body"])

    def test_feishu_failure_does_not_fallback_to_local(self) -> None:
        with patch("server.feishu_sync.fetch_reports_from_feishu", side_effect=RuntimeError("飞书读取失败")):
            payload = server.reports_payload(source="feishu")

        self.assertEqual("feishu", payload["dataSource"])
        self.assertEqual([], payload["reports"])
        self.assertIn("飞书读取失败", payload["errors"][0]["body"])

    def test_feishu_read_uses_fixed_fieldnames_without_listing_fields(self) -> None:
        config = {"app_token": "app", "table_ids": {"daily": "table_daily"}}
        records = [
            {
                "fields": {
                    "统计周期": "6.01",
                    "周期类型": "日",
                    "开始日期": "2026-06-01",
                    "结束日期": "2026-06-01",
                    "用户数": 10,
                    "次留": 0.2,
                }
            }
        ]

        with (
            patch("feishu_sync.list_fields", side_effect=AssertionError("should not list fields")),
            patch("feishu_sync.list_records_with_fields", return_value=records) as list_records,
        ):
            report = feishu_sync.fetch_report_from_feishu(config, "token", "daily")

        self.assertEqual("daily", report["id"])
        self.assertEqual("6.01", report["rows"][0]["统计周期"])
        self.assertEqual(10, report["rows"][0]["用户数"])
        self.assertEqual("20.00%", report["rows"][0]["次留"])
        self.assertIn("30日留", list_records.call_args.args[3])

    def test_feishu_sync_uses_single_daily_table_with_period_key(self) -> None:
        self.assertEqual(["daily"], list(feishu_sync.SHEETS))
        self.assertEqual(("周期类型", "开始日期", "结束日期"), feishu_sync.SHEETS["daily"]["key_fields"])


if __name__ == "__main__":
    unittest.main()
