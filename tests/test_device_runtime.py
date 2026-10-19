"""设备解析单测（不依赖 torch-directml）。"""

from __future__ import annotations

import unittest


class DeviceRuntimeTests(unittest.TestCase):
    def test_resolve_cpu(self) -> None:
        from src.device_runtime import resolve_torch_device

        label, dev = resolve_torch_device("cpu")
        self.assertEqual(label, "cpu")
        self.assertEqual(dev, "cpu")

    def test_probe_ort_or_skip(self) -> None:
        from src.device_runtime import probe_onnxruntime_dml

        ok, msg = probe_onnxruntime_dml()
        self.assertIsInstance(ok, bool)
        self.assertTrue(msg)

    def test_directml_explicit_without_pkg(self) -> None:
        from src.device_runtime import probe_directml

        ok, msg, dev = probe_directml()
        # 主环境通常未装 torch-directml
        if not ok:
            self.assertIsNone(dev)
            self.assertIn("torch-directml", msg.lower())


if __name__ == "__main__":
    unittest.main()
