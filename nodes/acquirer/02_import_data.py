from datetime import date
from pathlib import Path
import re

import pandas as pd
from openpyxl import load_workbook


def read_acquirer_weekly(file_path, year):
    workbook = load_workbook(file_path, data_only=True)
    try:
        sheet = workbook.worksheets[0]
        entity_headers = (
            "收单分公司", "收单市场", "收单机构名称", "收单机构代码",
        )
        date_columns = []
        if tuple(cell.value for cell in sheet[1][:4]) == entity_headers:
            first_data_row = 2
            for col in range(5, sheet.max_column, 2):
                header = str(sheet.cell(1, col).value)
                match = re.fullmatch(r"(\d{1,2})(\d{2})承兑笔数", header)
                if match is None:
                    if "无承兑天数" in header:
                        break
                    raise ValueError(f"无法识别日期表头：{header}")
                month, day = map(int, match.groups())
                amount_header = f"{''.join(match.groups())}承兑人民币金额"
                if sheet.cell(1, col + 1).value != amount_header:
                    raise ValueError(f"{header} 缺少对应金额列")
                date_columns.append((col, date(year, month, day).isoformat()))
        elif tuple(cell.value for cell in sheet[3][:4]) == entity_headers:
            first_data_row = 6
            month = None
            for col in range(5, sheet.max_column, 2):
                month_cell = sheet.cell(3, col).value
                if month_cell is not None:
                    month = int(month_cell)
                day = sheet.cell(4, col).value
                if day is not None:
                    date_columns.append((col, date(year, month, int(day)).isoformat()))
        else:
            raise ValueError("找不到收单机构的四列表头，请检查输入文件")
        if not date_columns:
            raise ValueError("收单文件里没有找到交易日期列")

        records = []
        for row in sheet.iter_rows(min_row=first_data_row, values_only=True):
            branch, market, name, code = row[:4]
            if code is None or not str(code).strip():
                continue

            for col, trans_dt in date_columns:
                records.append({
                    "acquirer_branch": branch,
                    "acquirer_market": market,
                    "acquirer_name": name,
                    "acquirer_code": str(code).strip(),
                    "trans_dt": trans_dt,
                    "trans_cnt": row[col - 1],
                    "trans_amount": row[col],
                })

        return pd.DataFrame.from_records(records)
    finally:
        workbook.close()


def run(conn, params):
    file_path = Path(__file__).resolve().parent / params["input_file"]
    df = read_acquirer_weekly(file_path, params["input_year"])
    if df.empty:
        return 0

    columns = [
        "acquirer_branch", "acquirer_market", "acquirer_name", "acquirer_code",
        "trans_dt", "trans_cnt", "trans_amount",
    ]

    # 保留真实的 0，把 Excel 空白写成 SQLite NULL。
    rows = df[columns].copy()
    rows["trans_cnt"] = rows["trans_cnt"].astype("Int64")
    rows = rows.astype(object).where(rows.notna(), None)

    dates = rows["trans_dt"].unique().tolist()
    placeholders = ", ".join("?" for _ in dates)

    existing = conn.execute(
        f"""
        SELECT trans_dt
        FROM acquirer_weekly_raw_data
        WHERE trans_dt IN ({placeholders})
        LIMIT 1
        """,
        dates,
    ).fetchone()
    if existing:
        raise ValueError(f"交易日期 {existing[0]} 已入库，停止追加")

    conn.executemany(
        """
        INSERT INTO acquirer_weekly_raw_data (
            acquirer_branch, acquirer_market, acquirer_name, acquirer_code,
            trans_dt, trans_cnt, trans_amount
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows.itertuples(index=False, name=None),
    )

    return len(rows)

