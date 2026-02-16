from abc import ABC, abstractmethod
from typing import Any, Dict, List


class HistoryStore(ABC):
    @abstractmethod
    def append(
        self,
        timestamp: str,
        action: str,
        request: Dict[str, Any],
        response: Dict[str, Any] | None = None,
        error: str | None = None,
    ) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get(self, limit: int | None = None, action: str | None = None) -> List[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def delete(self, item_id: int) -> int:
        raise NotImplementedError


class SessionIdStore(ABC):
    @abstractmethod
    def new_session_id(self, user_id: str) -> str:
        raise NotImplementedError
