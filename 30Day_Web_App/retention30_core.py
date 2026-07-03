# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import calendar
import csv
import re
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
DEFAULT_OUTPUT = OUTPUT_DIR / "30日留存结果.xlsx"
PRIVATE_PREFIX = "名将杀 私域需求"
GDATA_PREFIX = "新登"
ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "gbk")
RETENTION_DAYS = (2, 3, 4, 5, 6, 7, 14, 21, 30)
MARKET_DAYS = (2, 3, 7)
DAY_LABELS = {
    2: "次留",
    3: "3日留",
    4: "4日留",
    5: "5日留",
    6: "6日留",
    7: "7日留",
    14: "14日留",
    21: "21日留",
    30: "30日留",
}
MARKET_LABELS = {
    2: "大盘次留",
    3: "大盘3日留",
    7: "大盘7日留",
}
MARKET_SOURCE_COLUMNS = {
    2: "次留率",
    3: "3留率",
    7: "7留率",
}
DATE_PATTERN = re.compile(r"(20\d{2})[-/]?(\d{2})[-/]?(\d{2})")
YEAR_IN_NAME = re.compile(r"(20\d{6})")
XLSX_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
XLSX_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


@dataclass
class DailyRetention:
    day: date
    users: int
    login_counts: dict[int, int]
    mature: dict[int, bool]


@dataclass(frozen=True)
class MarketDaily:
    new_accounts: int | None
    rates: dict[int, float]


def excel_column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def excel_column_index(reference: str) -> int:
    letters = re.match(r"[A-Z]+", reference.upper())
    if not letters:
        return 0
    index = 0
    for char in letters.group(0):
        index = index * 26 + ord(char) - 64
    return index - 1


def excel_serial_date(value: object) -> date | None:
    try:
        serial = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if serial < 20000 or serial > 70000:
        return None
    return date(1899, 12, 30) + timedelta(days=int(serial))


def parse_xlsx_number(text: str) -> object:
    try:
        number = float(text)
    except ValueError:
        return text
    if number.is_integer():
        return int(number)
    return number


def xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        content = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(content)
    values: list[str] = []
    for item in root.findall(f"{{{XLSX_NS}}}si"):
        values.append("".join(text.text or "" for text in item.findall(f".//{{{XLSX_NS}}}t")))
    return values


def xlsx_sheet_paths(archive: zipfile.ZipFile) -> dict[str, str]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets: dict[str, str] = {}
    for rel in rels.findall(f"{{{PACKAGE_REL_NS}}}Relationship"):
        target = rel.attrib.get("Target", "")
        if target.startswith("/"):
            path = target.lstrip("/")
        elif target.startswith("xl/"):
            path = target
        else:
            path = "xl/" + target
        targets[rel.attrib.get("Id", "")] = path

    paths: dict[str, str] = {}
    for sheet in workbook.findall(f".//{{{XLSX_NS}}}sheet"):
        sheet_name = sheet.attrib.get("name", "")
        rel_id = sheet.attrib.get(f"{{{XLSX_REL_NS}}}id", "")
        if sheet_name and rel_id in targets:
            paths[sheet_name] = targets[rel_id]
    return paths


def xlsx_cell_value(cell: ET.Element, shared_strings: list[str]) -> object:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(text.text or "" for text in cell.findall(f".//{{{XLSX_NS}}}t"))
    value = cell.find(f"{{{XLSX_NS}}}v")
    if value is None or value.text is None:
        return ""
    text = value.text.strip()
    if cell_type == "s":
        try:
            return shared_strings[int(text)]
        except (ValueError, IndexError):
            return ""
    if cell_type in {"str", "b"}:
        return text
    return parse_xlsx_number(text)


def read_xlsx_rows(path: Path, sheet_name: str | None = None) -> list[list[object]]:
    with zipfile.ZipFile(path) as archive:
        shared_strings = xlsx_shared_strings(archive)
        sheet_paths = xlsx_sheet_paths(archive)
        if sheet_name is None:
            sheet_path = next(iter(sheet_paths.values()), None)
        else:
            sheet_path = sheet_paths.get(sheet_name)
        if not sheet_path:
            raise ValueError(f"XLSX 缺少 sheet：{sheet_name or '首个工作表'}")
        root = ET.fromstring(archive.read(sheet_path))

    rows: list[list[object]] = []
    for row in root.findall(f".//{{{XLSX_NS}}}sheetData/{{{XLSX_NS}}}row"):
        values: dict[int, object] = {}
        for cell in row.findall(f"{{{XLSX_NS}}}c"):
            reference = cell.attrib.get("r", "")
            column_index = excel_column_index(reference)
            values[column_index] = xlsx_cell_value(cell, shared_strings)
        max_column = max(values.keys(), default=-1)
        rows.append([values.get(index, "") for index in range(max_column + 1)])
    return rows


