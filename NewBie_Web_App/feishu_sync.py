#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
CONFIG_DIR = APP_DIR / "config"
CONFIG_PATH = CONFIG_DIR / "feishu_sync_config.json"
STATE_PATH = CONFIG_DIR / "feishu_sync_state.json"
CSV_PATH = APP_DIR / "output" / "推送用户留存付费汇总.csv"
API_ROOT = "https://open.feishu.cn/open-apis"
PERCENT_FIELDS = frozenset(
    {
        "次日留存率",
        "3日留存率",
        "7日留存率",
        "大盘次日留存率",
        "大盘3日留存率",
        "大盘7日留存率",
    }
)
TEXT_FIELDS = ("组别",)
INTEGER_FIELDS = ("用户量",)
LTV_FIELDS = (
    "LTV7",
    "LTV7差值",
    "LTV15",
    "LTV15差值",
    "LTV30",
    "LTV30差值",
)
DATE_FIELDS = ("批次日期",)
BATCH_LABEL = re.compile(r"^(\d{1,2})月(\d{1,2})日$")
YEAR_IN_NAME = re.compile(r"(20\d{2})")
CHINA_TZ = timezone(timedelta(hours=8))
BLANK_NUMBER_TEXT = {"", "-", "—", "–", r"\n", "null", "none", "nan", "n/a", "na"}


class SyncError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="创建并同步名将杀推送留存付费飞书多维表格。")
    parser.add_argument("--dry-run", action="store_true", help="只检查配置和本地数据，不写飞书。")
    parser.add_argument("--setup-only", action="store_true", help="只创建多维表格和字段，不同步记录。")
    return parser.parse_args()


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise SyncError(f"未找到飞书配置：{CONFIG_PATH}")
    with CONFIG_PATH.open("r", encoding="utf-8-sig") as file:
        config = json.load(file)
    config["app_secret"] = os.environ.get("FEISHU_APP_SECRET") or config.get("app_secret")
    missing = [name for name in ("app_id", "app_secret") if not config.get(name)]
    if missing:
        raise SyncError("飞书配置缺少：" + ", ".join(missing))
    config.setdefault("base_name", "名将杀推送留存付费")
    config.setdefault("table_name", "推送留存付费")
    return config


def save_config(config: dict[str, Any]) -> None:
    temporary = CONFIG_PATH.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(config, file, ensure_ascii=False, indent=2)
        file.write("\n")
    temporary.replace(CONFIG_PATH)


def load_sync_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"tables": {}}
    with STATE_PATH.open("r", encoding="utf-8-sig") as file:
        state = json.load(file)
    if not isinstance(state.get("tables"), dict):
        raise SyncError("飞书同步状态文件无效")
    return state


def save_sync_state(state: dict[str, Any]) -> None:
    temporary = STATE_PATH.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(state, file, ensure_ascii=False, indent=2)
        file.write("\n")
    temporary.replace(STATE_PATH)


def request_json(
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict[str, Any] | None = None,
    retry: bool = True,
) -> dict[str, Any]:
    if method.upper() == "DELETE":
        raise SyncError("安全限制：飞书同步不允许删除记录，只允许新增或更新。")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    attempts = 3 if retry else 1
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(API_ROOT + path, data=data, headers=headers, method=method)
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            last_error = SyncError(f"飞书 HTTP {exc.code}: {details}")
            if exc.code not in {429, 500, 502, 503, 504} or attempt + 1 == attempts:
                raise last_error from exc
            time.sleep(1.5 * (attempt + 1))
            continue
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = SyncError(f"飞书请求失败：{exc}")
            if attempt + 1 == attempts:
                raise last_error from exc
            time.sleep(1.5 * (attempt + 1))
            continue
        code = payload.get("code", 0)
        if code == 0:
            return payload
        last_error = SyncError(f"飞书 API 错误 {code}: {payload.get('msg', 'unknown error')}")
        if code not in {1254290, 1254291, 1254607, 1255040} or attempt + 1 == attempts:
            raise last_error
        time.sleep(1.5 * (attempt + 1))
    raise last_error or SyncError("飞书请求失败")


