# KWS 语音唤醒/声纹测试自动标注平台

这是一个面向语音算法测试流程的 Web 工具，用于管理音频测试任务、生成合成长音频、播放并标注坏例、管理测试数据集、导出测试结果，帮助提升语音唤醒和声纹测试的分析效率。

## 功能特点

- 音频任务上传：支持上传 WAV 文件或 ZIP 压缩包，自动提取音频并生成测试任务。
- 音频合成处理：支持统一采样率、声道、位深，并按固定间隔拼接音频，生成时间戳信息。
- 在线播放标注：提供任务播放页面，可定位音频片段并标注坏例。
- 坏例管理：支持新增、删除、备注坏例，并导出坏例 CSV。
- 环境信息维护：支持记录测试距离、角度、噪声等级等环境参数。
- 数据集管理：支持创建、查看、删除数据集，并分析音量最低的音频文件。
- 远程调试辅助：内置 SSH 连接接口，可用于远程设备命令交互。
- 报告导出：支持导出单个任务报告和坏例汇总报告。

## 技术栈

- Python
- FastAPI
- Uvicorn
- Jinja2 Templates
- pydub
- paramiko
- HTML / CSS / JavaScript

## 目录结构

```text
KWS_PROJ/
├── main.py              # FastAPI 后端主程序
├── run.py               # 本地启动入口，默认端口 8023
├── audio_processor.py   # 音频处理、任务管理、数据集管理工具函数
├── templates/           # 页面模板
├── static/              # 前端静态资源
├── tasks/               # 本地测试任务数据，仅保留 .gitkeep 到 Git
├── datasets/            # 本地数据集数据，仅保留 .gitkeep 到 Git
├── uploads/             # 上传和导出文件目录，不提交到 Git
└── requirements.txt     # 当前开发环境依赖导出
```

## 环境准备

建议使用 Python 3.10 或更新版本。

### 1. 进入项目目录

Git Bash：

```bash
cd /d/测试/语音测试/KWS_PROJ/KWS_PROJ
```

PowerShell：

```powershell
cd "D:\测试\语音测试\KWS_PROJ\KWS_PROJ"
```

### 2. 创建虚拟环境

```bash
python -m venv .venv
```

PowerShell 激活：

```powershell
.venv\Scripts\activate
```

Git Bash 激活：

```bash
source .venv/Scripts/activate
```

### 3. 安装核心依赖

```bash
pip install fastapi uvicorn python-multipart jinja2 pydub paramiko
```

如果需要按当前开发环境完整安装，也可以使用：

```bash
pip install -r requirements.txt
```

> 注意：`requirements.txt` 来自完整 Python 环境导出，内容较多。新环境部署时，优先安装核心依赖通常更轻量。

## 启动项目

```bash
python run.py
```

启动成功后，在浏览器打开：

```text
http://127.0.0.1:8023
```

如果需要局域网内其他设备访问，可以使用本机 IP 加端口访问，例如：

```text
http://本机IP:8023
```

## 基本使用流程

1. 打开首页，进入上传页面。
2. 上传 WAV 文件或包含 WAV 的 ZIP 压缩包。
3. 系统自动生成任务、合成长音频和片段时间戳。
4. 在播放页面检查音频片段，标注唤醒或声纹测试中的坏例。
5. 根据需要维护测试环境信息，例如距离、角度、噪声等级。
6. 在坏例页面或任务页面导出 CSV 报告。
7. 数据集页面可用于管理测试音频集合，并查看音量最低的文件。

## Git 使用说明

本仓库已经配置 `.gitignore`，默认不会提交以下本地运行数据和构建产物：

- `tasks/`
- `datasets/`
- `uploads/`
- `build/`
- `dist/`
- `.venv/`
- `__pycache__/`
- 日志文件

日常更新代码后，可以按下面流程提交：

```bash
git status
git add .
git commit -m "更新说明"
git push
```

提交前建议先看一下状态，确认没有误提交大文件：

```bash
git status
git diff --stat
```

## 注意事项

- Gitee 对单个文件大小有限制，音频、模型、压缩包、构建产物等大文件不要直接提交到 Git。
- `tasks/` 和 `datasets/` 中的数据会保留在本地，用于实际测试运行，但不会上传到远端仓库。
- 如果需要迁移测试数据，建议单独打包备份，或使用对象存储、网盘、专用数据管理系统保存。

## 适用场景

- 语音唤醒词测试
- 声纹测试结果分析
- 音频坏例标注
- 测试数据集整理
- 测试报告导出与归档