def xlsx_cell_xml(row_index: int, column_index: int, value: object) -> str:
    reference = f"{excel_column_name(column_index)}{row_index}"
    text = "" if value is None else str(value)
    return f'<c r="{reference}" t="inlineStr"><is><t xml:space="preserve">{escape(text)}</t></is></c>'


def xml_attr(value: str) -> str:
    return escape(value, {'"': "&quot;"})


def xlsx_sheet_xml(fieldnames: list[str], rows: list[dict[str, str | int]]) -> str:
    data_rows = [fieldnames, *[[row.get(field, "") for field in fieldnames] for row in rows]]
    xml_rows = []
    for row_index, values in enumerate(data_rows, start=1):
        cells = "".join(xlsx_cell_xml(row_index, column_index, value) for column_index, value in enumerate(values, start=1))
        xml_rows.append(f'<row r="{row_index}">{cells}</row>')
    last_cell = f"{excel_column_name(max(len(fieldnames), 1))}{max(len(data_rows), 1)}"
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<worksheet xmlns="{XLSX_NS}" xmlns:r="{XLSX_REL_NS}">'
        f'<dimension ref="A1:{last_cell}"/>'
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" '
        'activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        f'<sheetData>{"".join(xml_rows)}</sheetData>'
        f'<autoFilter ref="A1:{last_cell}"/>'
        '</worksheet>'
    )


def write_xlsx_workbook(output: Path, sheets: list[tuple[str, list[str], list[dict[str, str | int]]]]) -> None:
    sheet_overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, len(sheets) + 1)
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        f"{sheet_overrides}</Types>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{PACKAGE_REL_NS}">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        '</Relationships>'
    )
    workbook_sheets = "".join(
        f'<sheet name="{xml_attr(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, (name, _, _) in enumerate(sheets, start=1)
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<workbook xmlns="{XLSX_NS}" xmlns:r="{XLSX_REL_NS}"><sheets>{workbook_sheets}</sheets></workbook>'
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{PACKAGE_REL_NS}">'
        + "".join(
            f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{index}.xml"/>'
            for index in range(1, len(sheets) + 1)
        )
        + '</Relationships>'
    )
    core_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:creator>30Day_Web_App</dc:creator></cp:coreProperties>'
    )
    app_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
        '<Application>30Day_Web_App</Application></Properties>'
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("docProps/core.xml", core_xml)
        archive.writestr("docProps/app.xml", app_xml)
        for index, (_, fieldnames, rows) in enumerate(sheets, start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", xlsx_sheet_xml(fieldnames, rows))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="计算名将杀私域用户 2-30 日留存，并生成本地结果表。")
    parser.add_argument("--input", type=Path, help="私域需求源 XLSX。默认读取目录中最新的「名将杀 私域需求*.xlsx」。")
    parser.add_argument("--gdata", type=Path, help="GDATA 新登 CSV/XLSX。默认读取目录中最新的「新登*」文件。")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help=f"输出 XLSX。默认：{DEFAULT_OUTPUT}")
    parser.add_argument("--as-of", type=str, help="手动指定统计截止日期，格式 YYYY-MM-DD。默认从源数据中最晚的有效登录记录自动推断。")
    return parser.parse_args()


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def find_latest_source(prefix: str, suffixes: set[str]) -> Path:
    ensure_dirs()
    candidates = [
        item
        for item in DATA_DIR.iterdir()
        if item.is_file()
        and item.name.startswith(prefix)
        and item.suffix.lower() in suffixes
        and not item.name.startswith("~$")
    ]
    if not candidates:
        raise FileNotFoundError(f"未找到以「{prefix}」开头的源文件，请放到：{DATA_DIR}")
    return max(candidates, key=lambda item: item.stat().st_mtime)


def parse_requested_cutoff(requested: str | None) -> date | None:
    if requested:
        return datetime.strptime(requested, "%Y-%m-%d").date()
    return None


def parse_reg_date(value: object, row_number: int) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if (serial_day := excel_serial_date(value)) is not None:
        return serial_day
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    match = DATE_PATTERN.search(text)
    if not match:
        raise ValueError(f"第 {row_number} 行 reg_date 不是有效日期：{value!r}")
    return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))


