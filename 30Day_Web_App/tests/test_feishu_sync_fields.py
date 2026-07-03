import unittest
import sys
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

import feishu_sync  # noqa: E402


class FeishuSyncFieldMergeTest(unittest.TestCase):
    def test_existing_record_only_updates_available_fields(self):
        local_fields = {
            "统计周期": "6.01",
            "周期类型": "日",
            "开始日期": "2026-06-01",
            "结束日期": "2026-06-01",
            "用户数": 100,
            "次留": 0.25,
            "7日留": 0.10,
            "21日留": None,
            "30日留": None,
            "__key": "日|2026-06-01|2026-06-01",
        }
        remote_fields = {
            "统计周期": "6.01",
            "周期类型": "日",
            "开始日期": "2026-06-01",
            "结束日期": "2026-06-01",
            "次留": 0.20,
            "7日留": 0.09,
            "21日留": 0.08,
            "30日留": 0.07,
        }

        merged, stats = feishu_sync.prepare_incremental_fields(local_fields, remote_fields, is_existing=True)

        self.assertEqual(0.25, merged["次留"])
        self.assertEqual(0.10, merged["7日留"])
        self.assertNotIn("21日留", merged)
        self.assertNotIn("30日留", merged)
        self.assertEqual(3, stats["updatedFields"])
        self.assertEqual(2, stats["skippedFields"])
        self.assertEqual({"暂不可统计或无可用计算结果": 2}, stats["skipReasons"])

    def test_zero_result_is_written(self):
        local_fields = {
            "统计周期": "6.01",
            "周期类型": "日",
            "开始日期": "2026-06-01",
            "结束日期": "2026-06-01",
            "用户数": 0,
            "次留": 0,
            "__key": "日|2026-06-01|2026-06-01",
        }

        merged, stats = feishu_sync.prepare_incremental_fields(local_fields, {}, is_existing=True)

        self.assertIn("用户数", merged)
        self.assertIn("次留", merged)
        self.assertEqual(0, merged["用户数"])
        self.assertEqual(0, merged["次留"])
        self.assertEqual(2, stats["updatedFields"])
        self.assertEqual(0, stats["skippedFields"])

    def test_invalid_field_is_skipped_without_blocking_other_fields(self):
        local_fields = {
            "统计周期": "6.01",
            "周期类型": "日",
            "开始日期": "2026-06-01",
            "结束日期": "2026-06-01",
            "用户数": 100,
            "次留": feishu_sync.INVALID_FIELD,
            "7日留": 0.10,
            "__key": "日|2026-06-01|2026-06-01",
        }

        merged, stats = feishu_sync.prepare_incremental_fields(local_fields, {}, is_existing=True)

        self.assertEqual(100, merged["用户数"])
        self.assertEqual(0.10, merged["7日留"])
        self.assertNotIn("次留", merged)
        self.assertEqual(2, stats["updatedFields"])
        self.assertEqual(1, stats["skippedFields"])
        self.assertEqual({"字段异常或计算失败": 1}, stats["skipReasons"])

    def test_reused_blank_record_writes_identity_fields(self):
        local_fields = {
            "统计周期": "6.01",
            "周期类型": "日",
            "开始日期": "2026-06-01",
            "结束日期": "2026-06-01",
            "用户数": 100,
            "__key": "日|2026-06-01|2026-06-01",
        }

        merged, _ = feishu_sync.prepare_incremental_fields(
            local_fields,
            {},
            is_existing=True,
            preserve_identity_fields=False,
        )

        self.assertEqual("6.01", merged["统计周期"])
        self.assertEqual("日", merged["周期类型"])
        self.assertEqual("2026-06-01", merged["开始日期"])
        self.assertEqual("2026-06-01", merged["结束日期"])


if __name__ == "__main__":
    unittest.main()
