--全球14日活动机构数
drop table if exists acquirer_global_active_ins_count;
create table acquirer_global_active_ins_count as
select
    trans_dt,
    count(distinct acquirer_code) as ins_count
from
acquirer_weekly_raw_data
where trans_cnt IS NOT NULL AND trans_cnt > 0 and trans_dt between date(:week_dt, '-14 days') and date(:week_dt, '-1 day')
group by trans_dt;

--日均活动机构数,分布
drop table if exists acquirer_global_active_ins_distribution;
create table acquirer_global_active_ins_distribution as
with daily_counts as (
    select acquirer_branch, trans_dt,
           count(distinct case when trans_cnt IS NOT NULL AND trans_cnt > 0 then acquirer_code end) as ins_count
    from acquirer_weekly_raw_data
    WHERE trans_dt between date(:week_dt, '-14 days') and date(:week_dt, '-1 day')
    group by acquirer_branch, trans_dt
)
select acquirer_branch, avg(ins_count) as ins_count
from daily_counts
group by acquirer_branch;

--14日非活动机构数
drop table if exists acquirer_global_inactive_ins_count;
create table acquirer_global_inactive_ins_count as
select
    '当周' as week_type,
    count(distinct acquirer_code) as ins_count
from
acquirer_weekly_alert_data
where inactive_txn_alert = '红灯' and week_dt = :week_dt
union all
select
    '上周' as week_type,
    count(distinct acquirer_code) as ins_count
from
acquirer_weekly_alert_data
where inactive_txn_alert = '红灯' and week_dt = date(:week_dt, "-7 days")
;

--14日非活动机构各大区分布
drop table if exists acquirer_global_inactive_ins_distribution;
create table acquirer_global_inactive_ins_distribution as
select
    '当周' as week_type,
    acquirer_branch,
    count(distinct acquirer_code) as ins_count
from
acquirer_weekly_alert_data
where inactive_txn_alert = '红灯' and week_dt = :week_dt
group by acquirer_branch
union all
select
    '上周' as week_type,
    acquirer_branch,
    count(distinct acquirer_code) as ins_count
from
acquirer_weekly_alert_data
where inactive_txn_alert = '红灯' and week_dt = date(:week_dt, "-7 days")
group by acquirer_branch;

--14日异动机构动态
drop table if exists acquirer_global_abnormal_ins;
create table acquirer_global_abnormal_ins as
select
'当周' as week_type,
COUNT(DISTINCT CASE WHEN overall_alert = '黄灯' THEN acquirer_code END) AS yellow_alert,
COUNT(DISTINCT CASE WHEN overall_alert = '红灯' THEN acquirer_code END) AS red_alert
from
acquirer_weekly_alert_data
WHERE week_dt = :week_dt
union all
select
'上周' as week_type,
COUNT(DISTINCT CASE WHEN overall_alert = '黄灯' THEN acquirer_code END) AS yellow_alert,
COUNT(DISTINCT CASE WHEN overall_alert = '红灯' THEN acquirer_code END) AS red_alert
from
acquirer_weekly_alert_data
where week_dt = date(:week_dt, "-7 days")
;

--当周异动机构分布
drop table if exists acquirer_global_abnormal_ins_distribution;
create table acquirer_global_abnormal_ins_distribution as
select
acquirer_branch,
COUNT(DISTINCT CASE WHEN overall_alert = '黄灯' THEN acquirer_code END) AS yellow_alert,
COUNT(DISTINCT CASE WHEN overall_alert = '红灯' THEN acquirer_code END) AS red_alert
from
acquirer_weekly_alert_data
WHERE week_dt = :week_dt
group by acquirer_branch;

--14日承兑笔数动态
drop table if exists acquirer_global_trans_cnt;
create table acquirer_global_trans_cnt as
select
    trans_dt,
    sum(trans_cnt) as trans_cnt
from
acquirer_weekly_raw_data
WHERE trans_dt between date(:week_dt, '-14 days') and date(:week_dt, '-1 day')
group by trans_dt;

--当周承兑笔数趋势
drop table if exists acquirer_global_trans_cnt_trend;
create table acquirer_global_trans_cnt_trend as
select
    acquirer_branch,
    1.0 * (sum(current_week_txn_count) - sum(prev_week_txn_count)) / nullif(sum(prev_week_txn_count), 0) as trans_cnt_wow,
    1.0 * (sum(current_week_txn_count) - sum(prev_month_same_week_txn_count)) / nullif(sum(prev_month_same_week_txn_count), 0) as trans_cnt_mom
from
acquirer_weekly_monitor_data
WHERE week_dt = :week_dt
group by acquirer_branch;

--14日承兑金额动态
drop table if exists acquirer_global_trans_amt;
create table acquirer_global_trans_amt as
select
    trans_dt,
    sum(trans_amount) as trans_amt
from
acquirer_weekly_raw_data
WHERE trans_dt between date(:week_dt, '-14 days') and date(:week_dt, '-1 day')
group by trans_dt;

--当周承兑金额动态
drop table if exists acquirer_global_trans_amt_trend;
create table acquirer_global_trans_amt_trend as
select
    acquirer_branch,
    1.0 * (sum(current_week_txn_amount) - sum(prev_week_txn_amount)) / nullif(sum(prev_week_txn_amount), 0) as trans_amount_wow,
    1.0 * (sum(current_week_txn_amount) - sum(prev_month_same_week_txn_amount)) / nullif(sum(prev_month_same_week_txn_amount), 0) as trans_amount_mom
from
acquirer_weekly_monitor_data
WHERE week_dt=:week_dt
group by acquirer_branch;
