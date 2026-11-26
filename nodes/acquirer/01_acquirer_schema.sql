-- 在这里填写建表和索引语句，每条 SQL 以分号结束。
-- 初始化程序统一管理事务，此文件直接填写 CREATE TABLE / CREATE INDEX。
-- 常用类型：TEXT 文本、INTEGER 整数、REAL 浮点数。
-- 取消下面示例的注释并修改即可。

-- CREATE TABLE IF NOT EXISTS weekly_records (
--     id INTEGER PRIMARY KEY AUTOINCREMENT,
--     business_week TEXT NOT NULL,
--     object_id TEXT NOT NULL,
--     transaction_count INTEGER NOT NULL DEFAULT 0,
--     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
--     UNIQUE (business_week, object_id)
-- );

-- CREATE INDEX IF NOT EXISTS idx_weekly_records_week
-- ON weekly_records (business_week);

-- 先删除依赖周统计表的预警表，再重建业务表。
DROP TABLE IF EXISTS acquirer_weekly_alert_data;
DROP TABLE IF EXISTS acquirer_weekly_monitor_data;
DROP TABLE IF EXISTS acquirer_weekly_raw_data;

CREATE TABLE IF NOT EXISTS acquirer_weekly_raw_data (
    id INTEGER PRIMARY KEY,

    acquirer_branch TEXT,             -- 收单分公司
    acquirer_market TEXT,             -- 收单市场
    acquirer_name TEXT,               -- 收单机构名称
    acquirer_code TEXT,               -- 收单机构代码

    trans_dt TEXT NOT NULL,         -- 交易日期 YYYY-MM-DD
    trans_cnt INTEGER,              -- 交易笔数
    trans_amount REAL              -- 交易金额，人民币元
);


CREATE TABLE IF NOT EXISTS acquirer_weekly_monitor_data (
    week_dt TEXT NOT NULL,                     -- 统计基准日期 YYYY-MM-DD
    acquirer_branch TEXT,                        -- 收单分公司
    acquirer_market TEXT,                        -- 收单市场
    acquirer_name TEXT,                          -- 收单机构名称
    acquirer_code TEXT NOT NULL,                 -- 收单机构代码

    -- 无交易天数
    current_week_inactive_days INTEGER,        -- 当周无交易天数
    prev_week_inactive_days INTEGER,           -- 上周无交易天数

    -- 交易笔数汇总及增长率
    current_week_txn_count INTEGER,            -- 当周笔数合计
    prev_week_txn_count INTEGER,               -- 上周笔数合计
    prev_month_same_week_txn_count INTEGER,    -- 上月同周笔数合计
    txn_count_vs_prev_month REAL,              -- 较上月同周笔数增长率
    txn_count_wow REAL,                        -- 笔数周环比增长率

    -- 交易金额汇总及增长率
    current_week_txn_amount REAL,              -- 当周金额合计
    prev_week_txn_amount REAL,                 -- 上周金额合计
    prev_month_same_week_txn_amount REAL,      -- 上月同周金额合计
    txn_amount_wow REAL,                       -- 金额周环比增长率
    txn_amount_vs_prev_month REAL,             -- 较上月同周金额增长率

    PRIMARY KEY (week_dt, acquirer_branch, acquirer_market, acquirer_name, acquirer_code)
);


CREATE TABLE IF NOT EXISTS acquirer_weekly_alert_data (
    week_dt TEXT NOT NULL,                     -- 统计基准日期 YYYY-MM-DD
    acquirer_branch TEXT,                       -- 收单分公司
    acquirer_market TEXT,                       -- 收单市场
    acquirer_name TEXT,                         -- 收单机构名称
    acquirer_code TEXT NOT NULL,                 -- 收单机构代码

    current_week_amount_status TEXT,          -- 当周金额定性
    current_week_count_status TEXT,           -- 当周笔数定性
    amount_wow_alert TEXT,                     -- 金额环比异常
    amount_vs_prev_month_alert TEXT,          -- 金额较上月同周异常
    count_wow_alert TEXT,                      -- 笔数环比异常
    count_vs_prev_month_alert TEXT,           -- 笔数较上月同周异常
    inactive_txn_alert TEXT,                   -- 非活跃交易
    txn_drop_alert TEXT,                       -- 交易突降
    overall_alert TEXT,                        -- 异常总览

    PRIMARY KEY (week_dt, acquirer_branch, acquirer_market, acquirer_name, acquirer_code),

    FOREIGN KEY (week_dt, acquirer_branch, acquirer_market, acquirer_name, acquirer_code)
        REFERENCES acquirer_weekly_monitor_data (week_dt, acquirer_branch, acquirer_market, acquirer_name, acquirer_code)
);

-- 每个统计周使用的交易笔数、金额分档阈值。
CREATE TABLE IF NOT EXISTS acquirer_weekly_percentiles (
    week_dt TEXT NOT NULL,
    percentile INTEGER NOT NULL CHECK (percentile IN (50, 75, 90, 99)),
    txn_count_threshold REAL,
    txn_amount_threshold REAL,
    PRIMARY KEY (week_dt, percentile)
);
