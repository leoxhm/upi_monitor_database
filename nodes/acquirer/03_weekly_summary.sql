-- 打标period上周,当周,上月同周
WITH period_data AS (
    SELECT
        acquirer_branch,
        acquirer_market,
        acquirer_name,
        acquirer_code,
        trans_dt,
        trans_cnt,
        trans_amount,
        CASE
            WHEN trans_dt >= date(:week_dt, '-7 days')
             AND trans_dt < :week_dt
            THEN 'current_week'

            WHEN trans_dt >= date(:week_dt, '-14 days')
             AND trans_dt < date(:week_dt, '-7 days')
            THEN 'prev_week'

            WHEN trans_dt >= :prev_month_week_start
             AND trans_dt < date(:prev_month_week_start, '+7 days')
            THEN 'prev_month_week'
        END AS period
    FROM acquirer_weekly_raw_data
    WHERE (
          (
              trans_dt >= date(:week_dt, '-14 days')
              AND trans_dt < :week_dt
          )
          OR
          (
              trans_dt >= :prev_month_week_start
              AND trans_dt < date(:prev_month_week_start, '+7 days')
          )
      )
)

-- 汇总承兑笔数,金额及其同环比,无交易天数
, weekly_summary AS (
SELECT
    acquirer_branch,
    acquirer_market,
    acquirer_name,
    acquirer_code,

    -- 当周无交易天数
    (
        COUNT(DISTINCT CASE
        WHEN period = 'current_week' AND trans_cnt IS NULL
        THEN trans_dt
    END)
        + COUNT(DISTINCT CASE
        WHEN period = 'current_week' AND trans_amount IS NULL
        THEN trans_dt
    END)
    ) / 2.0 AS current_week_inactive_days,

    -- 上周无交易天数
    (
        COUNT(DISTINCT CASE
        WHEN period = 'prev_week' AND trans_cnt IS NULL
        THEN trans_dt
    END)
        + COUNT(DISTINCT CASE
        WHEN period = 'prev_week' AND trans_amount IS NULL
        THEN trans_dt
    END)
    ) / 2.0 AS prev_week_inactive_days,

    -- 当周、上周笔数合计
    COALESCE(SUM(CASE WHEN period = 'current_week' THEN trans_cnt END), 0) AS current_week_txn_count,
    COALESCE(SUM(CASE WHEN period = 'prev_week' THEN trans_cnt END), 0) AS prev_week_txn_count,
    COALESCE(SUM(CASE WHEN period = 'prev_month_week' THEN trans_cnt END), 0) AS prev_month_same_week_txn_count,

    -- 当周、上周金额合计
    COALESCE(SUM(CASE WHEN period = 'current_week' THEN trans_amount END), 0) AS current_week_txn_amount,
    COALESCE(SUM(CASE WHEN period = 'prev_week' THEN trans_amount END), 0) AS prev_week_txn_amount,
    COALESCE(SUM(CASE WHEN period = 'prev_month_week' THEN trans_amount END), 0) AS prev_month_same_week_txn_amount

FROM period_data
GROUP BY
    acquirer_branch,
    acquirer_market,
    acquirer_name,
    acquirer_code
    )
INSERT INTO acquirer_weekly_monitor_data (
    week_dt,
    acquirer_branch,
    acquirer_market,
    acquirer_name,
    acquirer_code,
    current_week_inactive_days,
    prev_week_inactive_days,
    current_week_txn_count,
    prev_week_txn_count,
    prev_month_same_week_txn_count,
    current_week_txn_amount,
    prev_week_txn_amount,
    prev_month_same_week_txn_amount,
    txn_count_wow,
    txn_count_vs_prev_month,
    txn_amount_wow,
    txn_amount_vs_prev_month
)
SELECT
    :week_dt,
    acquirer_branch,
    acquirer_market,
    acquirer_name,
    acquirer_code,
    current_week_inactive_days,
    prev_week_inactive_days,
    current_week_txn_count,
    prev_week_txn_count,
    prev_month_same_week_txn_count,
    current_week_txn_amount,
    prev_week_txn_amount,
    prev_month_same_week_txn_amount,
    1.0 * (current_week_txn_count - prev_week_txn_count) / NULLIF(prev_week_txn_count, 0),
    1.0 * (current_week_txn_count - prev_month_same_week_txn_count) / NULLIF(prev_month_same_week_txn_count, 0),
    1.0 * (current_week_txn_amount - prev_week_txn_amount) / NULLIF(prev_week_txn_amount, 0),
    1.0 * (current_week_txn_amount - prev_month_same_week_txn_amount) / NULLIF(prev_month_same_week_txn_amount, 0)
FROM weekly_summary
WHERE acquirer_code IS NOT NULL AND acquirer_code <> ''
;