def tenant_token(config: dict[str, Any]) -> str:
    payload = request_json(
        "POST",
        "/auth/v3/tenant_access_token/internal",
        body={"app_id": config["app_id"], "app_secret": config["app_secret"]},
    )
    token = payload.get("tenant_access_token")
    if not token:
        raise SyncError("飞书未返回 tenant_access_token")
    return str(token)


def encoded(value: str) -> str:
    return urllib.parse.quote(value, safe="")


def list_tables(token: str, app_token: str) -> list[dict[str, Any]]:
    payload = request_json("GET", f"/bitable/v1/apps/{encoded(app_token)}/tables?page_size=100", token=token)
    return list((payload.get("data") or {}).get("items") or [])


def list_fields(token: str, app_token: str, table_id: str) -> list[dict[str, Any]]:
    payload = request_json(
        "GET",
        f"/bitable/v1/apps/{encoded(app_token)}/tables/{encoded(table_id)}/fields?page_size=100",
        token=token,
    )
    return list((payload.get("data") or {}).get("items") or [])


def create_field(
    token: str,
    app_token: str,
    table_id: str,
    name: str,
    field_type: int,
    formatter: str | None = None,
) -> None:
    body: dict[str, Any] = {"field_name": name, "type": field_type}
    if formatter:
        body["property"] = {"formatter": formatter}
    request_json(
        "POST",
        f"/bitable/v1/apps/{encoded(app_token)}/tables/{encoded(table_id)}/fields",
        token=token,
        body=body,
        retry=False,
    )


def resolve_wiki_target(token: str, config: dict[str, Any]) -> None:
    wiki_token = str(config.get("wiki_token") or "").strip()
    if not wiki_token or config.get("app_token"):
        return
    payload = request_json(
        "GET",
        f"/wiki/v2/spaces/get_node?token={encoded(wiki_token)}",
        token=token,
    )
    node = (payload.get("data") or {}).get("node") or {}
    object_type = str(node.get("obj_type") or "")
    app_token = str(node.get("obj_token") or "")
    if object_type != "bitable" or not app_token:
        raise SyncError(
            f"Wiki 节点不是多维表格，类型={object_type or 'unknown'}"
        )
    config["app_token"] = app_token
    save_config(config)
    print("已从 Wiki 链接解析多维表格 App Token。")


def ensure_schema(token: str, config: dict[str, Any]) -> None:
    app_token = str(config["app_token"])
    table_id = str(config["table_id"])
    fields = list_fields(token, app_token, table_id)
    if not fields:
        raise SyncError("目标数据表没有可识别字段")
    names = {str(field.get("field_name") or "") for field in fields}
    if "批次" not in names:
        primary = next(
            (field for field in fields if field.get("is_primary")),
            fields[0],
        )
        primary_id = str(primary.get("field_id") or "")
        request_json(
            "PUT",
            f"/bitable/v1/apps/{encoded(app_token)}/tables/{encoded(table_id)}/fields/{encoded(primary_id)}",
            token=token,
            body={"field_name": "批次", "type": 1},
        )
    existing_names = {
        str(field.get("field_name") or "")
        for field in list_fields(token, app_token, table_id)
    }
    definitions: list[tuple[str, int, str | None]] = []
    definitions.extend((name, 1, None) for name in TEXT_FIELDS)
    definitions.extend((name, 2, "0") for name in INTEGER_FIELDS)
    definitions.extend((name, 2, "0.00") for name in LTV_FIELDS)
    definitions.extend((name, 2, "0.00%") for name in PERCENT_FIELDS)
    definitions.extend((name, 5, None) for name in DATE_FIELDS)
    created = 0
    for name, field_type, formatter in definitions:
        if name not in existing_names:
            create_field(
                token,
                app_token,
                table_id,
                name,
                field_type,
                formatter,
            )
            created += 1
    print(f"字段检查完成：新建 {created} 个字段。")