def parse_login(value: object) -> bool:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text == "1"


def read_private_source(path: Path, requested_cutoff: date | None) -> tuple[list[DailyRetention], date]:
    source_rows = read_xlsx_rows(path)
    try:
        header = [str(cell).strip() if cell is not None else "" for cell in source_rows[0]]
    except StopIteration as exc:
        raise ValueError(f"源文件为空：{path}") from exc
    except IndexError as exc:
        raise ValueError(f"源文件为空：{path}") from exc

    required = ["account", "reg_date", *(f"day{day}" for day in RETENTION_DAYS)]
    missing = [name for name in required if name not in header]
    if missing:
        raise ValueError("私域源文件缺少字段：" + ", ".join(missing))

    account_index = header.index("account")
    reg_date_index = header.index("reg_date")
    day_indexes = {day: header.index(f"day{day}") for day in RETENTION_DAYS}
    parsed_rows: list[tuple[date, dict[int, bool]]] = []
    inferred_cutoff: date | None = None

    for row_number, row in enumerate(source_rows[1:], start=2):
        account = row[account_index] if account_index < len(row) else None
        if account is None or str(account).strip() == "":
            continue
        reg_day = parse_reg_date(row[reg_date_index] if reg_date_index < len(row) else "", row_number)
        logins = {
            day: parse_login(row[index] if index < len(row) else "")
            for day, index in day_indexes.items()
        }
        parsed_rows.append((reg_day, logins))
        for day, logged_in in logins.items():
            if logged_in:
                login_day = reg_day + timedelta(days=day - 1)
                if inferred_cutoff is None or login_day > inferred_cutoff:
                    inferred_cutoff = login_day

    if not parsed_rows:
        raise ValueError(f"源文件没有可统计账号：{path}")
    if requested_cutoff is None and inferred_cutoff is None:
        raise ValueError("无法从源文件自动推断统计截止日：所有 dayN 列都没有登录记录。请使用 --as-of 手动指定。")
    cutoff = requested_cutoff or inferred_cutoff
    assert cutoff is not None

    grouped: dict[date, DailyRetention] = {}
    for reg_day, logins in parsed_rows:
        item = grouped.setdefault(
            reg_day,
            DailyRetention(
                day=reg_day,
                users=0,
                login_counts={day: 0 for day in RETENTION_DAYS},
                mature={day: reg_day + timedelta(days=day - 1) <= cutoff for day in RETENTION_DAYS},
            ),
        )
        item.users += 1
        for day, logged_in in logins.items():
            if item.mature[day] and logged_in:
                item.login_counts[day] += 1

    return sorted(grouped.values(), key=lambda item: item.day, reverse=True), cutoff


def detect_encoding(path: Path) -> str:
    for encoding in ENCODINGS:
        try:
            path.read_text(encoding=encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("unknown", b"", 0, 1, f"无法识别文件编码：{path}")


def parse_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if (serial_day := excel_serial_date(value)) is not None:
        return serial_day
    text = str(value).strip()
    match = re.search(r"(20\d{2})-(\d{2})-(\d{2})", text)
    if not match:
        match = DATE_PATTERN.search(text)
    if not match:
        return None
    return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))


def parse_int(value: object) -> int | None:
    text = str(value).strip().replace(",", "")
    if text in {"", "-", "None"}:
        return None
    return int(float(text))


def parse_percent(value: object) -> float | None:
    text = str(value).strip().replace(",", "")
    if text in {"", "-", "None"}:
        return None
    return float(text.rstrip("%")) / 100


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    encoding = detect_encoding(path)
    with path.open("r", encoding=encoding, newline="") as file:
        return list(csv.DictReader(file))


def read_xlsx_dict_rows(path: Path) -> list[dict[str, object]]:
    rows = read_xlsx_rows(path)
    if not rows:
        return []
    header = [str(cell).strip() if cell is not None else "" for cell in rows[0]]
    return [
        {header[index]: value for index, value in enumerate(row) if index < len(header)}
        for row in rows[1:]
    ]


