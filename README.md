# upi_monitor_database

发卡侧周监测工作流。读取 Excel，用 SQLite 汇总交易数据并生成预警和输出表。

依赖 Python、pandas 和 openpyxl。把输入文件路径和统计日期配置在 `nodes/issuer_weekly_params.json`，再从仓库根目录执行：

```bash
python executor.py --workflow workflows/issuer_weekly.json --db weekly_test.db
```

工作流会重建业务表，请使用专门的测试数据库。
