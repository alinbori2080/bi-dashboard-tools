# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import csv
import posixpath
import re
import zipfile
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET


APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
OUTPUT_DIR = APP_DIR / "output"
DEFAULT_OUTPUT = OUTPUT_DIR / "推送用户留存付费汇总.csv"
NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CELL_REF = re.compile(r"([A-Z]+)(\d+)")
SHEET_DATE = re.compile(r"^\s*(\d{1,2})[./-](\d{1,2})\s*$")
DAY_HEADER = re.compile(r"^day(\d{3,4})$", re.I)
FILL_HEADER = re.compile(r"^fillpoint_(\d{3,4})$", re.I)
YEAR_IN_NAME = re.compile(r"(20\d{2})")
RETENTION_DAYS = (2, 3, 7)
LTV_DAYS = (7, 15, 30)
BLANK_NUMBER_TEXT = {"", "-", "—", "–", r"\n", "null", "none", "nan", "n/a", "na"}


@dataclass(frozen=True)
class SheetData:
    name: str
    rows: list[list[str]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="分实验组、对照组统计推送留存和 LTV。")
    parser.add_argument("--input", type=Path, help="源 XLSX；默认读取目录中最新的名将杀 私域需求*.xlsx。")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help=f"输出 CSV；默认：{DEFAULT_OUTPUT}")
    parser.add_argument("--year", type=int, help="Sheet 日期所属年份；默认从文件名推断。")
    return parser.parse_args()


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def find_input() -> Path:
    ensure_dirs()
    candidates = [
        item for item in DATA_DIR.iterdir()
        if item.is_file()
        and item.name.startswith("名将杀 私域需求")
        and item.suffix.lower() == ".xlsx"
        and not item.name.startswith("~$")
    ]
    if not candidates:
        raise FileNotFoundError(f"未找到名将杀 私域需求*.xlsx，请把源文件放到：{DATA_DIR}")
    return max(candidates, key=lambda item: item.stat().st_mtime)


def infer_year(path: Path, requested: int | None) -> int:
    if requested is not None:
        return requested
    match = YEAR_IN_NAME.search(path.stem)
    return int(match.group(1)) if match else date.today().year


def shared_strings(book: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in book.namelist():
        return []
    root = ET.fromstring(book.read("xl/sharedStrings.xml"))
    return ["".join(node.text or "" for node in item.findall(".//x:t", NS)) for item in root.findall("x:si", NS)]


def workbook_relationships(book: zipfile.ZipFile) -> dict[str, str]:
    root = ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))
    result: dict[str, str] = {}
    for relation in root.findall("r:Relationship", REL_NS):
        target = relation.attrib.get("Target", "")
        normalized = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))
        result[relation.attrib.get("Id", "")] = normalized
    return result


def column_number(reference: str) -> int | None:
    match = CELL_REF.match(reference)
    if not match:
        return None
    number = 0
    for character in match.group(1):
        number = number * 26 + ord(character) - ord("A") + 1
    return number


def cell_value(cell: ET.Element, strings: list[str]) -> str:
    cell_type = cell.attrib.get("t", "")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//x:t", NS)).strip()
    node = cell.find("x:v", NS)
    value = "" if node is None or node.text is None else node.text
    if cell_type == "s" and value:
        return strings[int(float(value))].strip()
    return value.strip()


def sheet_rows(book: zipfile.ZipFile, target: str, strings: list[str]) -> list[list[str]]:
    root = ET.fromstring(book.read(target))
    result: list[list[str]] = []
    for row_node in root.findall(".//x:sheetData/x:row", NS):
        cells: dict[int, str] = {}
        for cell in row_node.findall("x:c", NS):
            index = column_number(cell.attrib.get("r", ""))
            if index is not None:
                cells[index] = cell_value(cell, strings)
        result.append([cells.get(index, "") for index in range(1, max(cells, default=0) + 1)])
    return result