def setup_bitable(token: str, config: dict[str, Any]) -> None:
    payload = request_json(
        "POST",
        "/bitable/v1/apps",
        token=token,
        body={"name": config["base_name"]},
        retry=False,
    )
    app = (payload.get("data") or {}).get("app") or {}
    app_token = str(app.get("app_token") or "")
    table_id = str(app.get("default_table_id") or "")
    if not app_token:
        raise SyncError("创建多维表格成功，但未返回 App Token")
    if not table_id:
        tables = list_tables(token, app_token)
        if tables:
            table_id = str(tables[0].get("table_id") or "")
    if not table_id:
        table_payload = request_json(
            "POST",
            f"/bitable/v1/apps/{encoded(app_token)}/tables",
            token=token,
            body={"table": {"name": config["table_name"], "default_view_name": "全部数据"}},
            retry=False,
        )
        table_id = str((((table_payload.get("data") or {}).get("table") or {}).get("table_id") or ""))
    if not table_id:
        raise SyncError("创建多维表格成功，但未能定位数据表 ID")

    fields = list_fields(token, app_token, table_id)
    primary = next((field for field in fields if field.get("is_primary")), fields[0] if fields else None)
    if primary:
        primary_id = str(primary.get("field_id") or "")
        request_json(
            "PUT",
            f"/bitable/v1/apps/{encoded(app_token)}/tables/{encoded(table_id)}/fields/{encoded(primary_id)}",
            token=token,
            body={"field_name": "批次", "type": 1},
        )
    else:
        create_field(token, app_token, table_id, "批次", 1)

    existing_names = {str(field.get("field_name") or "") for field in list_fields(token, app_token, table_id)}
    definitions: list[tuple[str, int, str | None]] = []
    definitions.extend((name, 1, None) for name in TEXT_FIELDS)
    definitions.extend((name, 2, "0") for name in INTEGER_FIELDS)
    definitions.extend((name, 2, "0.00") for name in LTV_FIELDS)
    definitions.extend((name, 2, "0.00%") for name in PERCENT_FIELDS)
    definitions.extend((name, 5, None) for name in DATE_FIELDS)
    for name, field_type, formatter in definitions:
        if name not in existing_names:
            create_field(token, app_token, table_id, name, field_type, formatter)

    config["app_token"] = app_token
    config["table_id"] = table_id
    config["app_url"] = str(app.get("url") or "")
    save_config(config)
    print(f"已创建新的飞书多维表格：{config['base_name']}")
    if config["app_url"]:
        print(f"飞书链接：{config['app_url']}")


def source_year() -> int:
    candidates = [
        item
        for item in DATA_DIR.iterdir()
        if item.is_file()
        and item.name.startswith("名将杀 私域需求")
        and item.suffix.lower() == ".xlsx"
        and not item.name.startswith("~$")
    ]
    if not candidates:
        return datetime.now(CHINA_TZ).year
    source = max(candidates, key=lambda item: item.stat().st_mtime)
    match = YEAR_IN_NAME.search(source.stem)
    return int(match.group(1)) if match else datetime.now(CHINA_TZ).year


def batch_timestamp(batch: str, year: int) -> int:
    match = BATCH_LABEL.fullmatch(batch)
    if not match:
        raise SyncError(f"无法识别批次日期：{batch}")
    value = datetime(year, int(match.group(1)), int(match.group(2)), tzinfo=CHINA_TZ)
    return int(value.timestamp() * 1000)


def source_year() -> int:
    candidates = [
        item
        for item in DATA_DIR.iterdir()
        if item.is_file()
        and item.name.startswith("名将杀 私域需求")
        and item.suffix.lower() == ".xlsx"
        and not item.name.startswith("~$")
    ]
    if not candidates:
        return datetime.now(CHINA_TZ).year
    source = max(candidates, key=lambda item: item.stat().st_mtime)
    match = YEAR_IN_NAME.search(source.stem)
    return int(match.group(1)) if match else datetime.now(CHINA_TZ).year


def batch_timestamp(batch: str, year: int) -> int:
    match = BATCH_LABEL.fullmatch(batch)
    if not match:
        raise SyncError(f"无法识别批次日期：{batch}")
    value = datetime(year, int(match.group(1)), int(match.group(2)), tzinfo=CHINA_TZ)
    return int(value.timestamp() * 1000)


