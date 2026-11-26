import pandas as pd


def run(conn, params):
    df = pd.read_sql_query(
        """
        SELECT *
        FROM acquirer_weekly_monitor_data
        WHERE week_dt = :week_dt
        """,
        conn,
        params=params,
    )

    conn.execute(
        "DELETE FROM acquirer_weekly_percentiles WHERE week_dt = :week_dt",
        params,
    )
    if df.empty:
        return

    metric_columns = [
        "current_week_txn_count",
        "current_week_txn_amount",
    ]

    # 确保指标为数值，无法转换的内容作为缺失值处理
    df[metric_columns] = df[metric_columns].apply(
        pd.to_numeric, errors="coerce"
    )

    # 全部收单机构共用一套分位数，数值 0 仍参与计算。
    percentiles = [0.50, 0.75, 0.90, 0.99]
    result = df[metric_columns].quantile(percentiles)
    thresholds = result.astype(object).where(result.notna(), None)
    conn.executemany(
        """
        INSERT INTO acquirer_weekly_percentiles (
            week_dt, percentile, txn_count_threshold, txn_amount_threshold
        ) VALUES (?, ?, ?, ?)
        """,
        (
            (params["week_dt"], round(fraction * 100), count, amount)
            for fraction, count, amount in thresholds.itertuples()
        ),
    )

    def classify_metric(value_column, labels):
        values = df[value_column]
        valid = values.gt(0)
        status = pd.Series("0/无效", index=df.index, dtype="string")
        status.loc[valid] = labels[-1]
        # 从高档往低档覆盖，等于阈值时归入较低档。
        for fraction, label in reversed(list(zip(percentiles, labels[:4]))):
            status.loc[valid & values.le(result.at[fraction, value_column])] = label
        return status

    df["current_week_amount_status"] = classify_metric(
        "current_week_txn_amount",
        ["小额", "中额", "大额", "超大额", "异常大额"],
    )

    # 笔数暂按与金额相同的分位分档规则
    df["current_week_count_status"] = classify_metric(
        "current_week_txn_count",
        ["小笔数", "中笔数", "大笔数", "超大笔数", "异常大笔数"],
    )

    # 各档位依次为红灯、黄灯阈值，比较时严格小于。
    amount_thresholds = {
        "中额": (-0.85, -0.80),
        "大额": (-0.80, -0.60),
        "超大额": (-0.60, -0.55),
        "异常大额": (-0.60, -0.45),
    }
    amount_vs_prev_month_thresholds = {
        **amount_thresholds,
        "超大额": (-0.75, -0.65),
    }
    count_thresholds = {
        "中笔数": (-0.70, -0.50),
        "大笔数": (-0.60, -0.40),
        "超大笔数": (-0.55, -0.35),
        "异常大笔数": (-0.40, -0.20),
    }
    count_vs_prev_month_thresholds = {
        "中笔数": (-0.75, -0.65),
        "大笔数": (-0.75, -0.65),
        "超大笔数": (-0.65, -0.50),
        "异常大笔数": (-0.40, -0.20),
    }

    def classify_alert(df, status_column, rate_column, thresholds):
        status = df[status_column]
        rate = pd.to_numeric(df[rate_column], errors="coerce")
        alert = pd.Series("", index=df.index, dtype="string")
        for tier, (red_threshold, yellow_threshold) in thresholds.items():
            matched = status.eq(tier) & rate.notna()
            alert.loc[matched] = "正常"
            alert.loc[matched & rate.lt(yellow_threshold)] = "黄灯"
            alert.loc[matched & rate.lt(red_threshold)] = "红灯"
        return alert

    df["amount_wow_alert"] = classify_alert(
        df,
        "current_week_amount_status",
        "txn_amount_wow",
        amount_thresholds,
    )

    df["amount_vs_prev_month_alert"] = classify_alert(
        df,
        "current_week_amount_status",
        "txn_amount_vs_prev_month",
        amount_vs_prev_month_thresholds,
    )

    df["count_wow_alert"] = classify_alert(
        df,
        "current_week_count_status",
        "txn_count_wow",
        count_thresholds,
    )

    df["count_vs_prev_month_alert"] = classify_alert(
        df,
        "current_week_count_status",
        "txn_count_vs_prev_month",
        count_vs_prev_month_thresholds,
    )

    current_inactive = pd.to_numeric(
        df["current_week_inactive_days"], errors="coerce"
    )
    prev_inactive = pd.to_numeric(
        df["prev_week_inactive_days"], errors="coerce"
    )
    prev_count = pd.to_numeric(df["prev_week_txn_count"], errors="coerce")

    # 非活跃交易：两周无交易天数合计等于 14
    df["inactive_txn_alert"] = "正常"
    inactive = (current_inactive + prev_inactive).eq(14)
    df.loc[inactive.fillna(False), "inactive_txn_alert"] = "红灯"

    # 交易突降：当周 7 天无交易，上周有交易且笔数超过 50
    df["txn_drop_alert"] = "正常"
    txn_drop = (
        current_inactive.eq(7)
        & prev_inactive.lt(7)
        & prev_count.gt(50)
    )
    df.loc[txn_drop.fillna(False), "txn_drop_alert"] = "红灯"

    # 异常总览：任一红灯优先，其次任一黄灯
    alerts = df[
        [
            "amount_wow_alert",
            "amount_vs_prev_month_alert",
            "count_wow_alert",
            "count_vs_prev_month_alert",
        ]
    ].fillna("")

    df["overall_alert"] = "正常"
    df.loc[alerts.eq("黄灯").any(axis=1), "overall_alert"] = "黄灯"
    df.loc[alerts.eq("红灯").any(axis=1), "overall_alert"] = "红灯"

    alert_columns = [
        "week_dt",
        "acquirer_code",
        "acquirer_branch",
        "acquirer_market",
        "acquirer_name",
        "current_week_amount_status",
        "current_week_count_status",
        "amount_wow_alert",
        "amount_vs_prev_month_alert",
        "count_wow_alert",
        "count_vs_prev_month_alert",
        "inactive_txn_alert",
        "txn_drop_alert",
        "overall_alert",
    ]

    # 将 pandas 缺失值转换为 None，写入 SQLite 后就是 NULL。
    alert_df = df[alert_columns].astype(object)
    alert_df = alert_df.where(alert_df.notna(), None)

    columns_sql = ", ".join(alert_columns)
    placeholders = ", ".join("?" for _ in alert_columns)
    updates_sql = ", ".join(
        f"{column} = excluded.{column}"
        for column in alert_columns[5:]
    )

    sql = f"""
    INSERT INTO acquirer_weekly_alert_data ({columns_sql})
    VALUES ({placeholders})
    ON CONFLICT (week_dt, acquirer_branch, acquirer_market, acquirer_name, acquirer_code)
    DO UPDATE SET {updates_sql}
    """

    conn.executemany(sql, alert_df.itertuples(index=False, name=None))

    print(f"已保存 {len(alert_df)} 条监测结果")
