import json
from typing import Any, Dict, List

from .connection import DatabaseConnection
from ..interfaces import HistoryStore
from .utils import _VALID_TABLE_RE, safe_json_loads


class DatabaseHistoryStore(HistoryStore):
    def __init__(
        self,
        backend: str,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
        table: str = "kb_session_messages",
        connect_timeout: int = 5,
    ):
        table_name = (table or "").strip()
        if not _VALID_TABLE_RE.match(table_name):
            raise ValueError(f"Invalid history table name: {table!r}")

        self.messages_table = table_name  # 子表：消息记录
        self.sessions_table = "kb_sessions"  # 主表：会话元数据
        self._conn = DatabaseConnection(
            backend=backend,
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            connect_timeout=connect_timeout,
        )
        self._ensure_table()

    def _ensure_table(self) -> None:
        """创建主表（sessions）和子表（messages）"""
        if self._conn.backend == "mysql":
            # 创建主表：会话元数据
            sessions_ddl = f"""
            CREATE TABLE IF NOT EXISTS {self.sessions_table} (
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
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """
            # 创建子表：消息记录
            messages_ddl = f"""
            CREATE TABLE IF NOT EXISTS {self.messages_table} (
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
                FOREIGN KEY (session_id) REFERENCES {self.sessions_table}(session_id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """
            self._conn.run_write(sessions_ddl)
            self._conn.run_write(messages_ddl)
            return

        # PostgreSQL
        # 创建主表：会话元数据
        create_sessions = f"""
        CREATE TABLE IF NOT EXISTS {self.sessions_table} (
            id BIGSERIAL PRIMARY KEY,
            session_id VARCHAR(128) UNIQUE NOT NULL,
            user_id VARCHAR(128) NULL,
            title TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            message_count INT NOT NULL DEFAULT 0
        );
        """
        # 创建子表：消息记录
        create_messages = f"""
        CREATE TABLE IF NOT EXISTS {self.messages_table} (
            id BIGSERIAL PRIMARY KEY,
            session_id VARCHAR(128) NOT NULL,
            timestamp VARCHAR(64) NOT NULL,
            action VARCHAR(64) NOT NULL,
            user_id VARCHAR(128) NULL,
            request_json TEXT NOT NULL,
            response_json TEXT NULL,
            error TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES {self.sessions_table}(session_id) ON DELETE CASCADE
        );
        """
        
        self._conn.run_write(create_sessions)
        self._conn.run_write(create_messages)
        
        # 创建索引（主表）
        self._conn.run_write(
            f"CREATE INDEX IF NOT EXISTS idx_{self.sessions_table}_user ON {self.sessions_table}(user_id);"
        )
        self._conn.run_write(
            f"CREATE INDEX IF NOT EXISTS idx_{self.sessions_table}_created ON {self.sessions_table}(created_at);"
        )
        self._conn.run_write(
            f"CREATE INDEX IF NOT EXISTS idx_{self.sessions_table}_updated ON {self.sessions_table}(updated_at);"
        )
        # 创建索引（子表）
        self._conn.run_write(
            f"CREATE INDEX IF NOT EXISTS idx_{self.messages_table}_session ON {self.messages_table}(session_id);"
        )
        self._conn.run_write(
            f"CREATE INDEX IF NOT EXISTS idx_{self.messages_table}_action ON {self.messages_table}(action);"
        )
        self._conn.run_write(
            f"CREATE INDEX IF NOT EXISTS idx_{self.messages_table}_timestamp ON {self.messages_table}(timestamp);"
        )
        self._conn.run_write(
            f"CREATE INDEX IF NOT EXISTS idx_{self.messages_table}_user ON {self.messages_table}(user_id);"
        )

    def append(
        self,
        timestamp: str,
        action: str,
        request: Dict[str, Any],
        response: Dict[str, Any] | None = None,
        error: str | None = None,
    ) -> Dict[str, Any]:
        request_json = json.dumps(request, ensure_ascii=False)
        response_json = None if response is None else json.dumps(response, ensure_ascii=False)
        session_id = request.get("session_id")
        user_id = request.get("user_id")
        
        # 如果没有session_id，生成一个系统session_id
        if not session_id:
            import time
            # 使用 system_ 前缀标记为系统事件
            session_id = f"system_{action}_{int(time.time() * 1000)}"
        
        conn = self._conn.connect()
        try:
            with conn.cursor() as cur:
                # 1. 确保主表存在session记录
                # 检查session是否存在
                cur.execute(
                    f"SELECT id FROM {self.sessions_table} WHERE session_id = %s",
                    (session_id,)
                )
                session_exists = cur.fetchone() is not None
                
                if not session_exists:
                    # 创建新session，title为第一个问题或action名称
                    query = request.get("query") or action or ""
                    title = str(query)[:200]  # 限制标题长度
                    cur.execute(
                        f"""
                        INSERT INTO {self.sessions_table} 
                        (session_id, user_id, title, message_count) 
                        VALUES (%s, %s, %s, 1)
                        """,
                        (session_id, user_id, title)
                    )
                else:
                    # 更新现有session的更新时间和消息计数
                    if self._conn.backend == "mysql":
                        # MySQL的ON UPDATE CURRENT_TIMESTAMP会自动更新updated_at
                        cur.execute(
                            f"""
                            UPDATE {self.sessions_table} 
                            SET message_count = message_count + 1,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE session_id = %s
                            """,
                            (session_id,)
                        )
                    else:
                        # PostgreSQL需要手动设置updated_at
                        cur.execute(
                            f"""
                            UPDATE {self.sessions_table} 
                            SET message_count = message_count + 1,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE session_id = %s
                            """,
                            (session_id,)
                        )
                
                # 2. 插入子表消息记录
                if self._conn.backend == "postgresql":
                    cur.execute(
                        f"""
                        INSERT INTO {self.messages_table}
                        (session_id, timestamp, action, user_id, request_json, response_json, error)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (session_id, timestamp, action, user_id, request_json, response_json, error),
                    )
                    row = cur.fetchone()
                    item_id = int(row[0]) if row else None
                else:
                    cur.execute(
                        f"""
                        INSERT INTO {self.messages_table}
                        (session_id, timestamp, action, user_id, request_json, response_json, error)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (session_id, timestamp, action, user_id, request_json, response_json, error),
                    )
                    item_id = int(cur.lastrowid) if getattr(cur, "lastrowid", None) else None
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        item: Dict[str, Any] = {
            "timestamp": timestamp,
            "action": action,
            "request": request,
        }
        if item_id is not None:
            item["id"] = item_id
        if response is not None:
            item["response"] = response
        if error:
            item["error"] = error
        return item

    def get(self, limit: int | None = None, action: str | None = None) -> List[Dict[str, Any]]:
        """从子表查询消息记录"""
        params: List[Any] = []
        where = ""
        if action:
            where = " WHERE action = %s"
            params.append(action)

        if limit is None:
            order_clause = " ORDER BY id ASC"
        else:
            lim = max(0, int(limit))
            if lim == 0:
                return []
            order_clause = " ORDER BY id DESC LIMIT %s"
            params.append(lim)

        sql = (
            f"SELECT id, timestamp, action, session_id, user_id, request_json, response_json, error "
            f"FROM {self.messages_table}{where}{order_clause}"
        )

        conn = self._conn.connect()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
        finally:
            conn.close()

        out: List[Dict[str, Any]] = []
        for row in rows:
            item: Dict[str, Any] = {
                "id": int(row[0]),
                "timestamp": str(row[1]),
                "action": str(row[2]),
                "request": safe_json_loads(row[5]),
            }
            if row[3]:  # session_id
                item["session_id"] = str(row[3])
            if row[4]:  # user_id
                item["user_id"] = str(row[4])
            response = safe_json_loads(row[6])
            if row[6] is not None:
                item["response"] = response
            if row[7]:
                item["error"] = str(row[7])
            out.append(item)

        if limit is not None:
            out.reverse()
        return out

    def get_by_sessions(self, limit: int | None = None, action: str | None = None) -> List[Dict[str, Any]]:
        """通过主表查询sessions，并关联子表获取消息"""
        params: List[Any] = []
        
        # 从主表获取session列表（按更新时间倒序）
        session_sql = f"""
        SELECT session_id, user_id, title, created_at, updated_at, message_count
        FROM {self.sessions_table}
        ORDER BY updated_at DESC
        """
        
        if limit is not None:
            lim = max(0, int(limit))
            if lim == 0:
                return []
            session_sql += " LIMIT %s"
            params.append(lim)

        conn = self._conn.connect()
        try:
            with conn.cursor() as cur:
                # 获取session列表
                cur.execute(session_sql, tuple(params))
                sessions = cur.fetchall()
                
                if not sessions:
                    return []
                
                # 获取这些session的所有消息
                session_ids = [str(row[0]) for row in sessions]
                placeholders = ','.join(['%s'] * len(session_ids))
                
                message_where = f" WHERE m.session_id IN ({placeholders})"
                message_params = session_ids.copy()
                
                if action:
                    message_where += " AND m.action = %s"
                    message_params.append(action)
                
                message_sql = f"""
                SELECT m.id, m.timestamp, m.action, m.session_id, m.user_id, 
                       m.request_json, m.response_json, m.error
                FROM {self.messages_table} m
                {message_where}
                ORDER BY m.session_id, m.id ASC
                """
                
                cur.execute(message_sql, tuple(message_params))
                rows = cur.fetchall()
        finally:
            conn.close()

        # 按session组织消息数据
        sessions_dict: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            session_id = str(row[3]) if row[3] else None
            if not session_id:
                continue
                
            item: Dict[str, Any] = {
                "id": int(row[0]),
                "timestamp": str(row[1]),
                "action": str(row[2]),
                "session_id": session_id,
                "user_id": str(row[4]) if row[4] else None,
                "request": safe_json_loads(row[5]),
            }
            response = safe_json_loads(row[6])
            if row[6] is not None:
                item["response"] = response
            if row[7]:
                item["error"] = str(row[7])
            
            if session_id not in sessions_dict:
                sessions_dict[session_id] = []
            sessions_dict[session_id].append(item)

        # 构建返回结果（保持主表的排序顺序）
        result = []
        for session_row in sessions:
            session_id = str(session_row[0])
            user_id = str(session_row[1]) if session_row[1] else None
            title = str(session_row[2]) if session_row[2] else "新建聊天"
            created_at = session_row[3]
            updated_at = session_row[4]
            message_count = int(session_row[5]) if session_row[5] else 0
            
            items = sessions_dict.get(session_id, [])
            
            # 如果指定了action过滤，从主表的message_count可能与实际过滤后的数量不同
            actual_count = len(items)
            
            # 使用主表的updated_at作为timestamp（最后活动时间）
            if self._conn.backend == "mysql":
                timestamp = updated_at.isoformat() if hasattr(updated_at, 'isoformat') else str(updated_at)
            else:
                timestamp = updated_at.isoformat() if hasattr(updated_at, 'isoformat') else str(updated_at)
            
            # 如果有消息，使用第一条消息的query作为标题（覆盖主表的title）
            if items:
                first_query = items[0].get("request", {}).get("query", title)
            else:
                first_query = title
            
            result.append({
                "session_id": session_id,
                "first_query": first_query,
                "timestamp": timestamp,
                "user_id": user_id,
                "count": actual_count,
                "items": items
            })
        
        return result

    def clear(self) -> int:
        """清空所有表（先清子表，再清主表）"""
        count = self._conn.run_write(f"DELETE FROM {self.messages_table}")
        self._conn.run_write(f"DELETE FROM {self.sessions_table}")
        return count

    def delete(self, item_id: int) -> int:
        """删除单条消息记录，并更新主表的message_count"""
        # 先获取这条消息的session_id
        conn = self._conn.connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT session_id FROM {self.messages_table} WHERE id = %s",
                    (int(item_id),)
                )
                row = cur.fetchone()
                session_id = str(row[0]) if row and row[0] else None
                
                # 删除消息
                cur.execute(
                    f"DELETE FROM {self.messages_table} WHERE id = %s",
                    (int(item_id),)
                )
                affected = cur.rowcount
                
                # 如果消息属于某个session，更新主表计数
                if session_id and affected > 0:
                    cur.execute(
                        f"""
                        UPDATE {self.sessions_table} 
                        SET message_count = message_count - 1,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE session_id = %s AND message_count > 0
                        """,
                        (session_id,)
                    )
                    
                    # 如果session没有消息了，删除session记录
                    cur.execute(
                        f"DELETE FROM {self.sessions_table} WHERE session_id = %s AND message_count = 0",
                        (session_id,)
                    )
                
            conn.commit()
            return affected
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def delete_session(self, session_id: str) -> int:
        """删除整个session（包括主表和所有子表记录）"""
        # 由于设置了外键 ON DELETE CASCADE，删除主表时会自动删除子表
        return self._conn.run_write(
            f"DELETE FROM {self.sessions_table} WHERE session_id = %s",
            (str(session_id),)
        )
