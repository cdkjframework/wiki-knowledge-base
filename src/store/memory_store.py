import time
from threading import Lock
from typing import Any, Dict, List

from .interfaces import HistoryStore, SessionIdStore


class InMemoryHistoryStore(HistoryStore):
    def __init__(self):
        self._items: List[Dict[str, Any]] = []
        self._next_id = 1

    def append(
        self,
        timestamp: str,
        action: str,
        request: Dict[str, Any],
        response: Dict[str, Any] | None = None,
        error: str | None = None,
        thinking_summary: str | None = None,
    ) -> Dict[str, Any]:
        item: Dict[str, Any] = {
            "id": int(self._next_id),
            "timestamp": timestamp,
            "action": action,
            "request": request,
        }
        self._next_id += 1
        if response is not None:
            item["response"] = response
        if error:
            item["error"] = error
        if thinking_summary:
            item["thinking_summary"] = thinking_summary
        self._items.append(item)
        return item

    def get(self, limit: int | None = None, action: str | None = None) -> List[Dict[str, Any]]:
        records = self._items
        if action:
            records = [x for x in records if x.get("action") == action]
        if limit is not None:
            records = records[-max(0, int(limit)) :]
        return list(records)

    def get_by_sessions(self, limit: int | None = None, action: str | None = None) -> List[Dict[str, Any]]:
        """按session分组获取历史记录，按最后入库时间倒序"""
        records = self._items
        if action:
            records = [x for x in records if x.get("action") == action]
        
        # 按session_id分组，记录每个session的最后一个item的索引
        sessions_dict: Dict[str, List[Dict[str, Any]]] = {}
        session_last_index: Dict[str, int] = {}
        
        for idx, item in enumerate(records):
            session_id = item.get("request", {}).get("session_id")
            if not session_id:
                continue
            
            if session_id not in sessions_dict:
                sessions_dict[session_id] = []
            sessions_dict[session_id].append(item)
            session_last_index[session_id] = idx  # 记录最后一个索引
        
        # 按最后索引倒序排列session
        sorted_sessions = sorted(session_last_index.items(), key=lambda x: x[1], reverse=True)
        
        # 转换为结果格式
        result = []
        for session_id, _ in sorted_sessions:
            items = sessions_dict[session_id]
            result.append({
                "session_id": session_id,
                "first_query": items[0].get("request", {}).get("query", "新建聊天"),
                "timestamp": items[-1].get("timestamp"),  # 使用最后一条记录的时间
                "user_id": items[0].get("request", {}).get("user_id"),
                "count": len(items),
                "items": items
            })
        
        if limit is not None:
            result = result[:max(0, int(limit))]  # 取前limit个（已经是倒序）
        
        return result

    def clear(self) -> int:
        count = len(self._items)
        self._items.clear()
        return count

    def delete(self, item_id: int) -> int:
        target = int(item_id)
        before = len(self._items)
        self._items = [x for x in self._items if int(x.get("id", -1)) != target]
        return 1 if len(self._items) != before else 0

    def delete_session(self, session_id: str) -> int:
        """删除整个session的所有消息"""
        before = len(self._items)
        self._items = [
            x for x in self._items 
            if x.get("request", {}).get("session_id") != session_id
        ]
        return before - len(self._items)


class InMemorySessionIdStore(SessionIdStore):
    def __init__(self):
        self._lock = Lock()
        self._counters: Dict[str, int] = {}

    def new_session_id(self, user_id: str) -> str:
        user = str(user_id or "").strip()
        if not user:
            raise ValueError("user_id is required")
        with self._lock:
            counter = self._counters.get(user, 0) + 1
            self._counters[user] = counter
        return f"s_{user}_{time.time_ns()}_{counter}"