def read_market_source(path: Path) -> dict[date, MarketDaily]:
    raw_rows = read_xlsx_dict_rows(path) if path.suffix.lower() == ".xlsx" else read_csv_rows(path)
    result: dict[date, MarketDaily] = {}
    for row in raw_rows:
        day = parse_date(row.get("日期", ""))
        if day is None:
            continue
        new_accounts = parse_int(row.get("新登账号", ""))
        rates = {
            target_day: rate
            for target_day, source_name in MARKET_SOURCE_COLUMNS.items()
            if (rate := parse_percent(row.get(source_name, ""))) is not None
        }
        result[day] = MarketDaily(new_accounts=new_accounts, rates=rates)
    if not result:
        raise ValueError(f"GDATA 新登文件没有可识别日期：{path}")
    return result


def percent_text(value: float | None) -> str:
    return "-" if value is None else f"{value:.2%}"


def diff_text(value: float | None, market: float | None) -> str:
    if value is None or market is None:
        return "-"
    return f"{value - market:.2%}"


def retention_rate(item: DailyRetention, target_day: int) -> float | None:
    if not item.mature[target_day] or item.users == 0:
        return None
    return item.login_counts[target_day] / item.users


def date_text(day: date) -> str:
    return day.isoformat()


def max_mature_day(item: DailyRetention) -> int:
    mature_days = [day for day in RETENTION_DAYS if item.mature[day]]
    return max(mature_days, default=0)


def detail_fieldnames() -> list[str]:
    return [
        "统计周期",
        "周期类型",
        "开始日期",
        "结束日期",
        "用户数",
        *(DAY_LABELS[day] for day in RETENTION_DAYS),
        "新登账号",
        *(MARKET_LABELS[day] for day in MARKET_DAYS),
        *(f"{DAY_LABELS[day]}-大盘{DAY_LABELS[day]}" for day in MARKET_DAYS),
        "统计截止日",
        "已统计最高留存日",
    ]


def detail_rows(items: list[DailyRetention], market: dict[date, MarketDaily], cutoff: date) -> list[dict[str, str | int]]:
    rows: list[dict[str, str | int]] = []
    for item in items:
        market_item = market.get(item.day)
        row: dict[str, str | int] = {
            "统计周期": period_label(item.day, item.day),
            "周期类型": "日",
            "开始日期": date_text(item.day),
            "结束日期": date_text(item.day),
            "用户数": item.users,
            "新登账号": "" if market_item is None or market_item.new_accounts is None else market_item.new_accounts,
            "统计截止日": date_text(cutoff),
            "已统计最高留存日": max_mature_day(item),
        }
        rates = {day: retention_rate(item, day) for day in RETENTION_DAYS}
        for day in RETENTION_DAYS:
            row[DAY_LABELS[day]] = percent_text(rates[day])
        for day in MARKET_DAYS:
            market_rate = market_item.rates.get(day) if market_item else None
            row[MARKET_LABELS[day]] = percent_text(market_rate)
            row[f"{DAY_LABELS[day]}-大盘{DAY_LABELS[day]}"] = diff_text(rates[day], market_rate)
        rows.append(row)
    return rows


def date_range(start_day: date, end_day: date) -> Iterable[date]:
    current = start_day
    while current <= end_day:
        yield current
        current += timedelta(days=1)


def week_range(day: date) -> tuple[date, date]:
    start_day = day - timedelta(days=day.weekday())
    return start_day, start_day + timedelta(days=6)


def week_label(start_day: date, end_day: date) -> str:
    return period_label(start_day, end_day)


def period_label(start_day: date, end_day: date) -> str:
    start_text = f"{start_day.month}.{start_day.day:02d}"
    end_text = f"{end_day.month}.{end_day.day:02d}"
    return start_text if start_day == end_day else f"{start_text}-{end_text}"


def month_range(day: date) -> tuple[date, date]:
    start_day = day.replace(day=1)
    end_day = day.replace(day=calendar.monthrange(day.year, day.month)[1])
    return start_day, end_day


def weighted_market_rate(days: list[date], market: dict[date, MarketDaily], target_day: int) -> float | None:
    weighted_sum = 0.0
    denominator = 0
    for day in days:
        item = market.get(day)
        if item is None or item.new_accounts is None or target_day not in item.rates:
            continue
        weighted_sum += item.new_accounts * item.rates[target_day]
        denominator += item.new_accounts
    if denominator == 0:
        return None
    return weighted_sum / denominator


def summarize_retention(items: list[DailyRetention], target_day: int) -> float | None:
    users = sum(item.users for item in items if item.mature[target_day])
    if users == 0:
        return None
    logins = sum(item.login_counts[target_day] for item in items if item.mature[target_day])
    return logins / users


def market_gap_field(target_day: int) -> str:
    return f"{DAY_LABELS[target_day]}-大盘{DAY_LABELS[target_day]}"


