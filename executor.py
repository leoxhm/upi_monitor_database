"""按 JSON 工作流中声明的顺序执行 SQLite 节点。"""

import argparse
import json
import runpy
import sqlite3
from pathlib import Path
from database import DB_PATH, get_connection


def execute_sql_file(conn, path, params):
    # SQLite 判断语句边界，保留字符串和触发器中的分号。
    sql = path.read_text(encoding="utf-8")
    start = 0
    for end, char in enumerate(sql, 1):
        if char == ";" and sqlite3.complete_statement(sql[start:end]):
            conn.execute(sql[start:end], params)
            start = end
    if sql[start:].strip():
        conn.execute(sql[start:], params)


def run_pipeline(workflow_path, params=None, db_path=DB_PATH):
    workflow_path = Path(workflow_path).resolve()
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    if params is None:
        params_file = workflow.get("params_file")
        params = {}
        if params_file:
            path = workflow_path.parent / params_file
            try:
                params = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise ValueError(f"无法读取参数文件 {path}：{exc}") from exc
    if not isinstance(params, dict):
        raise ValueError("工作流参数必须是 JSON 对象")
    missing = [key for key in workflow.get("required_params", []) if key not in params]
    if missing:
        raise ValueError(f"缺少工作流参数：{', '.join(missing)}")

    entries = workflow["nodes"]
    if not isinstance(entries, list) or not entries:
        raise ValueError("nodes 必须是非空的节点路径列表")

    nodes = [workflow_path.parent / entry for entry in entries]
    for node in nodes:
        if node.suffix not in {".sql", ".py"} or not node.is_file():
            raise ValueError(f"无效的节点文件：{node}")

    with get_connection(db_path) as conn:
        conn.execute("BEGIN")
        for node in nodes:
            try:
                if node.suffix == ".sql":
                    execute_sql_file(conn, node, params)
                else:
                    runpy.run_path(str(node))["run"](conn, params)
            except Exception as exc:
                raise RuntimeError(f"节点 {node.name} 执行失败：{exc}") from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--workflow", type=Path, help="JSON 工作流路径")
    source.add_argument("--init", type=Path, metavar="SCHEMA", help="执行建表 SQL 文件")
    parser.add_argument("--db", type=Path, default=DB_PATH, help="SQLite 数据库路径")
    args = parser.parse_args()

    if args.init:
        with get_connection(args.db) as conn:
            conn.execute("BEGIN")
            execute_sql_file(conn, args.init, {})
        return

    run_pipeline(args.workflow, db_path=args.db)
    print("工作流完成，结果已提交。")


if __name__ == "__main__":
    main()
