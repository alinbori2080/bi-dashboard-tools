#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import retention30_core

APP_DIR = Path(__file__).resolve().parent
CONFIG_DIR = APP_DIR / "config"
CONFIG_PATH = CONFIG_DIR / "feishu_sync_config.json"
STATE_PATH = CONFIG_DIR / "feishu_sync_state.json"
LOCAL_XLSX = APP_DIR / "output" / "30日留存结果.xlsx"
API_ROOT = "https://open.feishu.cn/open-apis"
SHEETS = {
    "daily": {"sheet_name": "每日结果", "table_name": "每日结果", "key_fields": ("周期类型", "开始日期", "结束日期")},
}
CHINA_TZ = timezone(timedelta(hours=8))
INTEGER_FIELDS = {"用户数", "新登账号", "已统计最高留存日"}
DATE_FIELDS = {"开始日期", "结束日期", "统计截止日"}
TEXT_FIELDS = {"统计周期", "周期类型"}
PERCENT_FIELD_KEYWORDS = ("留", "大盘")
IDENTITY_FIELDS = {"统计周期", "周期类型", "开始日期", "结束日期"}
INVALID_FIELD = object()
SKIP_EMPTY_REASON = "暂不可统计或无可用计算结果"
SKIP_INVALID_REASON = "字段异常或计算失败"


class SyncError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="同步 30 日留存结果到飞书多维表格。")
    parser.add_argument("--dry-run", action="store_true", help="只检查本地数据和配置，不写入飞书。")
    parser.add_argument("--setup-only", action="store_true", help="只创建/检查多维表格和字段，不同步记录。")
    return parser.parse_args()


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise SyncError(f"未找到飞书配置：{CONFIG_PATH}。请从旧工具迁移配置，或按 README 填写后再同步。")
    with CONFIG_PATH.open("r", encoding="utf-8-sig") as file:
        config = json.load(file)
    config["app_secret"] = os.environ.get("FEISHU_APP_SECRET") or config.get("app_secret")
    missing = [name for name in ("app_id", "app_secret") if not config.get(name)]
    if missing:
        raise SyncError("飞书配置缺少：" + ", ".join(missing))
    config.setdefault("base_name", "名将杀30日留存")
    config.setdefault("table_names", {key: value["table_name"] for key, value in SHEETS.items()})
    config.setdefault("table_ids", {})
    return config


def valid_url(value: object) -> str:
    text = str(value or "").strip()
    parsed = urlparse(text)
    return text if parsed.scheme in {"http", "https"} and parsed.netloc else ""


def feishu_links(config: dict[str, Any]) -> list[dict[str, str]]:
    raw_links = configured_feishu_links(config)
    return [
        {
            "label": item["label"],
            "url": item["url"],
        }
        for item in raw_links
    ]


def configured_feishu_links(config: dict[str, Any]) -> list[dict[str, str]]:
    base_url = valid_url(config.get("app_url") or config.get("base_url") or config.get("url"))
    table_urls = config.get("table_urls") or {}
    if base_url and not table_urls and not config.get("daily_table_url") and not config.get("summary_table_url"):
        return [{"target": "app", "label": "飞书结果表", "url": base_url}]
    return [
        {
            "target": "daily",
            "label": "飞书结果表（每日结果）",
            "url": valid_url(table_urls.get("daily") if isinstance(table_urls, dict) else "") or valid_url(config.get("daily_table_url")) or base_url,
        }
    ]


def feishu_link_url(target: str) -> str:
    config = load_config()
    links = configured_feishu_links(config)
    for item in links:
        if item["target"] == target:
            return item["url"]
    if len(links) == 1:
        return links[0]["url"]
    return ""


def save_config(config: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    temporary = CONFIG_PATH.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(config, file, ensure_ascii=False, indent=2)
        file.write("\n")
    temporary.replace(CONFIG_PATH)


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"tables": {}}
    with STATE_PATH.open("r", encoding="utf-8-sig") as file:
        state = json.load(file)
    state.setdefault("tables", {})
    return state


