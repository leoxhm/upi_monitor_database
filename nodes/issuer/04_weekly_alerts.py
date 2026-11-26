import pandas as pd


def run(conn, params):
    df = pd.read_sql_query(
        """
        SELECT *
        FROM issuer_weekly_monitor_data
        WHERE week_dt = :week_dt
        """,
        conn,
        params=params,
    )

    conn.execute(
        "DELETE FROM issuer_weekly_percentiles WHERE week_dt = :week_dt",
        params,
    )
    if df.empty:
        return

    # 去除市场首尾空格
    market = df["issuer_market"].fillna("").str.strip()

    df["market_group"] = market.eq("中国大陆").map({
        True: "中国大陆",
        False: "非中国大陆",
    })

    metric_columns = [
        "current_week_txn_count",
        "current_week_txn_amount",
    ]

    # 确保指标为数值，无法转换的内容作为缺失值处理
    df[metric_columns] = df[metric_columns].apply(
        pd.to_numeric, errors="coerce"
    )

    # 计算分位数：排除空市场，零值和负值仍参与，与原分位数公式一致
    result = (
        df.loc[market.ne("")]
        .groupby("market_group")[metric_columns]
        .quantile([0.50, 0.75, 0.90, 0.99])
        .rename_axis(index=["market_group", "percentile"])
        .reset_index()
    )

    # 保存实际用于分档的阈值，缺失指标写为 SQLite NULL。
    thresholds = result.astype(object).where(result.notna(), None)
    conn.executemany(
        """
        INSERT INTO issuer_weekly_percentiles (
            week_dt, market_group, percentile,
            txn_count_threshold, txn_amount_threshold
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            (params["week_dt"], group, round(fraction * 100), count, amount)
            for group, fraction, count, amount in thresholds.itertuples(
                index=False, name=None
            )
        ),
    )


    def classify_metric(value_column, labels):
        # 将每行匹配到其市场组对应的四个阈值
        thresholds = result.pivot(
            index="market_group",
            columns="percentile",
            values=value_column,
        ).reindex(columns=[0.50, 0.75, 0.90, 0.99])

        matched = thresholds.reindex(df["market_group"])
        matched.index = df.index

        values = df[value_column]
        valid = values.notna() & values.gt(0)
        complete = matched.notna().all(axis=1)

        status = pd.Series("0/无效", index=df.index)
        status.loc[valid & ~complete] = "阈值缺失"
        status.loc[valid & complete] = labels[4]

        # 从高阈值向低阈值覆盖，等于阈值时归入较低一档
        for percentile, label in zip(
            [0.99, 0.90, 0.75, 0.50],
            [labels[3], labels[2], labels[1], labels[0]],
        ):
            status.loc[
                valid & complete & values.le(matched[percentile])
            ] = label

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

    print(
        df[
            [
                "issuer_code",
                "issuer_name",
                "current_week_txn_amount",
                "current_week_amount_status",
                "current_week_txn_count",
                "current_week_count_status",
            ]
        ]
    )

    # 金额环比阈值，每组依次为（红灯、黄灯），均使用严格小于判断。
    amount_thresholds = {
        ("中国大陆", "大额"): (-0.95, -0.90),
        ("中国大陆", "超大额"): (-0.60, -0.50),
        ("中国大陆", "异常大额"): (-0.40, -0.30),
        ("非中国大陆", "大额"): (-0.40, -0.30),
        ("非中国大陆", "超大额"): (-0.35, -0.20),
        ("非中国大陆", "异常大额"): (-0.30, -0.15),
    }

    # 金额同比阈值（BF 列），每组依次为（红灯、黄灯），均使用严格小于判断。
    amount_vs_prev_month_thresholds = {
        ("中国大陆", "大额"): (-0.95, -0.90),
        ("中国大陆", "超大额"): (-0.60, -0.50),
        ("中国大陆", "异常大额"): (-0.40, -0.30),
        ("非中国大陆", "大额"): (-0.40, -0.30),
        ("非中国大陆", "超大额"): (-0.35, -0.25),
        ("非中国大陆", "异常大额"): (-0.30, -0.15),
    }

    # 笔数环比阈值（BA 列），每组依次为（红灯、黄灯），均使用严格小于判断。
    count_thresholds = {
        ("中国大陆", "大笔数"): (-0.90, -0.85),
        ("中国大陆", "超大笔数"): (-0.60, -0.45),
        ("中国大陆", "异常大笔数"): (-0.15, -0.10),
        ("非中国大陆", "大笔数"): (-0.40, -0.30),
        ("非中国大陆", "超大笔数"): (-0.35, -0.20),
        ("非中国大陆", "异常大笔数"): (-0.15, -0.10),
    }

    # 笔数同比阈值（AZ 列），每组依次为（红灯、黄灯），均使用严格小于判断。
    count_vs_prev_month_thresholds = {
        ("中国大陆", "大笔数"): (-0.90, -0.85),
        ("中国大陆", "超大笔数"): (-0.60, -0.45),
        ("中国大陆", "异常大笔数"): (-0.15, -0.10),
        ("非中国大陆", "大笔数"): (-0.40, -0.30),
        ("非中国大陆", "超大笔数"): (-0.35, -0.25),
        ("非中国大陆", "异常大笔数"): (-0.15, -0.10),
    }



    def classify_alert(df, status_column, rate_column, thresholds):
        """根据市场、当周定性和增长率，返回红灯、黄灯、正常或空白。"""
        market = df["issuer_market"].fillna("").str.strip()
        market_group = market.eq("中国大陆").map({
            True: "中国大陆",
            False: "非中国大陆",
        })

        status = df[status_column].fillna("")
        rate = pd.to_numeric(df[rate_column], errors="coerce")

        # “阈值缺失”是 Python 分档阶段产生的状态，也留空。
        valid = rate.notna() & ~status.isin(["", "0/无效", "阈值缺失"])
        alert = pd.Series("", index=df.index, dtype="string")
        alert.loc[valid] = "正常"

        for (market_name, tier), (red_threshold, yellow_threshold) in thresholds.items():
            matched = valid & market_group.eq(market_name) & status.eq(tier)
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
        "issuer_code",
        "issuer_branch",
        "issuer_market",
        "issuer_name",
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
    INSERT INTO issuer_weekly_alert_data ({columns_sql})
    VALUES ({placeholders})
    ON CONFLICT (week_dt, issuer_branch, issuer_market, issuer_name, issuer_code)
    DO UPDATE SET {updates_sql}
    """

    conn.executemany(sql, alert_df.itertuples(index=False, name=None))

    print(f"已保存 {len(alert_df)} 条监测结果")
