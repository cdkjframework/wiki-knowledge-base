# 可选解析能力启用指南（Pix2Text / PDF Marker）

本项目主流程在可选组件不可用时会自动降级，不影响服务启动。
如果你希望启用图片 OCR（Pix2Text）和 PDF Marker，请按以下步骤操作。

## 1. 安装可选依赖

```powershell
pip install -r requirements.optional-parser.txt
```

说明：

- `optimum==2.1.0` 与当前项目保持一致；代码内已加入 `ORTModelForVision2Seq` 兼容补丁。
- `marker-pdf` 未默认启用，因不同环境对 torch/CUDA 要求差异较大。

## 2. 运行预检查与模型预热

```powershell
python download_optional_parser_models.py
```

脚本会输出：

- `PDF Marker` 是否可导入
- `Pix2Text` 是否可初始化
- 如果失败，会给出常见原因提示

## 3. 常见问题

### 3.1 日志提示“PDF Marker 不可用，回退到当前 PDF 解析器”

通常是未安装 `marker-pdf` 或其依赖不满足。

### 3.2 日志提示“Pix2Text 不可用，回退到当前图片解析器”

常见原因：

- 可选依赖未安装完整
- `torch` / `optimum` 版本不兼容
- Pix2Text 需要的布局模型未下载成功

### 3.3 不想启用可选能力

可忽略这些告警，系统会继续使用默认解析路径。