def read_workbook(path: Path) -> list[SheetData]:
    with zipfile.ZipFile(path) as book:
        strings = shared_strings(book)
        relations = workbook_relationships(book)
        root = ET.fromstring(book.read("xl/workbook.xml"))
        result: list[SheetData] = []
        for sheet in root.findall(".//x:sheets/x:sheet", NS):
            name = sheet.attrib.get("name", "").strip()
            relation_id = sheet.attrib.get(f"{{{OFFICE_REL_NS}}}id", "")
            target = relations.get(relation_id)
            if not target:
                raise ValueError(f"无法读取 Sheet「{name}」。")
            result.append(SheetData(name, sheet_rows(book, target, strings)))
        return result


def parse_sheet_day(name: str, year: int) -> date | None:
    match = SHEET_DATE.match(name)
    if not match:
        return None
    try:
        return date(year, int(match.group(1)), int(match.group(2)))
    except ValueError as exc:
        raise ValueError(f"Sheet 名不是有效日期：{name}") from exc


def parse_column_day(token: str, push_day: date) -> date:
    digits = token.zfill(4)
    month, day_number = int(digits[:2]), int(digits[2:])
    result = date(push_day.year, month, day_number)
    if result < push_day - timedelta(days=180):
        result = date(push_day.year + 1, month, day_number)
    elif result > push_day + timedelta(days=185):
        result = date(push_day.year - 1, month, day_number)
    return result


def number(value: str, sheet: str, row: int, column: str) -> float:
    text = value.strip().replace(",", "")
    if text.lower() in BLANK_NUMBER_TEXT:
        return 0.0
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"Sheet「{sheet}」第 {row} 行「{column}」不是数字：{value!r}") from exc


def at(row: list[str], index: int) -> str:
    return row[index] if index < len(row) else ""


def consecutive(columns: dict[date, int], start: date) -> list[tuple[date, int]]:
    result: list[tuple[date, int]] = []
    current = start
    while current in columns:
        result.append((current, columns[current]))
        current += timedelta(days=1)
    return result


def display_day(value: date) -> str:
    return f"{value.month}/{value.day:02d}"


def retention_text(logins: int, people: int) -> str:
    return "" if people == 0 else f"{logins / people:.2%}"


def ltv_text(value: float | None) -> str:
    return "" if value is None else f"{value:,.2f}"


def analyze(sheet: SheetData, push_day: date) -> list[dict[str, str | int]]:
    if not sheet.rows:
        raise ValueError(f"Sheet「{sheet.name}」为空。")
    headers = [str(item).strip() for item in sheet.rows[0]]
    try:
        account_col, control_col = headers.index("account"), headers.index("is_control")
    except ValueError as exc:
        raise ValueError(f"Sheet「{sheet.name}」缺少 account 或 is_control。") from exc

    day_cols: dict[date, int] = {}
    fill_cols: dict[date, int] = {}
    for index, header in enumerate(headers):
        day_match, fill_match = DAY_HEADER.match(header), FILL_HEADER.match(header)
        if day_match:
            column_day = parse_column_day(day_match.group(1), push_day)
            if column_day >= push_day:
                day_cols[column_day] = index
        elif fill_match:
            column_day = parse_column_day(fill_match.group(1), push_day)
            if column_day >= push_day:
                fill_cols[column_day] = index

    login_columns, payment_columns = consecutive(day_cols, push_day), consecutive(fill_cols, push_day)
    if not login_columns or not payment_columns:
        raise ValueError(f"Sheet「{sheet.name}」缺少从推送日期开始的 day 或 fillpoint 日期列。")

    people = {0: 0, 1: 0}
    logins = {group: {day_number: 0 for day_number in RETENTION_DAYS} for group in (0, 1)}
    payments = {group: [0.0] * len(payment_columns) for group in (0, 1)}
    accounts: set[str] = set()

    for row_number, row in enumerate(sheet.rows[1:], start=2):
        account = at(row, account_col).strip()
        if not account:
            continue
        if account in accounts:
            raise ValueError(f"Sheet「{sheet.name}」包含重复账号：{account}")
        accounts.add(account)
        raw_group = number(at(row, control_col), sheet.name, row_number, "is_control")
        if raw_group not in (0.0, 1.0):
            raise ValueError(f"Sheet「{sheet.name}」第 {row_number} 行 is_control 不是 0 或 1。")
        group = int(raw_group)
        people[group] += 1

        for day_number in RETENTION_DAYS:
            target = push_day + timedelta(days=day_number - 1)
            column = day_cols.get(target)
            if column is not None:
                login_value = number(at(row, column), sheet.name, row_number, headers[column])
                if login_value > 0:
                    logins[group][day_number] += 1
        for offset, (_, column) in enumerate(payment_columns):
            payments[group][offset] += number(at(row, column), sheet.name, row_number, headers[column])

    login_days, payment_days = len(login_columns), len(payment_columns)
    rows: list[dict[str, str | int]] = []
    for group in (0, 1):
        cumulative: list[float] = []
        running = 0.0
        for daily_payment in payments[group]:
            running += daily_payment
            cumulative.append(running)
        ltv: dict[int, float | None] = {
            target: cumulative[target - 1] / people[group]
            if payment_days >= target and people[group] else None
            for target in LTV_DAYS
        }
        longest_value = cumulative[-1] / people[group] if people[group] else None
        longest_is_standard = payment_days in LTV_DAYS
        rows.append({
            "推送日期": display_day(push_day),
            "组别": "实验组" if group == 0 else "对照组",
            "is_control": group,
            "推送人数": people[group],
            "登录数据截止日期": display_day(login_columns[-1][0]),
            "充值数据截止日期": display_day(payment_columns[-1][0]),
            "可统计登录天数": login_days,
            "可统计充值天数": payment_days,
            "次日登录人数": logins[group][2] if login_days >= 2 else "",
            "3日登录人数": logins[group][3] if login_days >= 3 else "",
            "7日登录人数": logins[group][7] if login_days >= 7 else "",
            "次日留存": retention_text(logins[group][2], people[group]) if login_days >= 2 else "",
            "3日留存": retention_text(logins[group][3], people[group]) if login_days >= 3 else "",
            "7日留存": retention_text(logins[group][7], people[group]) if login_days >= 7 else "",
            "LTV7": ltv_text(ltv[7]),
            "LTV15": ltv_text(ltv[15]),
            "LTV30": ltv_text(ltv[30]),
            "最长LTV指标": "" if longest_is_standard else f"LTV{payment_days}",
            "最长周期LTV": "" if longest_is_standard else ltv_text(longest_value),
        })
    return rows


