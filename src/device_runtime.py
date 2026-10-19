"""
推理设备解析：cpu / cuda / rocm / directml / auto。

DirectML（Windows iGPU，如 Radeon 890M）依赖可选包 torch-directml。
该包装死旧版 torch（约 2.4.x），与主环境 torch>=2.7 冲突，建议用独立 venv：
  python -m venv .venv-dml
  .venv-dml\\Scripts\\pip install -r requirements.directml.txt
"""

from __future__ import annotations

import logging
from typing import Any, Tuple

logger = logging.getLogger(__name__)


def probe_directml() -> Tuple[bool, str, Any | None]:
    """
    返回 (可用?, 说明, device 对象或 None)。
    device 对象可直接传给 Tensor.to / Module.to。
    """
    try:
        import torch_directml  # type: ignore
    except ImportError:
        return False, "未安装 torch-directml（见 requirements.directml.txt）", None
    try:
        device = torch_directml.device()
        # 冒烟：能搬一张张量才算真可用
        import torch

        x = torch.ones(1, dtype=torch.float32).to(device)
        _ = (x + x).to("cpu")
        name = ""
        try:
            name = str(torch_directml.device_name(0))
        except Exception:
            name = "DirectML"
        return True, f"DirectML 可用：{name}", device
    except Exception as exc:
        return False, f"torch-directml 已装但不可用：{exc}", None


def probe_onnxruntime_dml() -> Tuple[bool, str]:
    """探测 onnxruntime-directml 是否暴露 DmlExecutionProvider（不替代 HF 主路径）。"""
    try:
        import onnxruntime as ort
    except ImportError:
        return False, "未安装 onnxruntime / onnxruntime-directml"
    providers = list(ort.get_available_providers() or [])
    if "DmlExecutionProvider" in providers:
        return True, f"ORT providers={providers}"
    return False, f"ORT 无 DML：providers={providers}"


def resolve_torch_device(requested: str | None = "auto") -> Tuple[str, Any]:
    """
    解析配置中的 device 字段。

    返回 (标签, torch 可用的 device 字符串或 DirectML device 对象)。
    标签用于日志 / 状态展示：cuda|cpu|directml|…
    """
    import torch

    req = (requested or "auto").strip().lower()

    def _has_rocm() -> bool:
        try:
            return bool(getattr(torch.version, "hip", None))
        except Exception:
            return False

    rocm = _has_rocm() and torch.cuda.is_available()
    cuda = torch.cuda.is_available() and not rocm

    if req in {"directml", "dml"}:
        ok, msg, dml_dev = probe_directml()
        if not ok or dml_dev is None:
            raise RuntimeError(f"device=directml 不可用：{msg}")
        logger.info("Inference device: directml (%s)", msg)
        return "directml", dml_dev

    if req == "cuda":
        if not (cuda or rocm):
            raise RuntimeError("device=cuda 但当前 torch 无可用 CUDA/ROCm")
        return "cuda", "cuda"

    if req == "cpu":
        return "cpu", "cpu"

    if req == "auto":
        # 优先独显/ROCm，再试 DirectML iGPU，最后 CPU
        if cuda or rocm:
            logger.info("Inference device auto → cuda (rocm=%s)", rocm)
            return "cuda", "cuda"
        ok, msg, dml_dev = probe_directml()
        if ok and dml_dev is not None:
            logger.info("Inference device auto → directml (%s)", msg)
            return "directml", dml_dev
        ort_ok, ort_msg = probe_onnxruntime_dml()
        if ort_ok:
            logger.info(
                "ORT DirectML 可用但主路径仍用 CPU（未装 torch-directml）。%s "
                "可用独立环境：pip install -r requirements.directml.txt",
                ort_msg,
            )
        logger.info("Inference device auto → cpu")
        return "cpu", "cpu"

    # 透传其它字符串（如 cuda:0）
    return req, req
