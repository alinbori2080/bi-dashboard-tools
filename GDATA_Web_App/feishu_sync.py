from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


APP_DIR = Path(__file__).resolve().parent
CONFIG_DIR = APP_DIR / "config"
CONFIG_PATH = CONFIG_DIR / "feishu_sync_config.json"
STATE_PATH = CONFIG_DIR / "feishu_sync_state.json"
API_ROOT = "https://open.feishu.cn/open-apis"
CHINA_TZ = timezone(timedelta(hours=8))


class SyncError(RuntimeError):
    pass


@dataclass(frozen=True)
class TableConfig:
    report_id: str
    name: str
    table_id: str
    integer_fields: frozenset[str]
    numeric_fields: frozenset[str]
    percentage_fields: frozenset[str]
    date_fields: frozenset[str]


def config_status() -> dict[str, object]:
    exists = CONFIG_PATH.exists()
    state_exists = STATE_PATH.exists()
    keys: list[str] = []
    missing: list[str] = []
    if exists:
        try:
            config = load_config(redact_secret=True)
            keys = sorted(config.keys())
            missing = [key for key in required_config_keys() if not config.get(key)]
            links = feishu_links(config)
        except Exception as exc:  # noqa: BLE001 - surfaced to local UI.
            return {
                "configured": False,
                "configPath": str(CONFIG_PATH),
                "statePath": str(STATE_PATH),
                "error": str(exc),
                "feishuLinks": [],
            }
    else:
        links = []
    return {
        "configured": exists and not missing,
        "configPath": str(CONFIG_PATH),
        "statePath": str(STATE_PATH),
        "stateExists": state_exists,
        "keys": keys,
        "missing": missing,
        "feishuLinks": links,
    }


def required_config_keys() -> tuple[str, ...]:
    return (
        "app_id",
        "app_secret",
        "app_token",
        "private_domain_table_id",
        "conversion_table_id",
    )


def load_config(*, redact_secret: bool = False) -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise SyncError(f"飞书配置文件不存在：{CONFIG_PATH}")

    with CONFIG_PATH.open("r", encoding="utf-8-sig") as handle:
        config = json.load(handle)

    secret = os.environ.get("FEISHU_APP_SECRET") or config.get("app_secret")
    required = {
        "app_id": config.get("app_id"),
        "app_secret": secret,
        "app_token": config.get("app_token"),
        "private_domain_table_id": config.get("private_domain_table_id"),
        "conversion_table_id": config.get("conversion_table_id"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise SyncError("飞书配置缺少字段：" + "、".join(missing))

    config["app_secret"] = "***" if redact_secret else secret
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
    if base_url:
        return [{"target": "app", "label": "飞书结果表", "url": base_url}]
    return [
        {
            "target": "conversion",
            "label": "飞书结果表（新用户转化率）",
            "url": valid_url(config.get("conversion_table_url")) or base_url,
        },
        {
            "target": "private",
            "label": "飞书结果表（活跃用户关注私域占比）",
            "url": valid_url(config.get("private_domain_table_url")) or base_url,
        },
    ]


def feishu_link_url(target: str) -> str:
    config = load_config(redact_secret=True)
    links = configured_feishu_links(config)
    for item in links:
        if item["target"] == target:
            return item["url"]
    if len(links) == 1:
        return links[0]["url"]
    return ""


def load_sync_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"tables": {}}
    with STATE_PATH.open("r", encoding="utf-8-sig") as handle:
        state = json.load(handle)
    if not isinstance(state.get("tables"), dict):
        raise SyncError("飞书同步状态文件格式无效。")
    return state


def save_sync_state(state: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    temporary_path = STATE_PATH.with_suffix(".tmp")
    with temporary_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temporary_path.replace(STATE_PATH)


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
    url = API_ROOT + path
    data = None
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")

    attempts = 3 if retry else 1
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, data=data, headers=headers, method=method)
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

        message = payload.get("msg", "Unknown Feishu API error")
        last_error = SyncError(f"飞书 API 错误 {code}: {message}")
        if code not in {1254290, 1254291, 1254607, 1255040} or attempt + 1 == attempts:
            raise last_error
        time.sleep(1.5 * (attempt + 1))

    raise last_error or SyncError("飞书请求失败。")


def get_tenant_access_token(config: dict[str, Any]) -> str:
    payload = request_json(
        "POST",
        "/auth/v3/tenant_access_token/internal",
        body={"app_id": config["app_id"], "app_secret": config["app_secret"]},
    )
    token = payload.get("tenant_access_token")
    if not token:
        raise SyncError("飞书未返回 tenant_access_token。")
    return str(token)


def table_configs(config: dict[str, Any]) -> dict[str, TableConfig]:
    return {
        "private": TableConfig(
            report_id="private",
            name="活跃用户关注私域占比",
            table_id=config["private_domain_table_id"],
            integer_fields=frozenset({"新加好友", "活跃账号", "活跃累计好友"}),
            numeric_fields=frozenset(),
            percentage_fields=frozenset({"活跃用户关注私域占比"}),
            date_fields=frozenset({"开始日期", "结束日期"}),
        ),
        "conversion": TableConfig(
            report_id="conversion",
            name="新用户转化率",
            table_id=config["conversion_table_id"],
            integer_fields=frozenset({"新增客户数_SCRM", "新登账号_GDATA"}),
            numeric_fields=frozenset(),
            percentage_fields=frozenset({"新用户转化率"}),
            date_fields=frozenset({"开始日期", "结束日期"}),
        ),
    }


def date_to_milliseconds(value: str) -> int:
    parsed = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=CHINA_TZ)
    return int(parsed.timestamp() * 1000)


