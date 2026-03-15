# 自定义构建 FAISS GPU Wheel

本项目内置了两种 FAISS GPU wheel 工作流：

1. 单独构建自定义 FAISS GPU wheel。
2. 在生成部署包时顺带构建，并把 wheel 放进部署目录。

## 前置要求

- Git
- CMake
- Visual Studio C++ Build Tools 或 Developer PowerShell 环境
- Python 3.12+
- CUDA Toolkit 或 ROCm Toolkit

说明：

- 脚本使用官方 faiss-wheels 仓库作为构建源。
- GPU wheel 不从 PyPI 拉取，而是在本地构建。
- 默认包名会被改成 `faiss-gpu`，便于和 `faiss-cpu` 区分。

## 方式一：单独构建 GPU wheel

PowerShell：

```powershell
.\build_faiss_gpu_wheel.ps1 -GpuSupport CUDA
```

批处理：

```cmd
build_faiss_gpu_wheel.bat -GpuSupport CUDA
```

常用参数：

- `-GpuSupport CUDA|ROCM|CUVS`
- `-FaissOptLevels "generic,avx2"`
- `-OutputDir "./dist/faiss-gpu-wheel"`
- `-WorkDir "./build/faiss-wheels-src"`
- `-RepoRef "main"`
- `-Clean`

构建成功后，脚本会输出 wheel 的完整路径。

## 方式二：构建主项目部署包时一并带入

```powershell
.\build_wheel.ps1 -BuildCustomFaissGpuWheel -FaissGpuSupport CUDA
```

常用参数：

- `-BuildCustomFaissGpuWheel`
- `-FaissGpuSupport CUDA|ROCM|CUVS`
- `-FaissOptLevels "generic,avx2"`
- `-FaissWheelOutputDir "./dist/faiss-gpu-wheel"`
- `-FaissWheelWorkspace "./build/faiss-wheels-src"`
- `-FaissWheelRepoRef "main"`

如果你已经提前构建好了 wheel，也可以直接指定现成文件：

```powershell
.\build_wheel.ps1 -CustomFaissWheelPath .\dist\faiss-gpu-wheel\faiss_gpu-*.whl
```

## 部署目录中的安装方式

当部署包中包含自定义 FAISS wheel 时，会额外生成这些脚本：

- `install-gpu.ps1`
- `install-gpu.bat`
- `install-gpu.sh`

推荐直接使用：

```powershell
.\install-gpu.ps1
```

它会调用部署目录中的 `install.ps1`，并自动启用本地打包进去的 FAISS wheel。

如果需要手工指定 wheel 路径，也可以继续使用：

```powershell
.\install.ps1 -CustomFaissWheel .\faiss_gpu_custom.whl
```

## 注意事项

- 自定义 GPU wheel 需要与你的工具链和目标机器运行时匹配。
- CUDA wheel 并不保证可直接在不同 CUDA 版本之间通用。
- 如果部署机器没有匹配的 GPU 运行环境，请继续使用默认的 `faiss-cpu`。
- `build_wheel.ps1` 里的 `-BuildCustomFaissGpuWheel` 与 `-CustomFaissWheelPath` 不能同时使用。