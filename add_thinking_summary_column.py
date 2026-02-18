#!/usr/bin/env python3
"""
数据库迁移脚本：为消息表添加 thinking_summary 列

使用方法:
    python add_thinking_summary_column.py

说明:
    此脚本会为 kb_session_messages 表添加 thinking_summary 列,用于存储深度思考的摘要内容。
    支持 MySQL 和 PostgreSQL 数据库。
    
注意:
    1. 请在运行前备份数据库
    2. 确保 config.json 中的数据库配置正确
    3. 如果表名不是 kb_session_messages,请相应修改脚本中的表名
"""

import json
import sys
from pathlib import Path


def load_config():
    """加载配置文件"""
    config_path = Path(__file__).parent / "config.json"
    if not config_path.exists():
        print(f"错误: 配置文件不存在: {config_path}")
        sys.exit(1)
    
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def migrate_mysql(config):
    """MySQL 数据库迁移"""
    try:
        import mysql.connector
    except ImportError:
        print("错误: 未安装 mysql-connector-python，请运行: pip install mysql-connector-python")
        sys.exit(1)
    
    db_config = config.get("history_store", {})
    table_name = db_config.get("table", "kb_session_messages")
    
    conn = mysql.connector.connect(
        host=db_config.get("host", "localhost"),
        port=db_config.get("port", 3306),
        user=db_config.get("user", "root"),
        password=db_config.get("password", ""),
        database=db_config.get("database", "kb"),
    )
    
    cursor = conn.cursor()
    
    # 检查列是否已存在
    cursor.execute(f"""
        SELECT COUNT(*) 
        FROM information_schema.COLUMNS 
        WHERE TABLE_SCHEMA = %s 
        AND TABLE_NAME = %s 
        AND COLUMN_NAME = 'thinking_summary'
    """, (db_config.get("database", "kb"), table_name))
    
    if cursor.fetchone()[0] > 0:
        print(f"列 thinking_summary 已存在于表 {table_name} 中，无需迁移")
        cursor.close()
        conn.close()
        return
    
    # 添加列
    print(f"正在为表 {table_name} 添加 thinking_summary 列...")
    cursor.execute(f"""
        ALTER TABLE {table_name} 
        ADD COLUMN thinking_summary LONGTEXT NULL 
        AFTER error
    """)
    conn.commit()
    
    cursor.close()
    conn.close()
    print("✓ MySQL 迁移完成")


def migrate_postgresql(config):
    """PostgreSQL 数据库迁移"""
    try:
        import psycopg2
    except ImportError:
        print("错误: 未安装 psycopg2，请运行: pip install psycopg2-binary")
        sys.exit(1)
    
    db_config = config.get("history_store", {})
    table_name = db_config.get("table", "kb_session_messages")
    
    conn = psycopg2.connect(
        host=db_config.get("host", "localhost"),
        port=db_config.get("port", 5432),
        user=db_config.get("user", "postgres"),
        password=db_config.get("password", ""),
        database=db_config.get("database", "kb"),
    )
    
    cursor = conn.cursor()
    
    # 检查列是否已存在
    cursor.execute("""
        SELECT COUNT(*) 
        FROM information_schema.columns 
        WHERE table_name = %s 
        AND column_name = 'thinking_summary'
    """, (table_name,))
    
    if cursor.fetchone()[0] > 0:
        print(f"列 thinking_summary 已存在于表 {table_name} 中，无需迁移")
        cursor.close()
        conn.close()
        return
    
    # 添加列
    print(f"正在为表 {table_name} 添加 thinking_summary 列...")
    cursor.execute(f"""
        ALTER TABLE {table_name} 
        ADD COLUMN thinking_summary TEXT NULL
    """)
    conn.commit()
    
    cursor.close()
    conn.close()
    print("✓ PostgreSQL 迁移完成")


def main():
    print("=" * 60)
    print("数据库迁移：添加 thinking_summary 列")
    print("=" * 60)
    print()
    
    config = load_config()
    
    # 检查是否配置了数据库
    if "history_store" not in config:
        print("警告: config.json 中未配置 history_store,跳过数据库迁移")
        print("如果您正在使用内存存储,则无需迁移")
        return
    
    db_config = config["history_store"]
    backend = db_config.get("backend", "").lower()
    
    if not backend:
        print("错误: 未指定数据库后端 (backend)")
        sys.exit(1)
    
    print(f"数据库类型: {backend}")
    print(f"主机: {db_config.get('host', 'localhost')}")
    print(f"数据库: {db_config.get('database', 'kb')}")
    print(f"表名: {db_config.get('table', 'kb_session_messages')}")
    print()
    
    # 确认执行
    response = input("是否继续执行迁移? (yes/no): ").strip().lower()
    if response not in ["yes", "y"]:
        print("已取消迁移")
        return
    
    print()
    
    try:
        if backend == "mysql":
            migrate_mysql(config)
        elif backend == "postgresql":
            migrate_postgresql(config)
        else:
            print(f"错误: 不支持的数据库类型: {backend}")
            sys.exit(1)
        
        print()
        print("=" * 60)
        print("✓ 迁移成功完成")
        print("=" * 60)
        
    except Exception as e:
        print()
        print("=" * 60)
        print(f"✗ 迁移失败: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
