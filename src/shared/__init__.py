"""
跨域共享工具与类型。

配置路径解析等公共能力放在本包，避免业务域互相硬编码路径。
"""

from .config_paths import (
    load_project_config,
    project_root,
    resolve_config_path,
    resolve_project_root,
)

__all__ = [
    "load_project_config",
    "project_root",
    "resolve_config_path",
    "resolve_project_root",
]