def save_state(state: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(state, file, ensure_ascii=False, indent=2)
        file.write("\n")
    temporary.replace(STATE_PATH)


def encoded(value: str) -> str:
    return urllib.parse.quote(value, safe="")


def network_error_message(exc: Exception, attempts: int) -> str:
    text = str(exc)
    if isinstance(exc, urllib.error.URLError):
        text = str(exc.reason)
    if "UNEXPECTED_EOF_WHILE_READING" in text or "EOF occurred in violation of protocol" in text:
        return f"飞书请求失败：网络连接被中途断开（SSL EOF），已重试 {attempts} 次。请稍后重试，或检查本机网络/代理。"
    return f"飞书请求失败：{text}"


def request_json(
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict[str, Any] | None = None,
    retry: bool = True,
) -> dict[str, Any]:
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
        "Connection": "close",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    attempts = 4 if retry else 1
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
        except (urllib.error.URLError, TimeoutError, ssl.SSLError, ConnectionError, OSError, json.JSONDecodeError) as exc:
            last_error = SyncError(network_error_message(exc, attempts))
            if attempt + 1 == attempts:
                raise last_error from exc
            time.sleep(1.5 * (attempt + 1))
            continue
        code = payload.get("code", 0)
        if code in {0, 1254606}:
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


def list_tables(token: str, app_token: str) -> list[dict[str, Any]]:
    payload = request_json("GET", f"/bitable/v1/apps/{encoded(app_token)}/tables?page_size=100", token=token)
    return list((payload.get("data") or {}).get("items") or [])


def create_table(token: str, app_token: str, table_name: str) -> str:
    payload = request_json(
        "POST",
        f"/bitable/v1/apps/{encoded(app_token)}/tables",
        token=token,
        body={"table": {"name": table_name, "default_view_name": "全部数据"}},
        retry=False,
    )
    table_id = str((((payload.get("data") or {}).get("table") or {}).get("table_id") or ""))
    if not table_id:
        raise SyncError(f"创建飞书数据表失败：{table_name}")
    return table_id


def list_fields(token: str, app_token: str, table_id: str) -> list[dict[str, Any]]:
    payload = request_json(
        "GET",
        f"/bitable/v1/apps/{encoded(app_token)}/tables/{encoded(table_id)}/fields?page_size=100",
        token=token,
    )
    return list((payload.get("data") or {}).get("items") or [])


def create_field(token: str, app_token: str, table_id: str, name: str, field_type: int, formatter: str | None = None) -> None:
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


def rename_primary_field(token: str, app_token: str, table_id: str, name: str) -> None:
    fields = list_fields(token, app_token, table_id)
    primary = next((field for field in fields if field.get("is_primary")), fields[0] if fields else None)
    if not primary:
        create_field(token, app_token, table_id, name, 1)
        return
    primary_id = str(primary.get("field_id") or "")
    request_json(
        "PUT",
        f"/bitable/v1/apps/{encoded(app_token)}/tables/{encoded(table_id)}/fields/{encoded(primary_id)}",
        token=token,
        body={"field_name": name, "type": 1},
    )


def setup_bitable(token: str, config: dict[str, Any]) -> None:
    if not config.get("app_token"):
        payload = request_json("POST", "/bitable/v1/apps", token=token, body={"name": config["base_name"]}, retry=False)
        app = (payload.get("data") or {}).get("app") or {}
        config["app_token"] = str(app.get("app_token") or "")
        config["app_url"] = str(app.get("url") or "")
        default_table_id = str(app.get("default_table_id") or "")
        if not config["app_token"]:
            raise SyncError("创建多维表格成功，但未返回 App Token")
        if default_table_id:
            config["table_ids"]["daily"] = default_table_id
        save_config(config)

    app_token = str(config["app_token"])
    table_names = config.get("table_names") or {}
    table_ids = config.setdefault("table_ids", {})
    existing = {str(item.get("name") or ""): str(item.get("table_id") or "") for item in list_tables(token, app_token)}
    for key, meta in SHEETS.items():
        if table_ids.get(key):
            continue
        table_name = str(table_names.get(key) or meta["table_name"])
        table_ids[key] = existing.get(table_name) or create_table(token, app_token, table_name)
        save_config(config)


def is_integer_field(name: str) -> bool:
    return (
        name in INTEGER_FIELDS
        or name.endswith("成熟用户数")
        or name in {"用户数较上期", "用户数较前4周"}
    )


def is_percent_field(name: str) -> bool:
    if name.endswith("比例"):
        return True
    if "较" in name:
        return False
    return any(keyword in name for keyword in PERCENT_FIELD_KEYWORDS)


def field_definition(name: str) -> tuple[int, str | None]:
    if name in DATE_FIELDS:
        return 5, None
    if is_integer_field(name):
        return 2, "0"
    if name in TEXT_FIELDS:
        return 1, None
    if is_percent_field(name):
        return 2, "0.00%"
    if "较" in name:
        return 1, None
    return 1, None


def ensure_schema(token: str, config: dict[str, Any], key: str, headers: list[str]) -> None:
    app_token = str(config["app_token"])
    table_id = str(config["table_ids"][key])
    existing = {str(field.get("field_name") or "") for field in list_fields(token, app_token, table_id)}
    created = 0
    for name in headers:
        if name in existing:
            continue
        field_type, formatter = field_definition(name)
        create_field(token, app_token, table_id, name, field_type, formatter)
        created += 1
    print(f"{SHEETS[key]['table_name']} 字段检查完成：新建 {created} 个字段。")


def read_local_sheet(sheet_name: str) -> tuple[list[str], list[dict[str, Any]]]:
    if not LOCAL_XLSX.exists():
        raise SyncError(f"未找到本地结果：{LOCAL_XLSX}。请先运行 thirty_day_retention.py。")
    try:
        rows = retention30_core.read_xlsx_rows(LOCAL_XLSX, sheet_name)
    except ValueError as exc:
        raise SyncError(f"本地结果缺少 sheet：{sheet_name}")
    except Exception as exc:
        raise SyncError(f"读取本地结果失败：{exc}") from exc
    if not rows:
        raise SyncError(f"本地 sheet 为空：{sheet_name}")
    headers = [str(value).strip() if value is not None else "" for value in rows[0]]
    records: list[dict[str, Any]] = []
    for raw in rows[1:]:
        row = {headers[index]: value for index, value in enumerate(raw) if index < len(headers)}
        if any(value not in (None, "") for value in row.values()):
            records.append(row)
    return headers, records


def date_timestamp(value: Any) -> int:
    if isinstance(value, datetime):
        day = value.date()
    elif isinstance(value, date):
        day = value
    else:
        day = datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    return int(datetime(day.year, day.month, day.day, tzinfo=CHINA_TZ).timestamp() * 1000)


def normalize_value(name: str, value: Any) -> Any:
    if value is None or value == "" or value == "-":
        return None
    if name in DATE_FIELDS:
        return date_timestamp(value)
    if is_integer_field(name):
        return int(float(str(value).replace(",", "")))
    if is_percent_field(name):
        text = str(value).strip()
        return float(text.rstrip("%")) / 100 if text.endswith("%") else float(text)
    return str(value).strip()


def empty_field_stats() -> dict[str, Any]:
    return {"createdFields": 0, "updatedFields": 0, "skippedFields": 0, "skipReasons": {}}


def add_skip_reason(stats: dict[str, Any], reason: str) -> None:
    stats["skippedFields"] += 1
    reasons = stats.setdefault("skipReasons", {})
    reasons[reason] = reasons.get(reason, 0) + 1


def merge_field_stats(target: dict[str, Any], source: dict[str, Any]) -> None:
    target["createdFields"] += int(source.get("createdFields") or 0)
    target["updatedFields"] += int(source.get("updatedFields") or 0)
    target["skippedFields"] += int(source.get("skippedFields") or 0)
    target_reasons = target.setdefault("skipReasons", {})
    for reason, count in (source.get("skipReasons") or {}).items():
        target_reasons[reason] = target_reasons.get(reason, 0) + int(count or 0)


def prepare_incremental_fields(
    local_fields: dict[str, Any],
    remote_fields: dict[str, Any] | None,
    *,
    is_existing: bool,
    preserve_identity_fields: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    fields: dict[str, Any] = {}
    stats = empty_field_stats()
    for name, value in local_fields.items():
        if name == "__key":
            continue
        if is_existing and preserve_identity_fields and name in IDENTITY_FIELDS:
            continue
        if value is INVALID_FIELD:
            add_skip_reason(stats, SKIP_INVALID_REASON)
            continue
        if value is None:
            add_skip_reason(stats, SKIP_EMPTY_REASON)
            continue
        fields[name] = value
        if is_existing:
            stats["updatedFields"] += 1
        else:
            stats["createdFields"] += 1
    return fields, stats


def local_records(key: str) -> tuple[list[str], list[dict[str, Any]]]:
    headers, rows = read_local_sheet(SHEETS[key]["sheet_name"])
    normalized: list[dict[str, Any]] = []
    for row in rows:
        fields = {}
        for name in headers:
            try:
                fields[name] = normalize_value(name, row.get(name))
            except (TypeError, ValueError):
                fields[name] = INVALID_FIELD
        record_key = "|".join(str(fields.get(name) or "") for name in SHEETS[key]["key_fields"])
        if not record_key.replace("|", ""):
            continue
        fields["__key"] = record_key
        normalized.append(fields)
    return headers, normalized


def remote_text(value: Any) -> str:
    if isinstance(value, list):
        return "".join(str(item.get("text") or "") if isinstance(item, dict) else str(item) for item in value).strip()
    return str(value or "").strip()


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


def report_cell_value(name: str, value: Any) -> Any:
    if value in (None, ""):
        return ""
    if name in DATE_FIELDS:
        return remote_date(value)
    if is_integer_field(name):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return remote_text(value)
    if is_percent_field(name):
        try:
            return f"{float(value):.2%}"
        except (TypeError, ValueError):
            return remote_text(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return remote_text(value) if isinstance(value, list) else value


def parse_cutoff(rows: list[dict[str, Any]]) -> date:
    dates = []
    for row in rows:
        raw = row.get("统计截止日") or row.get("结束日期")
        if not raw:
            continue
        try:
            dates.append(datetime.fromisoformat(str(raw)[:10]).date())
        except ValueError:
            continue
    return max(dates) if dates else date.today()


def report_payload_from_rows(key: str, rows: list[dict[str, Any]], fieldnames: list[str]) -> dict[str, Any]:
    return {
        "id": "daily",
        "title": "每日结果",
        "description": "按日、周、月展示私域用户 2-30 日留存，并对比 GDATA 大盘留存。",
        "fieldnames": fieldnames,
        "summary": retention30_core.daily_report_summary([row for row in rows if row.get("周期类型") == "日"], parse_cutoff(rows)),
        "rows": rows,
    }


def report_fieldnames(key: str) -> list[str]:
    return retention30_core.detail_fieldnames()


def normalized_report_row(raw_fields: dict[str, Any], fieldnames: list[str]) -> dict[str, Any]:
    return {name: report_cell_value(name, raw_fields.get(name)) for name in fieldnames}


def read_local_report_rows(sheet_name: str) -> tuple[list[str], list[dict[str, Any]]]:
    headers, records = read_local_sheet(sheet_name)
    rows: list[dict[str, Any]] = []
    for record in records:
        rows.append({name: report_cell_value(name, record.get(name)) for name in headers})
    return headers, rows


def fetch_reports_from_local_file() -> list[dict[str, Any]]:
    if not LOCAL_XLSX.exists():
        raise SyncError("请先刷新数据。")
    reports = []
    for key, meta in SHEETS.items():
        _, rows = read_local_report_rows(meta["sheet_name"])
        fieldnames = report_fieldnames(key)
        rows = [normalized_report_row(row, fieldnames) for row in rows]
        reports.append(report_payload_from_rows(key, rows, fieldnames))
    return reports


def list_records_with_fields(token: str, app_token: str, table_id: str, field_names: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
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
        records.extend(data.get("items") or [])
        if not data.get("has_more"):
            return records
        page_token = data.get("page_token")


def existing_fieldnames(token: str, app_token: str, table_id: str) -> set[str]:
    return {str(field.get("field_name") or "") for field in list_fields(token, app_token, table_id)}


def list_records_with_available_fields(
    token: str,
    app_token: str,
    table_id: str,
    field_names: list[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        return list_records_with_fields(token, app_token, table_id, field_names), field_names
    except SyncError as exc:
        if "1254045" not in str(exc) and "FieldNameNotFound" not in str(exc):
            raise
        available = existing_fieldnames(token, app_token, table_id)
        filtered = [name for name in field_names if name in available]
        if not filtered:
            raise SyncError(f"飞书结果表没有可读取字段：{table_id}") from exc
        return list_records_with_fields(token, app_token, table_id, filtered), filtered


def fetch_report_from_feishu(config: dict[str, Any], token: str, key: str) -> dict[str, Any]:
    app_token = str(config.get("app_token") or "")
    table_id = str((config.get("table_ids") or {}).get(key) or "")
    if not app_token or not table_id:
        raise SyncError(f"飞书结果表未绑定：{SHEETS[key]['table_name']}")
    fieldnames = report_fieldnames(key)
    records, _ = list_records_with_available_fields(token, app_token, table_id, fieldnames)
    rows = [
        normalized_report_row(record.get("fields") or {}, fieldnames)
        for record in records
    ]
    return report_payload_from_rows(key, rows, fieldnames)


def fetch_reports_from_feishu() -> list[dict[str, Any]]:
    config = load_config()
    token = tenant_token(config)
    return [fetch_report_from_feishu(config, token, key) for key in SHEETS]


def list_remote_records(
    token: str,
    app_token: str,
    table_id: str,
    key_fields: tuple[str, ...],
    field_names: list[str],
) -> tuple[dict[str, str], dict[str, dict[str, Any]], list[str]]:
    keyed: dict[str, str] = {}
    fields_by_id: dict[str, dict[str, Any]] = {}
    blank_record_ids: list[str] = []
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
        for record in data.get("items") or []:
            fields = record.get("fields") or {}
            record_id = str(record.get("record_id") or record.get("id") or "")
            if record_id:
                fields_by_id[record_id] = fields
            record_key = "|".join(remote_text(fields.get(name)) for name in key_fields)
            if record_key.replace("|", "") and record_id:
                keyed[record_key] = record_id
            elif record_id:
                blank_record_ids.append(record_id)
        if not data.get("has_more"):
            return keyed, fields_by_id, blank_record_ids
        page_token = data.get("page_token")


def write_record(token: str, app_token: str, table_id: str, fields: dict[str, Any], record_id: str | None) -> str:
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


def delete_record(token: str, app_token: str, table_id: str, record_id: str) -> None:
    request_json(
        "DELETE",
        f"/bitable/v1/apps/{encoded(app_token)}/tables/{encoded(table_id)}/records/{encoded(record_id)}",
        token=token,
    )


def sync_table(token: str, config: dict[str, Any], state: dict[str, Any], key: str, dry_run: bool) -> tuple[int, int, int, dict[str, Any]]:
    headers, records = local_records(key)
    table_id = str(config["table_ids"][key])
    table_state = state["tables"].setdefault(table_id, {})
    remote_by_key, remote_fields_by_id, blank_record_ids = list_remote_records(
        token,
        config["app_token"],
        table_id,
        SHEETS[key]["key_fields"],
        headers,
    )
    used_record_ids: set[str] = set()
    created = 0
    updated = 0
    deleted = 0
    field_stats = empty_field_stats()
    for record in records:
        record_key = str(record.get("__key"))
        record_id = table_state.get(record_key) or remote_by_key.get(record_key)
        if record_id in used_record_ids:
            record_id = None
        reused_blank_record = False
        if record_id is None:
            record_id = next((candidate for candidate in blank_record_ids if candidate not in used_record_ids), None)
            reused_blank_record = record_id is not None
        was_existing = bool(record_id)
        fields, stats = prepare_incremental_fields(
            record,
            remote_fields_by_id.get(str(record_id or "")),
            is_existing=was_existing,
            preserve_identity_fields=not reused_blank_record,
        )
        merge_field_stats(field_stats, stats)
        if not fields:
            continue
        if not dry_run:
            record_id = write_record(token, config["app_token"], table_id, fields, record_id)
            table_state[record_key] = record_id
            save_state(state)
            time.sleep(0.08)
        if was_existing:
            updated += 1
        else:
            created += 1
        if record_id:
            used_record_ids.add(record_id)

    print(
        f"{SHEETS[key]['table_name']}：本地 {len(records)} 行，新增 {created} 行，更新 {updated} 行，删除 {deleted} 行，"
        f"新增字段 {field_stats['createdFields']} 个，更新字段 {field_stats['updatedFields']} 个，跳过字段 {field_stats['skippedFields']} 个。"
    )
    return created, updated, deleted, field_stats


def config_status() -> dict[str, Any]:
    status: dict[str, Any] = {
        "path": str(CONFIG_PATH),
        "statePath": str(STATE_PATH),
        "exists": CONFIG_PATH.exists(),
        "stateExists": STATE_PATH.exists(),
        "ready": False,
        "appTokenSet": False,
        "tableIdsSet": False,
        "appUrl": "",
        "feishuLinks": [],
        "message": "未找到飞书配置",
    }
    if not CONFIG_PATH.exists():
        return status
    try:
        with CONFIG_PATH.open("r", encoding="utf-8-sig") as file:
            config = json.load(file)
    except Exception as exc:  # noqa: BLE001 - reported to local UI.
        status["message"] = f"飞书配置读取失败：{exc}"
        return status
    config["app_secret"] = os.environ.get("FEISHU_APP_SECRET") or config.get("app_secret")
    missing = [name for name in ("app_id", "app_secret") if not config.get(name)]
    table_ids = config.get("table_ids") or {}
    status.update(
        {
            "ready": not missing,
            "appTokenSet": bool(config.get("app_token")),
            "tableIdsSet": all(bool(table_ids.get(key)) for key in SHEETS),
            "appUrl": str(config.get("app_url") or ""),
            "feishuLinks": feishu_links(config),
            "message": "配置可用" if not missing else "飞书配置缺少：" + ", ".join(missing),
        }
    )
    return status


def empty_sync_counts() -> dict[str, Any]:
    return {"created": 0, "updated": 0, "deleted": 0, **empty_field_stats()}


def sync_message(action: str, counts: dict[str, Any]) -> str:
    reasons = counts.get("skipReasons") or {}
    reason_text = "；跳过原因：" + "，".join(f"{reason} {count} 个" for reason, count in reasons.items()) if reasons else ""
    return (
        f"{action}：新增 {counts['created']} 行，更新 {counts['updated']} 行，删除 {counts['deleted']} 行；"
        f"新增字段 {counts['createdFields']} 个，更新字段 {counts['updatedFields']} 个，跳过字段 {counts['skippedFields']} 个"
        f"{reason_text}。"
    )


def sync_reports(reports: list[dict[str, Any]], *, dry_run: bool = False) -> dict[str, Any]:
    if not reports:
        raise SyncError("没有可同步的 30 日留存报表，请先刷新数据。")
    retention30_core.write_all_reports(reports)
    for key, meta in SHEETS.items():
        _, rows = local_records(key)
        if not rows:
            raise SyncError(f"本地 {meta['sheet_name']} 没有可同步数据。")
    if dry_run and not CONFIG_PATH.exists():
        return {
            "ok": True,
            "blocked": False,
            "dryRun": True,
            "message": "dry-run：本地数据检查通过，未找到飞书配置，未写入飞书。",
            **empty_sync_counts(),
        }

    config = load_config()
    if dry_run and not config.get("app_token"):
        return {
            "ok": True,
            "blocked": False,
            "dryRun": True,
            "message": "dry-run：本地数据检查通过，配置尚未绑定 app_token，未写入飞书。",
            **empty_sync_counts(),
        }

    token = tenant_token(config)
    setup_bitable(token, config)
    for key in SHEETS:
        headers, _ = local_records(key)
        ensure_schema(token, config, key, headers)
    state = load_state()
    counts = empty_sync_counts()
    for key in SHEETS:
        created, updated, deleted, field_stats = sync_table(token, config, state, key, dry_run)
        counts["created"] += created
        counts["updated"] += updated
        counts["deleted"] += deleted
        merge_field_stats(counts, field_stats)
    action = "预计同步" if dry_run else "同步完成"
    return {
        "ok": True,
        "blocked": False,
        "dryRun": dry_run,
        **counts,
        "appUrl": str(config.get("app_url") or ""),
        "message": sync_message(action, counts),
    }


def main() -> int:
    args = parse_args()
    for key, meta in SHEETS.items():
        _, rows = local_records(key)
        print(f"本地 {meta['sheet_name']}：{len(rows)} 行")
    if args.dry_run and not CONFIG_PATH.exists():
        print("dry-run：未找到 feishu_sync_config.json，已完成本地数据检查。")
        return 0
    config = load_config()
    if args.dry_run and not config.get("app_token"):
        print("dry-run：配置尚未绑定 app_token，将只完成本地数据检查。")
        return 0
    token = tenant_token(config)
    print("飞书鉴权成功。")
    setup_bitable(token, config)
    for key in SHEETS:
        headers, _ = local_records(key)
        ensure_schema(token, config, key, headers)
    if args.setup_only:
        return 0
    state = load_state()
    counts = empty_sync_counts()
    for key in SHEETS:
        created, updated, deleted, field_stats = sync_table(token, config, state, key, args.dry_run)
        counts["created"] += created
        counts["updated"] += updated
        counts["deleted"] += deleted
        merge_field_stats(counts, field_stats)
    action = "预计" if args.dry_run else "同步完成"
    print(sync_message(action, counts))
    if config.get("app_url"):
        print(f"飞书链接：{config['app_url']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"运行失败：{exc}")
        raise SystemExit(1)



