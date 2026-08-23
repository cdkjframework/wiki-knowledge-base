"""
项目路径与配置文件解析。

优先读取 conf/ 下配置，兼容仓库根目录历史 config.json。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict


def project_root() -> Path:
    """
    返回仓库根目录。

    Returns:
        项目根路径（含 conf/、src/、frontend/ 的那一层）
    """
    env_root = str(os.getenv("KB_PROJECT_ROOT") or "").strip()
    if env_root:
        p = Path(env_root).expanduser().resolve()
        if p.exists():
            return p
    # src/shared/config_paths.py -> 上三级为仓库根
    return Path(__file__).resolve().parent.parent.parent


def _project_root_from_config_file(config_path: Path) -> Path | None:
    """若配置文件内声明了 KB_PROJECT_ROOT，则解析并返回。"""
    if not config_path.exists():
        return None
    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(cfg, dict):
        return None
    raw = str(cfg.get("KB_PROJECT_ROOT") or cfg.get("B_PROJECT_ROOT") or "").strip()
    if not raw:
        return None
    root = Path(raw)
    if not root.is_absolute():
        # conf/config.json 中的相对路径相对于仓库根（conf 的上一级），而非 conf/ 自身
        if config_path.parent.name == "conf":
            base = config_path.parent.parent
        else:
            base = config_path.parent
        root = (base / root).resolve()
    else:
        root = root.expanduser().resolve()
    return root if root.exists() else None


def resolve_project_root() -> Path:
    """
    解析项目根目录（环境变量 / 当前目录配置 / 包相对路径）。

    Returns:
        可用的项目根路径
    """
    env_root = str(os.getenv("KB_PROJECT_ROOT") or "").strip()
    if env_root:
        p = Path(env_root).expanduser().resolve()
        if p.exists():
            return p

    cwd = Path.cwd().resolve()
    for candidate in (cwd / "conf" / "config.json", cwd / "config.json"):
        cfg_root = _project_root_from_config_file(candidate)
        if cfg_root is not None:
            return cfg_root
    if (cwd / "conf" / "config.json").exists() or (cwd / "config.json").exists():
        return cwd

    root = project_root()
    for candidate in (root / "conf" / "config.json", root / "config.json"):
        cfg_root = _project_root_from_config_file(candidate)
        if cfg_root is not None:
            return cfg_root
    return root


def resolve_config_path(root: Path | None = None) -> Path | None:
    """
    解析主配置文件路径。

    优先级：
    1. 环境变量 KB_CONFIG_PATH
    2. {root}/conf/config.json
    3. {root}/config.json（兼容旧布局）

    Args:
        root: 项目根；为空则自动解析

    Returns:
        存在的配置文件路径；都不存在则返回 None
    """
    cfg_env = str(os.getenv("KB_CONFIG_PATH", "")).strip()
    if cfg_env:
        p = Path(cfg_env).expanduser().resolve()
        return p if p.exists() else None

    base = root if root is not None else resolve_project_root()
    conf_cfg = base / "conf" / "config.json"
    if conf_cfg.exists():
        return conf_cfg
    legacy = base / "config.json"
    if legacy.exists():
        return legacy
    return None


def _deep_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """递归合并字典，overlay 覆盖 base。"""
    result = dict(base)
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_project_config(root: Path | None = None) -> Dict[str, Any]:
    """
    加载项目配置（UTF-8 JSON）。

    在主配置基础上，若存在 conf/config.{KB_ENV}.json（如 dev/prod）则做浅层深合并覆盖。

    Args:
        root: 项目根；为空则自动解析

    Returns:
        配置字典；失败时返回空字典
    """
    base = root if root is not None else resolve_project_root()
    path = resolve_config_path(base)
    data: Dict[str, Any] = {}
    if path is not None:
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except Exception:
            data = {}

    env_name = str(os.getenv("KB_ENV", "")).strip().lower()
    if env_name:
        overlay_path = base / "conf" / f"config.{env_name}.json"
        if overlay_path.exists():
            try:
                overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
                if isinstance(overlay, dict):
                    data = _deep_merge(data, overlay)
            except Exception:
                pass
    return data