def fieldnames() -> list[str]:
    return [
        "批次",
        "组别",
        "用户量",
        "LTV7",
        "LTV7差值",
        "LTV15",
        "LTV15差值",
        "LTV30",
        "LTV30差值",
        "次日留存率",
        "3日留存率",
        "7日留存率",
        "大盘次日留存率",
        "大盘3日留存率",
        "大盘7日留存率",
    ]


def parse_output_number(value: object) -> float | None:
    text = str(value).strip().replace(",", "")
    if text.lower() in BLANK_NUMBER_TEXT:
        return None
    return float(text)


def displayed_ltv(
    row: dict[str, str | int], target_day: int
) -> tuple[str, str | None]:
    standard_value = str(row.get(f"LTV{target_day}", "")).strip()
    if standard_value:
        return standard_value, None

    label = str(row.get("最长LTV指标", "")).strip()
    longest_value = str(row.get("最长周期LTV", "")).strip()
    match = re.fullmatch(r"LTV([0-9]+)", label)
    if not match or not longest_value:
        return "", None
    actual_day = int(match.group(1))
    lower_bound = 0 if target_day == 7 else 7 if target_day == 15 else 15
    if lower_bound < actual_day < target_day:
        return longest_value, label
    return "", None


def ltv_cell(value: str, note: str | None) -> str:
    return value if not note else f"{value}（{note}）"


def difference_cell(
    experiment_value: str,
    control_value: str,
    note: str | None,
) -> str:
    left = parse_output_number(experiment_value)
    right = parse_output_number(control_value)
    if left is None or right is None:
        return ""
    value = f"{left - right:,.2f}"
    return value if not note else f"{value}（{note}）"


def batch_label(push_date: str) -> str:
    month_text, day_text = push_date.split("/", 1)
    return f"{int(month_text)}月{int(day_text)}日"