def build_sync_id(period_type: Any, start_day: Any, end_day: Any) -> str:
    period_type_text = str(period_type or "").strip()
    start_text = str(start_day or "").strip()
    end_text = str(end_day or "").strip()
    if period_type_text == "月" and len(start_text) >= 7:
        return f"{period_type_text}|{start_text[:7]}"
    return "|".join([period_type_text, start_text, end_text])


def convert_record(row: dict[str, Any], table: TableConfig) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for name, raw_value in row.items():
        value = str(raw_value if raw_value is not None else "").strip()
        if not value:
            continue
        if name in table.date_fields:
            fields[name] = date_to_milliseconds(value)
        elif name in table.integer_fields:
            fields[name] = int(float(value))
        elif name in table.numeric_fields:
            fields[name] = float(value)
        elif name in table.percentage_fields:
            fields[name] = float(value.rstrip("%")) / 100
        else:
            fields[name] = value

    fields["__sync_id"] = build_sync_id(row["周期类型"], row["开始日期"], row["结束日期"])
    return fields


def list_remote_records(token: str, app_token: str, table_id: str) -> list[dict[str, Any]]:
    return list_remote_records_with_fields(token, app_token, table_id, ["周期类型", "统计周期", "开始日期", "结束日期"])


def list_remote_records_with_fields(
    token: str,
    app_token: str,
    table_id: str,
    field_names: list[str],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    page_token: str | None = None
    encoded_app = urllib.parse.quote(app_token, safe="")
    encoded_table = urllib.parse.quote(table_id, safe="")

    while True:
        query = {"page_size": "500"}
        if page_token:
            query["page_token"] = page_token
        path = (
            f"/bitable/v1/apps/{encoded_app}/tables/{encoded_table}/records/search?"
            + urllib.parse.urlencode(query)
        )
        payload = request_json("POST", path, token=token, body={"field_names": field_names})
        data = payload.get("data") or {}
        records.extend(data.get("items") or [])
        if not data.get("has_more"):
            break
        page_token = data.get("page_token")
        if not page_token:
            raise SyncError("飞书分页缺少 page_token。")
    return records


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
    if not text:
        return None
    return float(text)


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


def remote_sync_id(fields: dict[str, Any]) -> str:
    return build_sync_id(
        remote_text(fields.get("周期类型")),
        remote_date(fields.get("开始日期")),
        remote_date(fields.get("结束日期")),
    )


def sort_report_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    period_rank = {"日": 2, "周": 1, "月": 0}

    def key(row: dict[str, Any]) -> tuple[int, str, str]:
        return (
            period_rank.get(str(row.get("周期类型") or ""), 0),
            str(row.get("结束日期") or ""),
            str(row.get("开始日期") or ""),
        )

    return sorted(rows, key=key, reverse=True)


def table_source(config: dict[str, Any], table_id: str, name: str, record_count: int) -> dict[str, Any]:
    return {
        "role": "飞书结果表",
        "name": name,
        "path": f"{config.get('app_token', '')}/{table_id}",
        "size": record_count,
        "updatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def fetch_report_from_feishu(config: dict[str, Any], token: str, report_id: str) -> dict[str, Any]:
    import gdata_core

    tables = table_configs(config)
    table = tables[report_id]
    fields = [
        "周期类型",
        "统计周期",
        "开始日期",
        "结束日期",
        *sorted(table.integer_fields),
        *sorted(table.percentage_fields),
    ]
    records = list_remote_records_with_fields(token, config["app_token"], table.table_id, fields)
    rows: list[dict[str, Any]] = []
    for record in records:
        source = record.get("fields") or {}
        row: dict[str, Any] = {
            "周期类型": remote_text(source.get("周期类型")),
            "统计周期": remote_text(source.get("统计周期")),
            "开始日期": remote_date(source.get("开始日期")),
            "结束日期": remote_date(source.get("结束日期")),
        }
        for name in table.integer_fields:
            row[name] = remote_int(source.get(name))
        for name in table.percentage_fields:
            row[name] = remote_percent(source.get(name))
        if row["周期类型"] and row["统计周期"]:
            rows.append(row)
    rows = sort_report_rows(rows)
    if not rows:
        raise SyncError(f"飞书结果表没有可展示的数据：{table.name}")

    if report_id == "conversion":
        payload = gdata_core.report_payload(
            report_id="conversion",
            title="新用户转化率",
            formula="新增客户数_SCRM / 新登账号_GDATA",
            ratio_field="新用户转化率",
            numerator_field="新增客户数_SCRM",
            denominator_field="新登账号_GDATA",
            rows=rows,
            sources=[],
        )
    else:
        payload = gdata_core.report_payload(
            report_id="private",
            title="活跃用户关注私域占比",
            formula="(活跃累计好友 - 新加好友) / (活跃账号 - 新加好友)",
            ratio_field="活跃用户关注私域占比",
            numerator_field="活跃累计好友",
            denominator_field="活跃账号",
            rows=rows,
            sources=[],
        )
    payload["sources"] = [table_source(config, table.table_id, table.name, len(rows))]
    payload["sourceMode"] = "feishu"
    return payload


def fetch_reports_from_feishu() -> list[dict[str, Any]]:
    config = load_config()
    token = get_tenant_access_token(config)
    return [
        fetch_report_from_feishu(config, token, "conversion"),
        fetch_report_from_feishu(config, token, "private"),
    ]


def write_record(
    token: str,
    app_token: str,
    table_id: str,
    fields: dict[str, Any],
    record_id: str | None = None,
) -> str:
    fields = {name: value for name, value in fields.items() if value is not None}
    encoded_app = urllib.parse.quote(app_token, safe="")
    encoded_table = urllib.parse.quote(table_id, safe="")
    base_path = f"/bitable/v1/apps/{encoded_app}/tables/{encoded_table}/records"
    if record_id:
        encoded_record = urllib.parse.quote(record_id, safe="")
        request_json("PUT", f"{base_path}/{encoded_record}", token=token, body={"fields": fields})
        return record_id

    payload = request_json("POST", base_path, token=token, body={"fields": fields}, retry=False)
    record = ((payload.get("data") or {}).get("record") or {})
    new_record_id = record.get("record_id") or record.get("id")
    if not new_record_id:
        raise SyncError("飞书创建记录成功但没有返回 record_id。")
    return str(new_record_id)


def sync_one_report(
    *,
    token: str,
    app_token: str,
    table: TableConfig,
    rows: list[dict[str, Any]],
    table_state: dict[str, str],
    state: dict[str, Any],
    dry_run: bool,
) -> dict[str, object]:
    local_records = [convert_record(row, table) for row in rows]
    local_records.sort(key=lambda fields: fields["__sync_id"] in table_state)
    remote_records = list_remote_records(token, app_token, table.table_id)

    by_sync_id: dict[str, list[str]] = {}
    by_period: dict[str, list[str]] = {}
    blank_record_ids: list[str] = []
    for record in remote_records:
        record_id = str(record.get("record_id") or record.get("id") or "")
        if not record_id:
            continue
        fields = record.get("fields") or {}
        sync_id = remote_sync_id(fields)
        if sync_id.strip("|"):
            by_sync_id.setdefault(sync_id, []).append(record_id)
        period = str(fields.get("统计周期") or "").strip()
        if period:
            period_type = remote_text(fields.get("周期类型"))
            by_period.setdefault(f"{period_type}|{period}", []).append(record_id)
        else:
            blank_record_ids.append(record_id)

    created = 0
    updated = 0
    used_record_ids: set[str] = set()
    for source_fields in local_records:
        fields = source_fields.copy()
        sync_id = str(fields.pop("__sync_id"))
        period_type = str(fields["周期类型"])
        period = str(fields["统计周期"])
        record_id = table_state.get(sync_id)
        if record_id in used_record_ids:
            record_id = None

        if record_id is None:
            candidates = by_sync_id.get(sync_id) or []
            record_id = next((candidate for candidate in candidates if candidate not in used_record_ids), None)
        if record_id is None:
            candidates = by_period.get(f"{period_type}|{period}") or []
            record_id = next((candidate for candidate in candidates if candidate not in used_record_ids), None)
        if record_id is None:
            record_id = next((candidate for candidate in blank_record_ids if candidate not in used_record_ids), None)

        was_existing = bool(record_id)
        if not dry_run:
            try:
                record_id = write_record(token, app_token, table.table_id, fields, record_id)
            except SyncError as exc:
                if record_id and ("1254043" in str(exc) or "1254006" in str(exc)):
                    record_id = write_record(token, app_token, table.table_id, fields)
                    was_existing = False
                else:
                    raise
            table_state[sync_id] = record_id
            save_sync_state(state)
            time.sleep(0.08)

        if was_existing:
            updated += 1
        else:
            created += 1
        if record_id:
            used_record_ids.add(record_id)

    return {
        "reportId": table.report_id,
        "name": table.name,
        "created": created,
        "updated": updated,
        "dryRun": dry_run,
    }


def sync_reports(reports: list[dict[str, Any]], *, dry_run: bool = False) -> dict[str, object]:
    config = load_config()
    state = load_sync_state()
    token = get_tenant_access_token(config)
    tables = table_configs(config)
    reports_by_id = {str(report["id"]): report for report in reports}
    results = []

    for report_id in ("private", "conversion"):
        report = reports_by_id.get(report_id)
        if report is None:
            raise SyncError(f"缺少可同步报表：{report_id}")
        table = tables[report_id]
        table_state = state["tables"].setdefault(table.table_id, {})
        rows = report.get("rows") or []
        results.append(
            sync_one_report(
                token=token,
                app_token=config["app_token"],
                table=table,
                rows=rows,
                table_state=table_state,
                state=state,
                dry_run=dry_run,
            )
        )

    if not dry_run:
        save_sync_state(state)
    return {
        "ok": True,
        "dryRun": dry_run,
        "syncedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tables": results,
    }
