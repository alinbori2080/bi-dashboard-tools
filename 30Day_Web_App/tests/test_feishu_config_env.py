import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

import feishu_sync  # noqa: E402


class FeishuConfigEnvTest(unittest.TestCase):
    def test_load_config_accepts_env_without_json_file(self):
        with (
            TemporaryDirectory() as temp_dir,
            patch.object(feishu_sync, "CONFIG_PATH", Path(temp_dir) / "missing.json"),
            patch.dict(
                "os.environ",
                {
                    "FEISHU_APP_ID": "env-app-id",
                    "FEISHU_APP_SECRET": "env-secret",
                    "FEISHU_APP_TOKEN": "env-app-token",
                    "FEISHU_DAILY_TABLE_ID": "env-daily-table",
                    "FEISHU_APP_URL": "https://example.feishu.cn/wiki/test",
                },
                clear=True,
            ),
        ):
            config = feishu_sync.load_config()

        self.assertEqual("env-app-id", config["app_id"])
        self.assertEqual("env-secret", config["app_secret"])
        self.assertEqual("env-app-token", config["app_token"])
        self.assertEqual("env-daily-table", config["table_ids"]["daily"])
        self.assertEqual("https://example.feishu.cn/wiki/test", config["app_url"])

    def test_env_values_override_json_config(self):
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "feishu_sync_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "app_id": "json-app-id",
                        "app_secret": "json-secret",
                        "app_token": "json-app-token",
                        "table_ids": {"daily": "json-daily-table"},
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch.object(feishu_sync, "CONFIG_PATH", config_path),
                patch.dict(
                    "os.environ",
                    {
                        "FEISHU_APP_ID": "env-app-id",
                        "FEISHU_APP_SECRET": "env-secret",
                        "FEISHU_APP_TOKEN": "env-app-token",
                        "FEISHU_DAILY_TABLE_ID": "env-daily-table",
                    },
                    clear=True,
                ),
            ):
                config = feishu_sync.load_config()

        self.assertEqual("env-app-id", config["app_id"])
        self.assertEqual("env-secret", config["app_secret"])
        self.assertEqual("env-app-token", config["app_token"])
        self.assertEqual("env-daily-table", config["table_ids"]["daily"])

    def test_config_status_uses_env_values(self):
        with (
            TemporaryDirectory() as temp_dir,
            patch.object(feishu_sync, "CONFIG_PATH", Path(temp_dir) / "missing.json"),
            patch.object(feishu_sync, "STATE_PATH", Path(temp_dir) / "state.json"),
            patch.dict(
                "os.environ",
                {
                    "FEISHU_APP_ID": "env-app-id",
                    "FEISHU_APP_SECRET": "env-secret",
                    "FEISHU_APP_TOKEN": "env-app-token",
                    "FEISHU_DAILY_TABLE_ID": "env-daily-table",
                },
                clear=True,
            ),
        ):
            status = feishu_sync.config_status()

        self.assertTrue(status["ready"])
        self.assertTrue(status["appTokenSet"])
        self.assertTrue(status["tableIdsSet"])


if __name__ == "__main__":
    unittest.main()