def summary_fieldnames() -> list[str]:
    return [
        "统计周期",
        "周期类型",
        "开始日期",
        "结束日期",
        "用户数",
        *(DAY_LABELS[day] for day in RETENTION_DAYS),
        "新登账号",
        *(MARKET_LABELS[day] for day in MARKET_DAYS),
        *(market_gap_field(day) for day in MARKET_DAYS),
        "统计截止日",
        "已统计最高留存日",
    ]


def build_summary_row(
    period_type: str,
    period: str,
    start_day: date,
    end_day: date,
    items: list[DailyRetention],
    market: dict[date, MarketDaily],
    cutoff: date,
) -> dict[str, str | int]:
    days = [item.day for item in items]
    rates = {day: summarize_retention(items, day) for day in RETENTION_DAYS}
    market_rates = {day: weighted_market_rate(days, market, day) for day in MARKET_DAYS}
    row: dict[str, str | int] = {
        "统计周期": period,
        "周期类型": period_type,
        "开始日期": start_day.isoformat(),
        "结束日期": end_day.isoformat(),
        "用户数": sum(item.users for item in items),
        "新登账号": sum(
            market[item.day].new_accounts or 0
            for item in items
            if item.day in market and market[item.day].new_accounts is not None
        ),
        "统计截止日": date_text(cutoff),
        "已统计最高留存日": max((max_mature_day(item) for item in items), default=0),
    }
    for day in RETENTION_DAYS:
        row[DAY_LABELS[day]] = percent_text(rates[day])
    for day in MARKET_DAYS:
        row[MARKET_LABELS[day]] = percent_text(market_rates[day])
        row[market_gap_field(day)] = diff_text(rates[day], market_rates[day])
    return row


def summary_rows(items: list[DailyRetention], market: dict[date, MarketDaily], cutoff: date) -> list[dict[str, str | int]]:
    by_day = {item.day: item for item in items}
    first_day = min(by_day)
    last_day = max(by_day)
    rows: list[dict[str, str | int]] = []

    week_start, _ = week_range(first_day)
    last_week_start, _ = week_range(last_day)
    while week_start <= last_week_start:
        week_end = week_start + timedelta(days=6)
        period_days = list(date_range(week_start, week_end))
        covered_days = [day for day in period_days if day in by_day]
        if covered_days:
            week_items = [by_day[day] for day in covered_days]
            rows.append(
                build_summary_row(
                    "周",
                    week_label(covered_days[0], covered_days[-1]),
                    covered_days[0],
                    covered_days[-1],
                    week_items,
                    market,
                    cutoff,
                )
            )
        week_start += timedelta(days=7)

    month_start = first_day.replace(day=1)
    last_month_start = last_day.replace(day=1)
    while month_start <= last_day:
        month_start_day, month_end_day = month_range(month_start)
        period_days = list(date_range(month_start_day, month_end_day))
        covered_days = [day for day in period_days if day in by_day]
        if covered_days:
            month_items = [by_day[day] for day in covered_days]
            rows.append(
                build_summary_row(
                    "月",
                    period_label(covered_days[0], covered_days[-1]),
                    covered_days[0],
                    covered_days[-1],
                    month_items,
                    market,
                    cutoff,
                )
            )
        if month_start.month == 12:
            month_start = month_start.replace(year=month_start.year + 1, month=1)
        else:
            month_start = month_start.replace(month=month_start.month + 1)

    return rows


def display_width(value: str) -> int:
    return sum(1 if ord(char) < 128 else 2 for char in value)


def write_workbook(
    output: Path,
    rows: list[dict[str, str | int]],
) -> None:
    write_xlsx_workbook(
        output,
        [
            ("每日结果", detail_fieldnames(), rows),
        ],
    )


def parse_percent_text(value: object) -> float | None:
    text = str(value or "").strip()
    if text in {"", "-"}:
        return None
    return float(text.rstrip("%")) / 100


def average_percent(rows: list[dict[str, str | int]], field: str) -> str:
    values = [parse_percent_text(row.get(field)) for row in rows]
    values = [value for value in values if value is not None]
    if not values:
        return "-"
    return f"{sum(values) / len(values):.2%}"


def weighted_percent(rows: list[dict[str, str | int]], field: str) -> str:
    weighted_sum = 0.0
    users = 0
    for row in rows:
        value = parse_percent_text(row.get(field))
        if value is None:
            continue
        row_users = int(row.get("用户数") or 0)
        weighted_sum += row_users * value
        users += row_users
    if users == 0:
        return "-"
    return f"{weighted_sum / users:.2%}"