def read_market_retention() -> dict[str, dict[str, str]]:
    ensure_dirs()
    candidates = [
        item
        for item in DATA_DIR.iterdir()
        if item.is_file()
        and item.name.startswith("新登_")
        and item.suffix.lower() == ".csv"
    ]
    if not candidates:
        return {}
    path = max(candidates, key=lambda item: item.stat().st_mtime)
    daily: dict[date, tuple[int, dict[str, float]]] = {}
    rate_columns = {
        "次留率": "次留率",
        "3留率": "3留率",
        "7留率": "7留率",
    }
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            match = re.match(r"^(20\d{2})-(\d{2})-(\d{2})", str(row.get("日期", "")))
            if not match:
                continue
            day = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            accounts_text = str(row.get("新登账号", "")).replace(",", "").strip()
            if accounts_text.lower() in BLANK_NUMBER_TEXT:
                continue
            accounts = int(float(accounts_text))
            rates: dict[str, float] = {}
            for output_name, source_name in rate_columns.items():
                value = str(row.get(source_name, "")).strip()
                if value.lower() not in BLANK_NUMBER_TEXT:
                    rates[output_name] = float(value.rstrip("%")) / 100
            daily[day] = (accounts, rates)

    result: dict[str, dict[str, str]] = {}
    for push_day, (_, rates) in daily.items():
        if push_day.weekday() == 3:
            result[display_day(push_day)] = {
                name: f"{value:.2%}" for name, value in rates.items()
            }
            continue
        if push_day.weekday() != 4:
            continue

        window_days = [push_day + timedelta(days=offset) for offset in range(6)]
        if any(day not in daily for day in window_days):
            continue
        total_accounts = sum(daily[day][0] for day in window_days)
        if total_accounts == 0:
            continue
        weighted: dict[str, str] = {}
        for field_name in rate_columns:
            if any(field_name not in daily[day][1] for day in window_days):
                continue
            value = sum(
                daily[day][0] * daily[day][1][field_name]
                for day in window_days
            ) / total_accounts
            weighted[field_name] = f"{value:.2%}"
        result[display_day(push_day)] = weighted
    return result


def build_report_rows(
    raw_rows: list[dict[str, str | int]],
) -> list[dict[str, str | int]]:
    market = read_market_retention()
    report: list[dict[str, str | int]] = []
    for index in range(0, len(raw_rows), 2):
        pair = raw_rows[index:index + 2]
        experiment = next((row for row in pair if row["组别"] == "实验组"), None)
        control = next((row for row in pair if row["组别"] == "对照组"), None)
        if experiment is None or control is None:
            raise ValueError("每个推送日期必须同时包含实验组和对照组。")

        push_date = str(experiment["推送日期"])
        market_row = market.get(push_date, {})
        experiment_row: dict[str, str | int] = {
            "批次": batch_label(push_date),
            "组别": "实验组(A组)",
            "用户量": experiment["推送人数"],
            "次日留存率": experiment["次日留存"],
            "3日留存率": experiment["3日留存"],
            "7日留存率": experiment["7日留存"],
            "大盘次日留存率": market_row.get("次留率", ""),
            "大盘3日留存率": market_row.get("3留率", ""),
            "大盘7日留存率": market_row.get("7留率", ""),
        }
        control_row: dict[str, str | int] = {
            "批次": "",
            "组别": "对照组(B组)",
            "用户量": control["推送人数"],
            "次日留存率": control["次日留存"],
            "3日留存率": control["3日留存"],
            "7日留存率": control["7日留存"],
            "大盘次日留存率": "",
            "大盘3日留存率": "",
            "大盘7日留存率": "",
        }

        for target_day in LTV_DAYS:
            value_column = f"LTV{target_day}"
            difference_column = f"LTV{target_day}差值"
            experiment_value, experiment_note = displayed_ltv(experiment, target_day)
            control_value, control_note = displayed_ltv(control, target_day)
            note = experiment_note or control_note
            experiment_row[value_column] = ltv_cell(experiment_value, experiment_note)
            control_row[value_column] = ltv_cell(control_value, control_note)
            experiment_row[difference_column] = difference_cell(
                experiment_value,
                control_value,
                note,
            )
            control_row[difference_column] = ""

        report.extend([experiment_row, control_row])
    return report


