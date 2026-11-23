from datetime import date
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook


def read_issuer_weekly(file_path, year):
    workbook = load_workbook(file_path, data_only=True)
    try:
        sheet = workbook.worksheets[0]
        date_columns = []
        month = None

        for col in range(5, sheet.max_column, 2):
            month_cell = sheet.cell(3, col).value
            if month_cell is not None:
                month = int(month_cell)

            day = sheet.cell(4, col).value
            if day is None:
                continue

            trans_dt = date(year, month, int(day)).isoformat()
            date_columns.append((col, trans_dt))

        records = []
        for row in sheet.iter_rows(min_row=6, values_only=True):
            branch, market, name, code = row[:4]
            if code is None or not str(code).strip():
                continue

            for col, trans_dt in date_columns:
                records.append({
                    "issuer_branch": branch,
                    "issuer_market": market,
                    "issuer_name": name,
                    "issuer_code": str(code).strip(),
                    "trans_dt": trans_dt,
                    "trans_cnt": row[col - 1],
                    "trans_amount": row[col],
                })

        return pd.DataFrame.from_records(records)
    finally:
        workbook.close()


def run(conn, params):
    file_path = Path(__file__).resolve().parent / params["input_file"]
    df = read_issuer_weekly(file_path, params["input_year"])
    if df.empty:
        return 0

    columns = [
        "issuer_branch", "issuer_market", "issuer_name", "issuer_code",
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
        FROM issuer_weekly_raw_data
        WHERE trans_dt IN ({placeholders})
        LIMIT 1
        """,
        dates,
    ).fetchone()
    if existing:
        raise ValueError(f"交易日期 {existing[0]} 已入库，停止追加")

    conn.executemany(
        """
        INSERT INTO issuer_weekly_raw_data (
            issuer_branch, issuer_market, issuer_name, issuer_code,
            trans_dt, trans_cnt, trans_amount
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows.itertuples(index=False, name=None),
    )

    return len(rows)