def parse_percent(value: str) -> float:
    text = value.strip()
    if text.lower() in BLANK_NUMBER_TEXT:
        raise ValueError("blank percent")
    return float(text.rstrip("%")) / 100


def read_local_records() -> list[dict[str, Any]]:
    if not CSV_PATH.exists():
        raise SyncError(f"未找到本地结果：{CSV_PATH}")
    result: list[dict[str, Any]] = []
    current_batch = ""
    year = source_year()
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        missing = set(("批次", "组别", *INTEGER_FIELDS, *LTV_FIELDS, *PERCENT_FIELDS)).difference(
            reader.fieldnames or []
        )
        if missing:
            raise SyncError("CSV 缺少字段：" + ", ".join(sorted(missing)))
        for row in reader:
            if row["批次"].strip():
                current_batch = row["批次"].strip()
            if not current_batch:
                raise SyncError("CSV 对照组行之前没有批次")
            fields: dict[str, Any] = {
                "批次": current_batch,
                "组别": row["组别"].strip(),
                "批次日期": batch_timestamp(current_batch, year),
            }
            fields["用户量"] = int(float(row["用户量"]))
            for name in LTV_FIELDS:
                value = row[name].strip()
                if value.lower() in BLANK_NUMBER_TEXT or "（LTV" in value:
                    fields[name] = None
                else:
                    fields[name] = float(value.replace(",", ""))
            for name in PERCENT_FIELDS:
                value = row[name].strip()
                fields[name] = None if value.lower() in BLANK_NUMBER_TEXT else parse_percent(value)
            fields["__key"] = f"{current_batch}|{row['组别'].strip()}"
            result.append(fields)
    return result


def remote_text(value: Any) -> str:
    if isinstance(value, list):
        return "".join(
            str(item.get("text") or "") if isinstance(item, dict) else str(item)
            for item in value
        ).strip()
    return str(value or "").strip()


def remote_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = remote_text(value).replace(",", "").replace("%", "").strip()
    if text.lower() in BLANK_NUMBER_TEXT:
        return None
    return float(text)


def remote_metric(value: Any) -> str:
    number = remote_number(value)
    return "" if number is None else f"{number:,.2f}"


def remote_int(value: Any) -> int | str:
    number = remote_number(value)
    return "" if number is None else int(number)


def remote_percent(value: Any) -> str:
    number = remote_number(value)
    if number is None:
        return ""
    if not isinstance(value, (int, float)) and number > 1:
        number = number / 100
    return f"{number:.2%}"


def remote_date(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value) / 1000, CHINA_TZ).date().isoformat()
    text = remote_text(value)
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text[:10]).date().isoformat()
    except ValueError:
        return text


def list_remote_records(token: str, app_token: str, table_id: str) -> list[dict[str, Any]]:
    return list_remote_records_with_fields(token, app_token, table_id, ["批次", "组别"])