def write_csv(rows: list[dict[str, str | int]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames(), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parse_batch_date(batch: str, year: int) -> date | None:
    match = re.fullmatch(r"(\d{1,2})月(\d{1,2})日", str(batch).strip())
    if not match:
        return None
    try:
        return date(year, int(match.group(1)), int(match.group(2)))
    except ValueError:
        return None


def report_summary(rows: list[dict[str, str | int]]) -> dict[str, object]:
    experiment_rows = [row for row in rows if str(row.get("组别", "")).startswith("实验组")]
    control_rows = [row for row in rows if str(row.get("组别", "")).startswith("对照组")]
    latest_experiment = experiment_rows[-1] if experiment_rows else {}
    return {
        "batchCount": len(experiment_rows),
        "experimentUsers": sum(int(row.get("用户量") or 0) for row in experiment_rows),
        "controlUsers": sum(int(row.get("用户量") or 0) for row in control_rows),
        "latestBatch": latest_experiment.get("批次", ""),
        "latestLtv7Diff": latest_experiment.get("LTV7差值", ""),
        "latestLtv15Diff": latest_experiment.get("LTV15差值", ""),
        "latestLtv30Diff": latest_experiment.get("LTV30差值", ""),
        "latestD1Retention": latest_experiment.get("次日留存率", ""),
        "latestD3Retention": latest_experiment.get("3日留存率", ""),
        "latestD7Retention": latest_experiment.get("7日留存率", ""),
    }


def build_report() -> dict[str, object]:
    source = find_input()
    year = infer_year(source, None)
    sheets = read_workbook(source)
    dated: list[tuple[date, SheetData]] = []
    skipped: list[str] = []
    for sheet in sheets:
        push_day = parse_sheet_day(sheet.name, year)
        if push_day is None:
            skipped.append(sheet.name)
        else:
            dated.append((push_day, sheet))
    if not dated:
        raise ValueError("没有名称形如 5.14、6.4 的推送日期 Sheet。")
    dated.sort(key=lambda item: item[0])
    raw_rows: list[dict[str, str | int]] = []
    for push_day, sheet in dated:
        raw_rows.extend(analyze(sheet, push_day))
    rows = build_report_rows(raw_rows)
    current_batch = ""
    for row in rows:
        batch = str(row.get("批次", "")).strip()
        if batch:
            current_batch = batch
        batch_day = parse_batch_date(current_batch, year) if current_batch else None
        row["批次日期"] = batch_day.isoformat() if batch_day else ""
    return {
        "id": "push_retention_ltv",
        "title": "推送用户留存付费汇总",
        "description": "按推送批次对比实验组与对照组的留存率、LTV 和差值。",
        "source": str(source),
        "year": year,
        "skippedSheets": skipped,
        "fieldnames": fieldnames(),
        "summary": report_summary(rows),
        "rows": rows,
    }


def write_report_csv(report: dict[str, object]) -> Path:
    rows = [dict(row) for row in (report.get("rows") or [])]
    output = OUTPUT_DIR / "推送用户留存付费汇总.csv"
    write_csv(rows, output)
    return output


def write_all_reports(reports: list[dict[str, object]]) -> dict[str, str]:
    return {str(report["id"]): str(write_report_csv(report)) for report in reports}


def main() -> int:
    args = parse_args()
    source = args.input or find_input()
    year = infer_year(source, args.year)
    sheets = read_workbook(source)
    dated: list[tuple[date, SheetData]] = []
    skipped: list[str] = []
    for sheet in sheets:
        push_day = parse_sheet_day(sheet.name, year)
        if push_day is None:
            skipped.append(sheet.name)
        else:
            dated.append((push_day, sheet))
    if not dated:
        raise ValueError("没有名称形如 5.14、6.4 的推送日期 Sheet。")
    dated.sort(key=lambda item: item[0])
    raw_rows: list[dict[str, str | int]] = []
    for push_day, sheet in dated:
        raw_rows.extend(analyze(sheet, push_day))
    report_rows = build_report_rows(raw_rows)
    write_csv(report_rows, args.output)
    print(f"源数据：{source}")
    print(f"推送日期 Sheet：{len(dated)} 个")
    print(f"输出分组行数：{len(report_rows)} 行")
    if skipped:
        print(f"已跳过非日期 Sheet：{', '.join(skipped)}")
    print(f"输出文件：{args.output}")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"运行失败：{exc}")
        raise SystemExit(1)
