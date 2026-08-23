"""Core modules for the recovered knowledge base project."""

__all__ = ["KnowledgeBase", "ChatModel", "KnowledgeBaseApi", "API", "HttpApiServer", "Main"]


def __getattr__(name: str):
    if name in {"KnowledgeBaseApi", "API"}:
        from .api import API, KnowledgeBaseApi

        return {"KnowledgeBaseApi": KnowledgeBaseApi, "API": API}[name]
    if name == "HttpApiServer":
        from .api import HttpApiServer

        return HttpApiServer
    if name == "Main":
        from .main import Main

        return Main
    if name == "KnowledgeBase":
        from .knowledge_base import KnowledgeBase

        return KnowledgeBase
    if name == "ChatModel":
        from .chat_model import ChatModel

        return ChatModel
    raise AttributeError(name)
