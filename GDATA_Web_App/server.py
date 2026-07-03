from __future__ import annotations

import json
import sys
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import feishu_sync
import gdata_core


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
FRONTEND_DIST_DIR = APP_DIR / "frontend" / "dist"
RUNTIME_STATE_PATH = APP_DIR / "runtime_state.json"
SERVER_STARTED_AT = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

class SingleInstanceHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = False


def json_default(value: object) -> str:
    if isinstance(value, Path):
        return str(value)
    return str(value)


def read_json_body(handler: SimpleHTTPRequestHandler) -> dict[str, object]:
    length = int(handler.headers.get("Content-Length") or "0")
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def write_runtime_state(payload: dict[str, object]) -> None:
    with RUNTIME_STATE_PATH.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, default=json_default)
        handle.write("\n")


def read_runtime_state() -> dict[str, object]:
    if not RUNTIME_STATE_PATH.exists():
        return {
            "generatedAt": "",
            "reports": [],
            "errors": [],
            "sync": {"ok": False, "message": "尚未刷新"},
        }
    with RUNTIME_STATE_PATH.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def source_inventory() -> list[dict[str, object]]:
    gdata_core.ensure_dirs()
    items = []
    for path in sorted(gdata_core.DATA_DIR.iterdir(), key=lambda item: item.name):
        if not path.is_file() or path.name.startswith("~$"):
            continue
        stat = path.stat()
        role = "未识别"
        if path.name.startswith("新登"):
            role = "GDATA 新登"
        elif path.name.startswith("企微分析_客户_趋势明细"):
            role = "SCRM 新增客户"
        elif path.name.startswith("企微好友"):
            role = "企微好友"
        items.append(
            {
                "role": role,
                "name": path.name,
                "path": str(path),
                "size": stat.st_size,
                "updatedAt": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    return items


def period_counts(rows: list[dict[str, object]]) -> dict[str, int]:
    counts = {"日": 0, "周": 0, "月": 0}
    for row in rows:
        period_type = str(row.get("周期类型") or "")
        if period_type in counts:
            counts[period_type] += 1
    return counts


def sync_preview(reports: list[dict[str, object]]) -> dict[str, object]:
    report_items = []
    total_rows = 0
    for report in reports:
        rows = list(report.get("rows") or [])
        counts = period_counts(rows)
        total_rows += len(rows)
        title = str(report.get("title") or report.get("id") or "报表")
        report_items.append(
            {
                "id": report.get("id", ""),
                "title": title,
                "totalRows": len(rows),
                "periodCounts": counts,
                "summary": f"{title}：共 {len(rows)} 行（日 {counts['日']} / 周 {counts['周']} / 月 {counts['月']}）",
            }
        )
    return {"totalRows": total_rows, "reports": report_items}


def status_payload() -> dict[str, object]:
    runtime = read_runtime_state()
    return {
        "appDir": str(APP_DIR),
        "dataDir": str(gdata_core.DATA_DIR),
        "outputDir": str(gdata_core.OUTPUT_DIR),
        "serverStartedAt": SERVER_STARTED_AT,
        "sourceMode": runtime.get("sourceMode", "feishu"),
        "sourceModes": ["feishu", "local"],
        "sources": source_inventory(),
        "config": feishu_sync.config_status(),
        "lastRefresh": runtime.get("generatedAt", ""),
        "lastSync": runtime.get("sync", {}),
    }


def calculate_reports() -> tuple[list[dict[str, object]], list[dict[str, str]]]:
    builders = [
        ("conversion", "新用户转化率", gdata_core.build_conversion_report),
        ("private", "活跃用户关注私域占比", gdata_core.build_private_report),
    ]
    reports: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    for report_id, title, builder in builders:
        try:
            reports.append(builder())
        except Exception as exc:  # noqa: BLE001 - reported to local UI.
            errors.append(
                {
                    "id": report_id,
                    "title": f"{title}计算失败",
                    "body": str(exc),
                }
            )
    return reports, errors


def refresh_payload(*, dry_run: bool, source_mode: str) -> dict[str, object]:
    if source_mode not in {"feishu", "local"}:
        source_mode = "feishu"
    if source_mode == "feishu":
        try:
            reports, errors = feishu_sync.fetch_reports_from_feishu(), []
        except Exception as exc:  # noqa: BLE001 - reported to local UI.
            reports, errors = [], [{"id": "conversion", "title": "飞书结果表读取失败", "body": str(exc)}]
    else:
        reports, errors = calculate_reports()
    sync_result: dict[str, object]
    output_files: dict[str, str] = {}

    if errors:
        sync_result = {
            "ok": False,
            "blocked": True,
            "message": "飞书结果表读取失败。" if source_mode == "feishu" else "存在报表计算失败，不能同步飞书。",
        }
    elif source_mode == "feishu":
        sync_result = {
            "ok": False,
            "blocked": True,
            "sourceMode": source_mode,
            "message": "当前数据已来自飞书结果表，无需同步。",
            "dryRun": dry_run,
        }
    else:
        output_files = gdata_core.write_all_reports(reports)
        sync_result = {
            "ok": False,
            "blocked": False,
            "ready": True,
            "message": "报表已刷新，等待确认同步飞书。",
            "dryRun": dry_run,
        }

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = status_payload()
    status["sourceMode"] = source_mode
    status["lastRefresh"] = generated_at
    status["lastSync"] = sync_result
    payload = {
        "generatedAt": generated_at,
        "sourceMode": source_mode,
        "reports": reports,
        "errors": errors,
        "outputFiles": output_files,
        "syncPreview": sync_preview(reports),
        "sync": sync_result,
        "status": status,
    }
    write_runtime_state(payload)
    return payload


def feishu_reports_payload() -> dict[str, object]:
    try:
        reports, errors = feishu_sync.fetch_reports_from_feishu(), []
    except Exception as exc:  # noqa: BLE001 - reported to local UI.
        reports, errors = [], [{"id": "conversion", "title": "飞书结果表读取失败", "body": str(exc)}]
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sync_result = {
        "ok": False,
        "blocked": True,
        "sourceMode": "feishu",
        "message": "当前数据已来自飞书结果表，无需同步。",
    }
    status = status_payload()
    status["sourceMode"] = "feishu"
    status["lastRefresh"] = generated_at
    status["lastSync"] = sync_result
    return {
        "generatedAt": generated_at,
        "sourceMode": "feishu",
        "reports": reports,
        "errors": errors,
        "outputFiles": {},
        "syncPreview": sync_preview(reports),
        "sync": sync_result,
        "status": status,
    }


def sync_payload(*, dry_run: bool) -> dict[str, object]:
    runtime = read_runtime_state()
    reports = runtime.get("reports") or []
    errors = runtime.get("errors") or []
    if runtime.get("sourceMode") == "feishu":
        runtime["sync"] = {
            "ok": False,
            "blocked": True,
            "sourceMode": "feishu",
            "message": "当前数据已来自飞书结果表，无需同步。",
            "dryRun": dry_run,
        }
        write_runtime_state(runtime)
        return runtime
    if errors:
        runtime["sync"] = {
            "ok": False,
            "blocked": True,
            "message": "存在报表计算失败，不能同步飞书。",
            "dryRun": dry_run,
        }
        write_runtime_state(runtime)
        return runtime
    if len(reports) < 2:
        runtime["sync"] = {
            "ok": False,
            "blocked": True,
            "message": "没有完整报表结果，请先刷新数据。",
            "dryRun": dry_run,
        }
        write_runtime_state(runtime)
        return runtime
    try:
        runtime["sync"] = feishu_sync.sync_reports(reports, dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001 - reported to local UI.
        runtime["sync"] = {
            "ok": False,
            "blocked": False,
            "message": str(exc),
            "dryRun": dry_run,
        }
    write_runtime_state(runtime)
    return runtime


def csv_response(report: dict[str, object]) -> bytes:
    import csv
    import io

    rows = report.get("rows") or []
    fieldnames = gdata_core.output_fieldnames(report)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return ("\ufeff" + output.getvalue()).encode("utf-8")


class AppHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: object, **kwargs: object) -> None:
        static_dir = FRONTEND_DIST_DIR if (FRONTEND_DIST_DIR / "index.html").exists() else STATIC_DIR
        super().__init__(*args, directory=str(static_dir), **kwargs)

    def do_GET(self) -> None:  # noqa: N802 - stdlib API.
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            self.write_json(status_payload())
            return
        if parsed.path == "/api/reports":
            self.write_json(read_runtime_state())
            return
        if parsed.path == "/api/export":
            self.write_export(parse_qs(parsed.query).get("report", [""])[0])
            return
        if parsed.path == "/api/feishu-link":
            self.redirect_feishu_link(parse_qs(parsed.query).get("target", [""])[0])
            return
        if parsed.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802 - stdlib API.
        parsed = urlparse(self.path)
        if parsed.path not in {"/api/refresh", "/api/sync"}:
            self.write_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        query = parse_qs(parsed.query)
        body = read_json_body(self)
        dry_run = str(query.get("dryRun", [""])[0]).lower() in {"1", "true", "yes"} or bool(body.get("dryRun"))
        source_mode = str(body.get("sourceMode") or "feishu")
        if parsed.path == "/api/refresh":
            self.write_json(refresh_payload(dry_run=dry_run, source_mode=source_mode))
        else:
            self.write_json(sync_payload(dry_run=dry_run))

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def write_json(self, payload: dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2, default=json_default).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def redirect_feishu_link(self, target: str) -> None:
        try:
            url = feishu_sync.feishu_link_url(target)
        except Exception:  # noqa: BLE001 - do not expose config details.
            url = ""
        if not url:
            self.write_json({"error": "未配置飞书链接"}, HTTPStatus.NOT_FOUND)
            return
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", url)
        self.end_headers()

    def write_export(self, report_id: str) -> None:
        runtime = read_runtime_state()
        report = next((item for item in runtime.get("reports", []) if item.get("id") == report_id), None)
        if report is None:
            self.write_json({"error": "没有可导出的报表，请先刷新数据。"}, HTTPStatus.NOT_FOUND)
            return
        body = csv_response(report)
        filename = quote(f"{report.get('title', 'report')}.csv")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{filename}")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        sys.stderr.write("[%s] %s\n" % (datetime.now().strftime("%H:%M:%S"), format % args))


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    gdata_core.ensure_dirs()
    server = SingleInstanceHTTPServer(("127.0.0.1", port), AppHandler)
    print(f"GDATA 网页 App 已启动：http://127.0.0.1:{port}")
    print(f"源数据目录：{gdata_core.DATA_DIR}")
    print(f"飞书配置：{feishu_sync.CONFIG_PATH}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
