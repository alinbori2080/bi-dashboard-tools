from __future__ import annotations

import calendar
import csv
import re
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET


DATA_DIR = Path(__file__).resolve().parent / "data"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"

ENCODINGS = ("utf-8-sig", "utf-8", "gb18030")
DATE_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})")
CELL_REF_PATTERN = re.compile(r"([A-Z]+)(\d+)")
XLSX_NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


@dataclass(frozen=True)
class SourceFile:
    role: str
    path: Path

    def to_dict(self) -> dict[str, object]:
        stat = self.path.stat()
        return {
            "role": self.role,
            "name": self.path.name,
            "path": str(self.path),
            "size": stat.st_size,
            "updatedAt": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        }


@dataclass(frozen=True)
class DailyMetric:
    day: date
    value: int


@dataclass(frozen=True)
class DailyPrivateRecord:
    day: date
    new_friends: int
    active_accounts: int
    active_total_friends: int


@dataclass(frozen=True)
class ConversionPeriod:
    period_type: str
    period: str
    start_day: date
    end_day: date
    gdata_sum: int
    scrm_sum: int
    gdata_days: int
    scrm_days: int
    missing_gdata_days: tuple[date, ...]
    missing_scrm_days: tuple[date, ...]

    @property
    def ratio(self) -> float | None:
        if self.gdata_sum == 0:
            return None
        return self.scrm_sum / self.gdata_sum


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def detect_encoding(path: Path) -> str:
    for encoding in ENCODINGS:
        try:
            path.read_text(encoding=encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("unknown", b"", 0, 1, f"无法识别文件编码：{path}")


def find_latest_source(prefix: str, *, suffixes: set[str]) -> Path:
    ensure_dirs()
    candidates = [
        path
        for path in DATA_DIR.iterdir()
        if path.is_file()
        and path.name.startswith(prefix)
        and path.suffix.lower() in suffixes
        and not path.name.startswith("~$")
    ]
    if not candidates:
        raise FileNotFoundError(f"未找到以「{prefix}」开头的源文件。请放到：{DATA_DIR}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def parse_date(value: object) -> date | None:
    match = DATE_PATTERN.search(str(value).strip())
    if not match:
        return None
    return datetime.strptime(match.group(1), "%Y-%m-%d").date()


def parse_number(value: object, column: str, row_number: int) -> int:
    text = str(value).strip().replace(",", "").replace("%", "")
    if text in {"", "-", "None"}:
        return 0
    try:
        return int(float(text))
    except ValueError as exc:
        raise ValueError(f"第 {row_number} 行的「{column}」不是数字：{value!r}") from exc


def read_csv_rows(path: Path) -> list[list[str]]:
    encoding = detect_encoding(path)
    with path.open("r", encoding=encoding, newline="") as handle:
        return list(csv.reader(handle))


def read_xlsx_rows(path: Path) -> list[list[str]]:
    with zipfile.ZipFile(path) as workbook:
        shared_strings = read_shared_strings(workbook)
        xml = workbook.read(first_sheet_path(workbook))

    root = ET.fromstring(xml)
    rows_by_number: dict[int, dict[int, str]] = {}
    for row_node in root.findall(".//x:sheetData/x:row", XLSX_NS):
        row_number = int(row_node.attrib.get("r", len(rows_by_number) + 1))
        cells: dict[int, str] = {}
        for cell_node in row_node.findall("x:c", XLSX_NS):
            ref = cell_node.attrib.get("r", "")
            column_index = column_number(ref)
            if column_index is None:
                continue
            cells[column_index] = cell_value(cell_node, shared_strings)
        rows_by_number[row_number] = cells

    rows: list[list[str]] = []
    for row_number in sorted(rows_by_number):
        cells = rows_by_number[row_number]
        max_index = max(cells, default=0)
        rows.append([cells.get(index, "") for index in range(1, max_index + 1)])
    return rows


def read_shared_strings(workbook: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in workbook.namelist():
        return []
    root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
    values: list[str] = []
    for item in root.findall("x:si", XLSX_NS):
        text_parts = [node.text or "" for node in item.findall(".//x:t", XLSX_NS)]
        values.append("".join(text_parts))
    return values


def first_sheet_path(workbook: zipfile.ZipFile) -> str:
    for name in workbook.namelist():
        if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"):
            return name
    raise ValueError("XLSX 文件中没有工作表。")


def column_number(cell_ref: str) -> int | None:
    match = CELL_REF_PATTERN.match(cell_ref)
    if not match:
        return None
    number = 0
    for char in match.group(1):
        number = number * 26 + (ord(char) - ord("A") + 1)
    return number


def cell_value(cell_node: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell_node.attrib.get("t", "")
    if cell_type == "inlineStr":
        text_parts = [node.text or "" for node in cell_node.findall(".//x:t", XLSX_NS)]
        return "".join(text_parts).strip()

    value_node = cell_node.find("x:v", XLSX_NS)
    value = "" if value_node is None or value_node.text is None else value_node.text
    if cell_type == "s" and value:
        return shared_strings[int(float(value))].strip()
    return value.strip()


def read_tabular_rows(path: Path) -> list[list[str]]:
    if path.suffix.lower() == ".xlsx":
        return read_xlsx_rows(path)
    return read_csv_rows(path)


def find_column_index(header: list[str], column_name: str) -> int:
    for index, value in enumerate(header):
        if value == column_name:
            return index
    raise ValueError(f"未找到字段「{column_name}」。当前字段：{', '.join(header)}")


def find_date_column_index(rows: list[list[str]]) -> int:
    max_columns = max((len(row) for row in rows), default=0)
    best_index = -1
    best_count = 0
    for index in range(max_columns):
        count = sum(1 for row in rows[1:] if index < len(row) and parse_date(row[index]) is not None)
        if count > best_count:
            best_index = index
            best_count = count
    if best_index == -1:
        raise ValueError("未能自动识别日期列。")
    return best_index


def read_gdata_new_login(path: Path) -> list[DailyMetric]:
    rows = read_tabular_rows(path)
    if not rows:
        raise ValueError(f"GDATA 新登源文件为空：{path}")

    header = [cell.strip() for cell in rows[0]]
    try:
        date_index = header.index("日期")
        new_login_index = header.index("新登账号")
    except ValueError as exc:
        raise ValueError("GDATA 新登表必须包含「日期」和「新登账号」字段。") from exc

    metrics: list[DailyMetric] = []
    for row_number, row in enumerate(rows[1:], start=2):
        day = parse_date(row[date_index] if date_index < len(row) else "")
        if day is None:
            continue
        metrics.append(
            DailyMetric(
                day=day,
                value=parse_number(row[new_login_index] if new_login_index < len(row) else "", "新登账号", row_number),
            )
        )
    if not metrics:
        raise ValueError(f"GDATA 新登表没有可识别的日期明细：{path}")
    return sorted(metrics, key=lambda metric: metric.day)


def read_scrm_new_customer(path: Path) -> list[DailyMetric]:
    rows = read_tabular_rows(path)
    if not rows:
        raise ValueError(f"SCRM 源文件为空：{path}")

    header = [str(cell).strip() for cell in rows[0]]
    value_index = find_column_index(header, "新增客户数")
    date_index = find_date_column_index(rows)

    metrics: list[DailyMetric] = []
    for row_number, row in enumerate(rows[1:], start=2):
        day = parse_date(row[date_index] if date_index < len(row) else "")
        if day is None:
            continue
        metrics.append(
            DailyMetric(
                day=day,
                value=parse_number(row[value_index] if value_index < len(row) else "", "新增客户数", row_number),
            )
        )
    if not metrics:
        raise ValueError(f"SCRM 客户趋势表没有可识别的日期明细：{path}")
    return sorted(metrics, key=lambda metric: metric.day)


def metric_map(metrics: Iterable[DailyMetric]) -> dict[date, int]:
    mapped: dict[date, int] = {}
    for metric in metrics:
        mapped[metric.day] = mapped.get(metric.day, 0) + metric.value
    return mapped


def week_range(day: date) -> tuple[date, date]:
    start_day = day - timedelta(days=day.weekday())
    return start_day, start_day + timedelta(days=6)


def natural_month_range(day: date) -> tuple[date, date]:
    start_day = day.replace(day=1)
    end_day = day.replace(day=calendar.monthrange(day.year, day.month)[1])
    return start_day, end_day


def date_range(start_day: date, end_day: date) -> Iterable[date]:
    current = start_day
    while current <= end_day:
        yield current
        current += timedelta(days=1)


def week_label(start_day: date, end_day: date) -> str:
    return f"{start_day.month}.{start_day.day:02d}-{end_day.month}.{end_day.day:02d}"


def period_date_label(start_day: date, end_day: date) -> str:
    return week_label(start_day, end_day)


def month_label(month: int) -> str:
    return f"{month}月"


def percent_text(value: float | None) -> str:
    return "" if value is None else f"{value:.2%}"


def build_conversion_period(
    period_type: str,
    period: str,
    start_day: date,
    end_day: date,
    gdata: dict[date, int],
    scrm: dict[date, int],
) -> ConversionPeriod:
    period_days = tuple(date_range(start_day, end_day))
    common_days = tuple(day for day in period_days if day in gdata and day in scrm)
    return ConversionPeriod(
        period_type=period_type,
        period=period,
        start_day=start_day,
        end_day=end_day,
        gdata_sum=sum(gdata[day] for day in common_days),
        scrm_sum=sum(scrm[day] for day in common_days),
        gdata_days=sum(1 for day in period_days if day in gdata),
        scrm_days=sum(1 for day in period_days if day in scrm),
        missing_gdata_days=tuple(day for day in period_days if day not in gdata),
        missing_scrm_days=tuple(day for day in period_days if day not in scrm),
    )


def ordered_conversion_results(results: list[ConversionPeriod]) -> list[ConversionPeriod]:
    period_rank = {"日": 2, "周": 1, "月": 0}
    return sorted(
        results,
        key=lambda result: (
            period_rank.get(result.period_type, 0),
            result.end_day,
            result.start_day,
        ),
        reverse=True,
    )


def build_conversion_results(gdata_metrics: list[DailyMetric], scrm_metrics: list[DailyMetric]) -> list[ConversionPeriod]:
    gdata = metric_map(gdata_metrics)
    scrm = metric_map(scrm_metrics)
    common_dates = sorted(set(gdata) & set(scrm))
    if not common_dates:
        gdata_range = f"{min(gdata)} 至 {max(gdata)}" if gdata else "无可用日期"
        scrm_range = f"{min(scrm)} 至 {max(scrm)}" if scrm else "无可用日期"
        raise ValueError(
            "两张表没有共同日期，无法计算新用户转化率。"
            f" GDATA 日期范围：{gdata_range}；SCRM 日期范围：{scrm_range}。"
        )

    first_day = common_dates[0]
    last_day = common_dates[-1]
    results: list[ConversionPeriod] = []

    for day in common_dates:
        results.append(
            build_conversion_period(
                "日",
                day.isoformat(),
                day,
                day,
                gdata,
                scrm,
            )
        )

    current_week_start, _ = week_range(first_day)
    last_week_start, _ = week_range(last_day)
    while current_week_start <= last_week_start:
        current_week_end = current_week_start + timedelta(days=6)
        week_days = tuple(date_range(current_week_start, current_week_end))
        if all(day in gdata and day in scrm for day in week_days):
            results.append(
                build_conversion_period(
                    "周",
                    week_label(current_week_start, current_week_end),
                    current_week_start,
                    current_week_end,
                    gdata,
                    scrm,
                )
            )
        current_week_start += timedelta(days=7)

    monthly_dates: dict[tuple[int, int], list[date]] = defaultdict(list)
    for day in common_dates:
        monthly_dates[(day.year, day.month)].append(day)

    for year, month in sorted(monthly_dates):
        month_days = monthly_dates[(year, month)]
        month_start_day = month_days[0]
        month_end_day = month_days[-1]
        results.append(
            build_conversion_period(
                "月",
                period_date_label(month_start_day, month_end_day),
                month_start_day,
                month_end_day,
                gdata,
                scrm,
            )
        )

    return results


def conversion_row(result: ConversionPeriod) -> dict[str, str | int]:
    return {
        "周期类型": result.period_type,
        "统计周期": result.period,
        "开始日期": result.start_day.isoformat(),
        "结束日期": result.end_day.isoformat(),
        "新增客户数_SCRM": result.scrm_sum,
        "新登账号_GDATA": result.gdata_sum,
        "新用户转化率": percent_text(result.ratio),
    }


def build_conversion_report() -> dict[str, object]:
    gdata_path = find_latest_source("新登", suffixes={".csv", ".xlsx"})
    scrm_path = find_latest_source("企微分析_客户_趋势明细", suffixes={".csv", ".xlsx"})
    results = build_conversion_results(
        read_gdata_new_login(gdata_path),
        read_scrm_new_customer(scrm_path),
    )
    rows = [conversion_row(result) for result in ordered_conversion_results(results)]
    return report_payload(
        report_id="conversion",
        title="新用户转化率",
        formula="新增客户数_SCRM / 新登账号_GDATA",
        ratio_field="新用户转化率",
        numerator_field="新增客户数_SCRM",
        denominator_field="新登账号_GDATA",
        rows=rows,
        sources=[SourceFile("GDATA 新登", gdata_path), SourceFile("SCRM 新增客户", scrm_path)],
    )


def read_private_records(path: Path) -> list[DailyPrivateRecord]:
    encoding = detect_encoding(path)
    with path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"企微好友源数据没有表头：{path}")
        required = ("日期", "新加好友", "活跃账号", "活跃累计好友")
        missing = [column for column in required if column not in reader.fieldnames]
        if missing:
            raise ValueError("企微好友源数据缺少必要字段：" + "、".join(missing))

        records: list[DailyPrivateRecord] = []
        for row_number, row in enumerate(reader, start=2):
            day = parse_date(row["日期"])
            if day is None:
                continue
            records.append(
                DailyPrivateRecord(
                    day=day,
                    new_friends=parse_number(row["新加好友"], "新加好友", row_number),
                    active_accounts=parse_number(row["活跃账号"], "活跃账号", row_number),
                    active_total_friends=parse_number(row["活跃累计好友"], "活跃累计好友", row_number),
                )
            )
    if not records:
        raise ValueError(f"企微好友源数据没有可识别的日期明细：{path}")
    return sorted(records, key=lambda record: record.day)


def private_week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def private_ratio_row(
    records: list[DailyPrivateRecord],
    start_day: date,
    end_day: date,
    label: str,
    period_type: str,
    is_complete: bool,
) -> dict[str, str | int | float]:
    covered_days = {record.day for record in records}
    new_friends_sum = sum(record.new_friends for record in records)
    active_accounts_sum = sum(record.active_accounts for record in records)
    active_total_friends_sum = sum(record.active_total_friends for record in records)
    numerator = active_total_friends_sum - new_friends_sum
    denominator = active_accounts_sum - new_friends_sum
    ratio = numerator / denominator if denominator else None
    return {
        "周期类型": period_type,
        "统计周期": label,
        "开始日期": start_day.isoformat(),
        "结束日期": end_day.isoformat(),
        "新加好友": new_friends_sum,
        "活跃账号": active_accounts_sum,
        "活跃累计好友": active_total_friends_sum,
        "活跃用户关注私域占比": "" if ratio is None else f"{ratio:.2%}",
        "_完整周期": "是" if is_complete else "否",
        "_天数": len(covered_days),
    }


def build_private_daily_rows(records: list[DailyPrivateRecord]) -> list[dict[str, str | int | float]]:
    return [
        private_ratio_row([record], record.day, record.day, record.day.isoformat(), "日", True)
        for record in sorted(records, key=lambda item: item.day)
    ]


def build_private_weekly_rows(records: list[DailyPrivateRecord]) -> list[dict[str, str | int | float]]:
    grouped: dict[date, list[DailyPrivateRecord]] = defaultdict(list)
    for record in records:
        grouped[private_week_start(record.day)].append(record)

    rows: list[dict[str, str | int | float]] = []
    for start_day in sorted(grouped):
        week_records = sorted(grouped[start_day], key=lambda record: record.day)
        covered_days = {record.day for record in week_records}
        end_day = start_day + timedelta(days=6)
        is_complete = len(covered_days) == 7 and min(covered_days) == start_day and max(covered_days) == end_day
        if not is_complete:
            continue
        rows.append(private_ratio_row(week_records, start_day, end_day, week_label(start_day, end_day), "周", is_complete))
    return rows


def build_private_monthly_rows(records: list[DailyPrivateRecord]) -> list[dict[str, str | int | float]]:
    grouped: dict[tuple[int, int], list[DailyPrivateRecord]] = defaultdict(list)
    for record in records:
        grouped[(record.day.year, record.day.month)].append(record)

    rows: list[dict[str, str | int | float]] = []
    for year, month in sorted(grouped):
        month_records = sorted(grouped[(year, month)], key=lambda record: record.day)
        covered_days = {record.day for record in month_records}
        start_day = min(covered_days)
        end_day = max(covered_days)
        rows.append(private_ratio_row(month_records, start_day, end_day, period_date_label(start_day, end_day), "月", True))
    return rows


def build_private_report() -> dict[str, object]:
    source_path = find_latest_source("企微好友", suffixes={".csv"})
    records = read_private_records(source_path)
    daily_rows = sorted(build_private_daily_rows(records), key=lambda row: (row["结束日期"], row["开始日期"]), reverse=True)
    weekly_rows = sorted(build_private_weekly_rows(records), key=lambda row: (row["结束日期"], row["开始日期"]), reverse=True)
    monthly_rows = sorted(build_private_monthly_rows(records), key=lambda row: (row["结束日期"], row["开始日期"]), reverse=True)
    rows = []
    for row in [*daily_rows, *weekly_rows, *monthly_rows]:
        clean_row = row.copy()
        clean_row.pop("_完整周期", None)
        clean_row.pop("_天数", None)
        rows.append(clean_row)
    return report_payload(
        report_id="private",
        title="活跃用户关注私域占比",
        formula="(活跃累计好友 - 新加好友) / (活跃账号 - 新加好友)",
        ratio_field="活跃用户关注私域占比",
        numerator_field="活跃累计好友",
        denominator_field="活跃账号",
        rows=rows,
        sources=[SourceFile("企微好友", source_path)],
    )


def pct_to_number(value: object) -> float | None:
    text = str(value or "").strip().replace("%", "")
    if not text:
        return None
    try:
        return float(text) / 100
    except ValueError:
        return None


def report_summary(rows: list[dict[str, object]], ratio_field: str, numerator_field: str, denominator_field: str) -> dict[str, object]:
    weekly = [row for row in rows if row.get("周期类型") == "周"]
    monthly = [row for row in rows if row.get("周期类型") == "月"]
    latest = weekly[0] if weekly else (rows[0] if rows else {})
    latest_month = monthly[0] if monthly else {}
    ratios = [pct_to_number(row.get(ratio_field)) for row in rows]
    ratios = [value for value in ratios if value is not None]
    return {
        "rowCount": len(rows),
        "latestPeriod": latest.get("统计周期", ""),
        "latestRatio": latest.get(ratio_field, ""),
        "latestNumerator": latest.get(numerator_field, ""),
        "latestDenominator": latest.get(denominator_field, ""),
        "latestMonth": latest_month.get("统计周期", ""),
        "latestMonthRatio": latest_month.get(ratio_field, ""),
        "averageRatio": f"{(sum(ratios) / len(ratios)):.2%}" if ratios else "",
        "minRatio": f"{min(ratios):.2%}" if ratios else "",
        "maxRatio": f"{max(ratios):.2%}" if ratios else "",
    }


def report_payload(
    *,
    report_id: str,
    title: str,
    formula: str,
    ratio_field: str,
    numerator_field: str,
    denominator_field: str,
    rows: list[dict[str, object]],
    sources: list[SourceFile],
) -> dict[str, object]:
    return {
        "id": report_id,
        "title": title,
        "formula": formula,
        "ratioField": ratio_field,
        "numeratorField": numerator_field,
        "denominatorField": denominator_field,
        "summary": report_summary(rows, ratio_field, numerator_field, denominator_field),
        "rows": rows,
        "sources": [source.to_dict() for source in sources],
    }


def output_fieldnames(report: dict[str, object]) -> list[str]:
    rows = report.get("rows") or []
    if rows:
        return list(rows[0].keys())
    if report.get("id") == "conversion":
        return ["周期类型", "统计周期", "开始日期", "结束日期", "新增客户数_SCRM", "新登账号_GDATA", "新用户转化率"]
    return ["周期类型", "统计周期", "开始日期", "结束日期", "新加好友", "活跃账号", "活跃累计好友", "活跃用户关注私域占比"]


def write_report_csv(report: dict[str, object]) -> Path:
    ensure_dirs()
    output_path = OUTPUT_DIR / f"{report['title']}.csv"
    rows = report.get("rows") or []
    fieldnames = output_fieldnames(report)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return output_path


def build_all_reports() -> list[dict[str, object]]:
    return [build_conversion_report(), build_private_report()]


def write_all_reports(reports: list[dict[str, object]]) -> dict[str, str]:
    return {str(report["id"]): str(write_report_csv(report)) for report in reports}
