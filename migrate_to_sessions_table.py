#!/usr/bin/env python3
"""
数据库迁移脚本：将旧的单表结构迁移到新的主子表结构

使用方法:
    python migrate_to_sessions_table.py
    
功能:
    - 从旧表 kb_history 读取所有数据
    - 按 session_id 分组，创建主表 kb_sessions 记录
    - 将消息数据迁移到子表 kb_session_messages
    - 保留原始表作为备份（重命名为 kb_history_backup）
    
注意:
    - 请先备份数据库！
    - 执行前请确保没有程序正在使用数据库
    - 迁移完成后请测试验证
"""

import json
import sys
from typing import Dict, List, Any

# 添加src目录到路径
sys.path.insert(0, 'src')

from src.store.db.connection import DatabaseConnection


def migrate_history_table(
    backend: str,
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
    old_table: str = "kb_history",
    sessions_table: str = "kb_sessions",
    messages_table: str = "kb_session_messages",
):
    """执行数据迁移"""
    print("开始数据库迁移...")
    print(f"数据库: {backend}://{host}:{port}/{database}")
    print(f"旧表: {old_table}")
    print(f"新主表: {sessions_table}")
    print(f"新子表: {messages_table}")
    print()
    
    conn_obj = DatabaseConnection(
        backend=backend,
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
    )
    
    conn = conn_obj.connect()
    try:
        with conn.cursor() as cur:
            # 1. 检查旧表是否存在
            if backend == "mysql":
                cur.execute(f"SHOW TABLES LIKE '{old_table}'")
            else:
                cur.execute(f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{old_table}')")
            
            if not cur.fetchone():
                print(f"⚠️  旧表 {old_table} 不存在，无需迁移")
                return
            
            # 2. 读取所有旧数据
            print(f"正在读取 {old_table} 中的数据...")
            cur.execute(f"SELECT * FROM {old_table} ORDER BY id")
            rows = cur.fetchall()
            
            if not rows:
                print("⚠️  旧表为空，无需迁移")
                return
            
            # 获取列名
            if backend == "mysql":
                cur.execute(f"SHOW COLUMNS FROM {old_table}")
                columns = [row[0] for row in cur.fetchall()]
            else:
                cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{old_table}' ORDER BY ordinal_position")
                columns = [row[0] for row in cur.fetchall()]
            
            print(f"找到 {len(rows)} 条记录")
            print(f"表字段: {columns}")
            print()
            
            # 3. 检查是否有 session_id 字段（新版本表结构）
            has_session_id = 'session_id' in columns
            
            if not has_session_id:
                print("⚠️  旧表没有 session_id 字段（旧版本表结构）")
                print("将为每条记录生成独立的 session_id")
                print()
                
                # 为每条记录生成列模板（添加 session_id 和 user_id）
                import time
                
                # 为了避免 session_id 重复，使用时间戳 + 递增计数器
                base_ts = int(time.time() * 1000)
            
            # 4. 按 session_id 分组数据
            print("正在分组数据...")
            sessions_data: Dict[str, List[Dict[str, Any]]] = {}
            
            for idx, row in enumerate(rows):
                row_dict = dict(zip(columns, row))
                
                if has_session_id:
                    session_id = row_dict.get('session_id')
                    if not session_id:
                        # 有 session_id 字段但值为空，生成一个
                        session_id = f"migrated_{row_dict.get('id', idx)}"
                        row_dict['session_id'] = session_id
                else:
                    # 没有 session_id 字段，为每条记录生成唯一ID
                    # 使用 migrated_<timestamp>_<id> 格式
                    record_id = row_dict.get('id', idx)
                    session_id = f"migrated_{base_ts}_{record_id}"
                    row_dict['session_id'] = session_id
                    
                    # 尝试从 request_json 中提取 user_id（如果有）
                    if 'user_id' not in row_dict:
                        try:
                            request = json.loads(row_dict.get('request_json', '{}'))
                            row_dict['user_id'] = request.get('user_id')
                        except:
                            row_dict['user_id'] = None
                
                if session_id not in sessions_data:
                    sessions_data[session_id] = []
                sessions_data[session_id].append(row_dict)
            
            print(f"共分组为 {len(sessions_data)} 个会话")
            print()
            
            # 5. 先创建新表结构
            print("正在创建新表结构...")
            
            if backend == "mysql":
                # 创建主表：会话元数据
                sessions_ddl = f"""
                CREATE TABLE IF NOT EXISTS {sessions_table} (
                    id BIGINT PRIMARY KEY AUTO_INCREMENT,
                    session_id VARCHAR(128) UNIQUE NOT NULL,
                    user_id VARCHAR(128) NULL,
                    title TEXT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    message_count INT NOT NULL DEFAULT 0,
                    KEY idx_user_id (user_id),
                    KEY idx_created_at (created_at),
                    KEY idx_updated_at (updated_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
                # 创建子表：消息记录
                messages_ddl = f"""
                CREATE TABLE IF NOT EXISTS {messages_table} (
                    id BIGINT PRIMARY KEY AUTO_INCREMENT,
                    session_id VARCHAR(128) NOT NULL,
                    timestamp VARCHAR(64) NOT NULL,
                    action VARCHAR(64) NOT NULL,
                    user_id VARCHAR(128) NULL,
                    request_json LONGTEXT NOT NULL,
                    response_json LONGTEXT NULL,
                    error LONGTEXT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    KEY idx_session_id (session_id),
                    KEY idx_action (action),
                    KEY idx_timestamp (timestamp),
                    KEY idx_user_id (user_id),
                    FOREIGN KEY (session_id) REFERENCES {sessions_table}(session_id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
                cur.execute(sessions_ddl)
                cur.execute(messages_ddl)
            else:
                # PostgreSQL
                sessions_ddl = f"""
                CREATE TABLE IF NOT EXISTS {sessions_table} (
                    id BIGSERIAL PRIMARY KEY,
                    session_id VARCHAR(128) UNIQUE NOT NULL,
                    user_id VARCHAR(128) NULL,
                    title TEXT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    message_count INT NOT NULL DEFAULT 0
                )
                """
                messages_ddl = f"""
                CREATE TABLE IF NOT EXISTS {messages_table} (
                    id BIGSERIAL PRIMARY KEY,
                    session_id VARCHAR(128) NOT NULL,
                    timestamp VARCHAR(64) NOT NULL,
                    action VARCHAR(64) NOT NULL,
                    user_id VARCHAR(128) NULL,
                    request_json TEXT NOT NULL,
                    response_json TEXT NULL,
                    error TEXT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES {sessions_table}(session_id) ON DELETE CASCADE
                )
                """
                cur.execute(sessions_ddl)
                cur.execute(messages_ddl)
                
                # 创建索引
                cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{sessions_table}_user ON {sessions_table}(user_id)")
                cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{sessions_table}_created ON {sessions_table}(created_at)")
                cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{sessions_table}_updated ON {sessions_table}(updated_at)")
                cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{messages_table}_session ON {messages_table}(session_id)")
                cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{messages_table}_action ON {messages_table}(action)")
                cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{messages_table}_timestamp ON {messages_table}(timestamp)")
                cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{messages_table}_user ON {messages_table}(user_id)")
            
            conn.commit()
            print("✓ 新表创建成功")
            print()
            
            # 6. 迁移数据到新表
            print("正在迁移数据到新表结构...")
            
            for idx, (session_id, items) in enumerate(sessions_data.items(), 1):
                # 插入主表记录
                first_item = items[0]
                last_item = items[-1]
                
                # 解析 request_json 获取 query 和 user_id
                try:
                    request = json.loads(first_item.get('request_json', '{}'))
                    title = request.get('query', '')[:200]
                    user_id = first_item.get('user_id') or request.get('user_id')
                except:
                    title = ''
                    user_id = first_item.get('user_id')
                
                created_at = first_item.get('created_at') or first_item.get('timestamp')
                updated_at = last_item.get('created_at') or last_item.get('timestamp')
                message_count = len(items)
                
                # 检查主表记录是否已存在
                cur.execute(f"SELECT id FROM {sessions_table} WHERE session_id = %s", (session_id,))
                if cur.fetchone():
                    print(f"  [{idx}/{len(sessions_data)}] Session {session_id[:20]}... 已存在，跳过")
                    continue
                
                # 插入主表
                cur.execute(
                    f"""
                    INSERT INTO {sessions_table} 
                    (session_id, user_id, title, created_at, updated_at, message_count)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (session_id, user_id, title, created_at, updated_at, message_count)
                )
                
                # 插入子表记录
                for item in items:
                    cur.execute(
                        f"""
                        INSERT INTO {messages_table}
                        (session_id, timestamp, action, user_id, request_json, response_json, error, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            session_id,
                            item.get('timestamp'),
                            item.get('action'),
                            item.get('user_id'),
                            item.get('request_json'),
                            item.get('response_json'),
                            item.get('error'),
                            item.get('created_at')
                        )
                    )
                
                if idx % 10 == 0:
                    print(f"  已迁移 {idx}/{len(sessions_data)} 个会话...")
            
            conn.commit()
            print(f"✓ 成功迁移 {len(sessions_data)} 个会话")
            print()
            
            # 7. 备份旧表
            backup_table = f"{old_table}_backup"
            print(f"正在备份旧表为 {backup_table}...")
            
            # 检查备份表是否已存在
            if backend == "mysql":
                cur.execute(f"SHOW TABLES LIKE '{backup_table}'")
            else:
                cur.execute(f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{backup_table}')")
            
            if cur.fetchone():
                print(f"⚠️  备份表 {backup_table} 已存在，跳过备份")
            else:
                if backend == "mysql":
                    cur.execute(f"RENAME TABLE {old_table} TO {backup_table}")
                else:
                    cur.execute(f"ALTER TABLE {old_table} RENAME TO {backup_table}")
                conn.commit()
                print(f"✓ 旧表已重命名为 {backup_table}")
            
            print()
            print("=" * 60)
            print("迁移完成！")
            print("=" * 60)
            print(f"✓ 主表 {sessions_table}: {len(sessions_data)} 条会话记录")
            print(f"✓ 子表 {messages_table}: {len(rows)} 条消息记录")
            print(f"✓ 备份表: {backup_table}")
            print()
            print("下一步:")
            print("1. 测试应用程序，确保功能正常")
            print("2. 确认无误后，可以删除备份表:")
            print(f"   DROP TABLE {backup_table};")
            
    except Exception as exc:
        conn.rollback()
        print(f"❌ 迁移失败: {exc}")
        raise
    finally:
        conn.close()


def main():
    """主函数：从 config.json 读取配置并执行迁移"""
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
    except FileNotFoundError:
        print("❌ 找不到 config.json 文件")
        print("请在项目根目录运行此脚本")
        sys.exit(1)
    
    # 读取数据库配置（直接从 db 键下）
    db_config = config.get('db', {})
    
    if not db_config:
        print("⚠️  配置文件中未找到数据库配置（db）")
        print("当前使用内存存储，无需迁移")
        return
    
    # 获取后端类型
    backend = db_config.get('backend', 'mysql')
    
    # 根据后端类型读取具体配置
    backend_config = db_config.get(backend, {})
    
    if not backend_config:
        print(f"⚠️  找不到 {backend} 的配置信息")
        print(f"请检查 config.json 中的 db.{backend} 配置")
        return
    
    # 确认用户是否要执行迁移
    print("=" * 60)
    print("数据库迁移工具 - 单表 -> 主子表结构")
    print("=" * 60)
    print()
    print(f"数据库类型: {backend}")
    print(f"数据库地址: {backend_config.get('host')}:{backend_config.get('port')}")
    print(f"数据库名称: {backend_config.get('database')}")
    print()
    print("⚠️  警告：此操作将修改数据库结构！")
    print()
    print("迁移内容:")
    print("  - 创建主表: kb_sessions（会话元数据）")
    print("  - 创建子表: kb_session_messages（消息记录）")
    print("  - 迁移旧表数据到新表")
    print("  - 备份旧表为: kb_history_backup")
    print()
    
    response = input("确认执行迁移吗？(yes/no): ").strip().lower()
    if response != 'yes':
        print("已取消迁移")
        return
    
    migrate_history_table(
        backend=backend,
        host=backend_config.get('host', 'localhost'),
        port=backend_config.get('port', 3306 if backend == 'mysql' else 5432),
        user=backend_config.get('user', 'root' if backend == 'mysql' else 'postgres'),
        password=backend_config.get('password', ''),
        database=backend_config.get('database', 'knowledge_base'),
        old_table=db_config.get('table', 'kb_history'),
    )


if __name__ == '__main__':
    main()