def list_remote_records_with_fields(
    token: str,
    app_token: str,
    table_id: str,
    field_names: list[str],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    page_token: str | None = None
    while True:
        query = {"page_size": "500"}
        if page_token:
            query["page_token"] = page_token
        payload = request_json(
            "POST",
            f"/bitable/v1/apps/{encoded(app_token)}/tables/{encoded(table_id)}/records/search?{urllib.parse.urlencode(query)}",
            token=token,
            body={"field_names": field_names},
        )
        data = payload.get("data") or {}
        result.extend(data.get("items") or [])
        if not data.get("has_more"):
            return result
        page_token = data.get("page_token")


def table_source(config: dict[str, Any], record_count: int) -> dict[str, Any]:
    return {
        "role": "飞书结果表",
        "name": str(config.get("table_name") or "推送留存付费"),
        "path": f"{config.get('app_token', '')}/{config.get('table_id', '')}",
        "size": record_count,
        "updatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def group_rank(group: str) -> int:
    if "实验" in group or "A" in group.upper():
        return 0
    if "对照" in group or "B" in group.upper():
        return 1
    return 2


def fetch_reports_from_feishu() -> list[dict[str, Any]]:
    import newbie_core

    config = load_config()
    token = tenant_token(config)
    resolve_wiki_target(token, config)
    if not config.get("app_token") or not config.get("table_id"):
        raise SyncError("飞书配置尚未绑定多维表格，无法作为数据源。")

    field_names = [*newbie_core.fieldnames(), "批次日期"]
    records = list_remote_records_with_fields(token, config["app_token"], config["table_id"], field_names)
    parsed: list[dict[str, Any]] = []
    for record in records:
        source = record.get("fields") or {}
        batch = remote_text(source.get("批次"))
        group = remote_text(source.get("组别"))
        if not batch or not group:
            continue
        row: dict[str, Any] = {
            "批次": batch,
            "组别": group,
            "用户量": remote_int(source.get("用户量")),
            "批次日期": remote_date(source.get("批次日期")),
        }
        for name in LTV_FIELDS:
            row[name] = remote_metric(source.get(name))
        for name in PERCENT_FIELDS:
            row[name] = remote_percent(source.get(name))
        parsed.append(row)

    if not parsed:
        raise SyncError("飞书结果表没有可展示的数据。")

    parsed.sort(key=lambda row: (str(row.get("批次日期") or ""), str(row.get("批次") or ""), group_rank(str(row.get("组别") or ""))))
    rows: list[dict[str, Any]] = []
    current_batch = ""
    for row in parsed:
        output_row = {name: row.get(name, "") for name in newbie_core.fieldnames()}
        output_row["批次日期"] = row.get("批次日期", "")
        batch = str(row.get("批次") or "")
        if batch == current_batch:
            output_row["批次"] = ""
        else:
            output_row["批次"] = batch
            current_batch = batch
        rows.append(output_row)

    report = {
        "id": "push_retention_ltv",
        "title": "推送用户留存付费汇总",
        "description": "从飞书结果表读取的推送批次留存、LTV 和差值。",
        "source": "飞书结果表",
        "sourceMode": "feishu",
        "skippedSheets": [],
        "fieldnames": newbie_core.fieldnames(),
        "summary": newbie_core.report_summary(rows),
        "sources": [table_source(config, len(rows))],
        "rows": rows,
    }
    return [report]


def write_record(
    token: str,
    app_token: str,
    table_id: str,
    fields: dict[str, Any],
    record_id: str | None,
) -> str:
    # data 目录可能只放部分批次；空值不写入，避免清空飞书历史字段。
    fields = {name: value for name, value in fields.items() if value is not None}
    base = f"/bitable/v1/apps/{encoded(app_token)}/tables/{encoded(table_id)}/records"
    if record_id:
        request_json("PUT", f"{base}/{encoded(record_id)}", token=token, body={"fields": fields})
        return record_id
    payload = request_json("POST", base, token=token, body={"fields": fields}, retry=False)
    record = ((payload.get("data") or {}).get("record") or {})
    new_record_id = record.get("record_id") or record.get("id")
    if not new_record_id:
        raise SyncError("飞书新增记录后未返回 record_id")
    return str(new_record_id)


def sync_records(
    token: str,
    config: dict[str, Any],
    dry_run: bool,
    state: dict[str, Any],
) -> tuple[int, int]:
    table_state = state["tables"].setdefault(str(config["table_id"]), {})
    local = read_local_records()
    local.sort(key=lambda fields: fields["__key"] in table_state)
    remote = list_remote_records(token, config["app_token"], config["table_id"])
    remote_by_key: dict[str, str] = {}
    blank_record_ids: list[str] = []
    used_record_ids: set[str] = set()
    for record in remote:
        fields = record.get("fields") or {}
        batch = remote_text(fields.get("批次"))
        group = remote_text(fields.get("组别"))
        record_id = str(record.get("record_id") or record.get("id") or "")
        if batch and group and record_id:
            remote_by_key[f"{batch}|{group}"] = record_id
        elif record_id:
            blank_record_ids.append(record_id)

    created = 0
    updated = 0
    for item in local:
        fields = item.copy()
        key = str(fields.pop("__key"))
        record_id = table_state.get(key)
        if record_id in used_record_ids:
            record_id = None
        if record_id is None:
            record_id = remote_by_key.get(key)
        if record_id is None:
            record_id = next(
                (candidate for candidate in blank_record_ids if candidate not in used_record_ids),
                None,
            )

        was_existing = bool(record_id)
        if not dry_run:
            try:
                record_id = write_record(
                    token, config["app_token"], config["table_id"], fields, record_id
                )
            except SyncError as exc:
                if record_id and ("1254043" in str(exc) or "1254006" in str(exc)):
                    record_id = write_record(
                        token, config["app_token"], config["table_id"], fields, None
                    )
                    was_existing = False
                else:
                    raise
            table_state[key] = record_id
            save_sync_state(state)
            time.sleep(0.08)

        if was_existing:
            updated += 1
        else:
            created += 1
        if record_id:
            used_record_ids.add(record_id)
    return created, updated


def config_status() -> dict[str, Any]:
    exists = CONFIG_PATH.exists()
    state_exists = STATE_PATH.exists()
    status: dict[str, Any] = {
        "path": str(CONFIG_PATH),
        "statePath": str(STATE_PATH),
        "exists": exists,
        "stateExists": state_exists,
        "ready": False,
        "appUrl": "",
        "message": "未找到飞书配置",
    }
    if not exists:
        return status
    try:
        with CONFIG_PATH.open("r", encoding="utf-8-sig") as file:
            config = json.load(file)
    except Exception as exc:  # noqa: BLE001 - reported to local UI.
        status["message"] = f"飞书配置读取失败：{exc}"
        return status
    missing = [name for name in ("app_id", "app_secret") if not config.get(name)]
    status.update(
        {
            "ready": not missing,
            "appTokenSet": bool(config.get("app_token")),
            "tableIdSet": bool(config.get("table_id")),
            "appUrl": str(config.get("app_url") or ""),
            "message": "配置可用" if not missing else "飞书配置缺少：" + ", ".join(missing),
        }
    )
    return status


def sync_reports(reports: list[dict[str, Any]], *, dry_run: bool = False) -> dict[str, Any]:
    report = next((item for item in reports if item.get("id") == "push_retention_ltv"), None)
    if report is None:
        raise SyncError("没有可同步的推送留存付费报表，请先刷新数据。")
    import newbie_core

    newbie_core.write_report_csv(report)
    local = read_local_records()
    config = load_config()
    state = load_sync_state()
    token = tenant_token(config)
    resolve_wiki_target(token, config)
    if not config.get("app_token") or not config.get("table_id"):
        if dry_run:
            raise SyncError("飞书配置尚未绑定多维表格，dry-run 不会自动创建。")
        setup_bitable(token, config)
    ensure_schema(token, config)
    created, updated = sync_records(token, config, dry_run=dry_run, state=state)
    action = "预计同步" if dry_run else "同步完成"
    return {
        "ok": True,
        "blocked": False,
        "dryRun": dry_run,
        "created": created,
        "updated": updated,
        "records": len(local),
        "appUrl": str(config.get("app_url") or ""),
        "message": f"{action}：新增 {created} 行，更新 {updated} 行。",
    }


def main() -> int:
    args = parse_args()
    config = load_config()
    local = read_local_records()
    print(f"本地待同步记录：{len(local)} 行")
    state = load_sync_state()
    token = tenant_token(config)
    print("飞书鉴权成功。")
    resolve_wiki_target(token, config)
    if not config.get("app_token") or not config.get("table_id"):
        setup_bitable(token, config)
    ensure_schema(token, config)
    if args.setup_only:
        return 0
    created, updated = sync_records(token, config, dry_run=args.dry_run, state=state)
    action = "预计" if args.dry_run else "同步完成"
    print(f"{action}：新增 {created} 行，更新 {updated} 行。")
    if config.get("app_url"):
        print(f"飞书链接：{config['app_url']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"运行失败：{exc}")
        raise SystemExit(1)