def mature_users_from_rows(rows: list[dict[str, str | int]], field: str) -> int:
    return sum(
        int(row.get("用户数") or 0)
        for row in rows
        if parse_percent_text(row.get(field)) is not None
    )


def daily_report_summary(rows: list[dict[str, str | int]], cutoff: date) -> dict[str, object]:
    if not rows:
        return {
            "rowCount": 0,
            "users": 0,
            "latestDate": "",
            "cutoff": cutoff.isoformat(),
            "maxMatureDay": 0,
        }
    return {
        "rowCount": len(rows),
        "users": sum(int(row.get("用户数") or 0) for row in rows),
        "latestDate": max(str(row.get("结束日期") or row.get("开始日期") or "") for row in rows),
        "cutoff": cutoff.isoformat(),
        "maxMatureDay": max(int(row.get("已统计最高留存日") or 0) for row in rows),
        "avgD1": weighted_percent(rows, "次留"),
        "avgD7": weighted_percent(rows, "7日留"),
        "avgD30": weighted_percent(rows, "30日留"),
        "matureUsersD1": mature_users_from_rows(rows, "次留"),
        "matureUsersD7": mature_users_from_rows(rows, "7日留"),
        "matureUsersD30": mature_users_from_rows(rows, "30日留"),
    }


def summary_report_summary(rows: list[dict[str, str | int]], cutoff: date) -> dict[str, object]:
    total = next((row for row in rows if row.get("周期类型") == "总计"), rows[0] if rows else {})
    return {
        "rowCount": len(rows),
        "users": int(total.get("用户数") or 0) if total else 0,
        "period": total.get("统计周期", ""),
        "cutoff": cutoff.isoformat(),
        "maxMatureDay": int(total.get("已统计最高留存日") or 0) if total else 0,
        "d1": total.get("次留", "-"),
        "d7": total.get("7日留", "-"),
        "d30": total.get("30日留", "-"),
    }


def build_reports(
    *,
    private_source: Path | None = None,
    gdata_source: Path | None = None,
    requested_cutoff: date | None = None,
) -> list[dict[str, object]]:
    ensure_dirs()
    source = private_source or find_latest_source(PRIVATE_PREFIX, {".xlsx"})
    gdata = gdata_source or find_latest_source(GDATA_PREFIX, {".csv", ".xlsx"})
    private_items, as_of = read_private_source(source, requested_cutoff)
    market = read_market_source(gdata)
    details = detail_rows(private_items, market, as_of)
    summaries = summary_rows(private_items, market, as_of)
    rows = [*details, *summaries]
    return [
        {
            "id": "daily",
            "title": "每日结果",
            "description": "按日、周、月展示私域用户 2-30 日留存，并对比 GDATA 大盘留存。",
            "source": str(source),
            "gdataSource": str(gdata),
            "fieldnames": detail_fieldnames(),
            "summary": daily_report_summary(details, as_of),
            "rows": rows,
        },
    ]


def write_all_reports(reports: list[dict[str, object]]) -> dict[str, str]:
    daily = next((report for report in reports if report.get("id") == "daily"), None)
    if daily is None:
        raise ValueError("缺少每日结果，无法写出 xlsx。")
    write_workbook(
        DEFAULT_OUTPUT,
        list(daily.get("rows") or []),
    )
    return {"workbook": str(DEFAULT_OUTPUT)}


def main() -> int:
    args = parse_args()
    source = args.input or find_latest_source(PRIVATE_PREFIX, {".xlsx"})
    gdata = args.gdata or find_latest_source(GDATA_PREFIX, {".csv", ".xlsx"})
    requested_cutoff = parse_requested_cutoff(args.as_of)

    private_items, as_of = read_private_source(source, requested_cutoff)
    market = read_market_source(gdata)
    details = detail_rows(private_items, market, as_of)
    summaries = summary_rows(private_items, market, as_of)
    write_workbook(args.output, [*details, *summaries])

    print("30日留存工具")
    print(f"私域源数据：{source}")
    print(f"GDATA 新登：{gdata}")
    print(f"数据截止日：{as_of.isoformat()}")
    print(f"每日结果：{len(details)} 行")
    print(f"周/月汇总：{len(summaries)} 行")
    print(f"输出文件：{args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"运行失败：{exc}")
        raise SystemExit(1)







