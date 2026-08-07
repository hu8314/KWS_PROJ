# -*- coding: utf-8 -*-
"""KWS关键词唤醒测试工具 - FastAPI后端"""
import os
import sys
import json
import re
import shutil
import threading
import queue
import time
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

import paramiko

# PyInstaller 打包兼容：确保当前目录在 sys.path 中
if getattr(sys, 'frozen', False):
    # 运行在 PyInstaller 打包环境
    bundle_dir = os.path.dirname(sys.executable)
else:
    bundle_dir = os.path.dirname(os.path.abspath(__file__))
if bundle_dir not in sys.path:
    sys.path.insert(0, bundle_dir)

from fastapi import FastAPI, Request, File, UploadFile, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from audio_processor import (
    generate_task_id, extract_zip, list_wav_files, create_task,
    load_task_config, load_timestamps, load_badcases, add_badcase,
    delete_badcase, clear_badcases, update_badcase_note, update_task_environment, update_task_name,
    delete_task, get_all_tasks, export_badcases_to_csv,
    create_dataset, load_dataset_meta, delete_dataset,
    get_all_datasets, get_dataset_file_paths,
    find_lowest_volume_files,
    export_task_report_to_csv
)

# ========== 配置 ==========
BASE_DIR = Path(__file__).parent
TASKS_DIR = BASE_DIR / "tasks"
UPLOADS_DIR = BASE_DIR / "uploads"
DATASETS_DIR = BASE_DIR / "datasets"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

TASKS_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(exist_ok=True)
DATASETS_DIR.mkdir(exist_ok=True)

# 环境参数默认值
DEFAULT_DISTANCES = ["1m", "3m", "5m"]
DEFAULT_ANGLES = ["90°", "45°", "180°", "270°"]
DEFAULT_NOISE_LEVELS = ["安静40db", "中低噪48db", "中高噪56db"]
TASK_TYPES = {"wake", "voiceprint", "oenshot"}

# ========== SSH会话管理 ==========
class SSHSession:
    def __init__(self):
        self.client = None
        self.shell = None
        self.connected = False
        self.host = ""
        self.output_queue = queue.Queue()
        self.thread = None
        self.lock = threading.Lock()

    def connect(self, host: str, port: int, username: str, password: str) -> bool:
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(host, port=port, username=username, password=password, timeout=10, banner_timeout=15)
        self.connected = True
        self.host = host
        self.shell = self.client.invoke_shell(term='xterm', width=120, height=30)
        self.shell.settimeout(0.1)
        self.thread = threading.Thread(target=self._read_output, daemon=True)
        self.thread.start()
        return True

    def _read_output(self):
        while self.connected and self.shell:
            try:
                if self.shell.recv_ready():
                    data = self.shell.recv(4096).decode('utf-8', errors='replace')
                    self.output_queue.put(data)
                else:
                    time.sleep(0.05)
            except Exception:
                break
        self.connected = False

    def send_command(self, cmd: str):
        if self.shell:
            self.shell.send(cmd + '\n')

    def get_output(self) -> str:
        lines = []
        while not self.output_queue.empty():
            try:
                lines.append(self.output_queue.get_nowait())
            except queue.Empty:
                break
        return ''.join(lines)

    def disconnect(self):
        self.connected = False
        if self.shell:
            try:
                self.shell.close()
            except Exception:
                pass
            self.shell = None
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None


ssh_sessions: Dict[str, SSHSession] = {}

# ========== FastAPI应用 ==========
app = FastAPI(title="KWS关键词唤醒测试工具", version="1.0.0")

# 挂载静态文件
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# 模板引擎
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.auto_reload = True
templates.env.cache = {}


def sanitize_download_filename(name: str, fallback: str = "download") -> str:
    """清理下载文件名，避免 Windows 非法字符。"""
    raw = str(name or "").strip()
    if not raw:
        raw = fallback
    sanitized = re.sub(r'[<>:"/\\\\|?*]+', "_", raw)
    sanitized = sanitized.strip().strip(".")
    return sanitized or fallback


# ========== 页面路由 ==========
# 页面模板修改后依赖运行中的热重载重新读取
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """首页 - 历史任务列表"""
    tasks = get_all_tasks(str(TASKS_DIR))
    return templates.TemplateResponse(request, "index.html", {
        "tasks": tasks,
        "distances": DEFAULT_DISTANCES,
        "angles": DEFAULT_ANGLES,
        "noise_levels": DEFAULT_NOISE_LEVELS
    })


@app.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request):
    """上传页面"""
    return templates.TemplateResponse(request, "upload.html", {
        "distances": DEFAULT_DISTANCES,
        "angles": DEFAULT_ANGLES,
        "noise_levels": DEFAULT_NOISE_LEVELS
    })


@app.get("/player/{task_id}", response_class=HTMLResponse)
async def player_page(request: Request, task_id: str):
    """播放页面"""
    task_dir = str(TASKS_DIR / task_id)
    config = load_task_config(task_dir)
    if not config:
        return templates.TemplateResponse(request, "player_empty.html", {
            "task_id": task_id
        }, status_code=404)
    config["task_type"] = config.get("task_type", "wake")
    
    timestamps = load_timestamps(task_dir)
    badcases = load_badcases(task_dir)
    
    return templates.TemplateResponse(request, "player.html", {
        "task": config,
        "timestamps": timestamps,
        "badcases": badcases
    })


@app.get("/datasets", response_class=HTMLResponse)
async def datasets_page(request: Request):
    """音频数据集管理页面"""
    datasets = get_all_datasets(str(DATASETS_DIR))
    return templates.TemplateResponse(request, "datasets.html", {
        "datasets": datasets,
        "distances": DEFAULT_DISTANCES,
        "angles": DEFAULT_ANGLES,
        "noise_levels": DEFAULT_NOISE_LEVELS
    })


@app.get("/badcases", response_class=HTMLResponse)
async def badcases_page(request: Request):
    """badcase管理页面"""
    all_badcases = []
    tasks = get_all_tasks(str(TASKS_DIR))
    badcase_groups = []
    for task in tasks:
        task_dir = str(TASKS_DIR / task["task_id"])
        task_badcases = load_badcases(task_dir)
        if not task_badcases:
            continue

        items = []
        for badcase in task_badcases:
            item = dict(badcase)
            item["task_id"] = task["task_id"]
            item["task_name"] = task["task_name"]
            item["task_type"] = task.get("task_type", "wake")
            item["selected_key"] = f"{task['task_id']}:{badcase.get('id', '')}"
            items.append(item)
            all_badcases.append(item)

        items.sort(key=lambda x: (float(x.get("start_time", 0) or 0), int(x.get("id", 0) or 0)))
        badcase_groups.append({
            "task_id": task["task_id"],
            "task_name": task["task_name"],
            "task_type": task.get("task_type", "wake"),
            "create_time": task.get("create_time", ""),
            "environment": task.get("environment", {}),
            "total_files": task.get("total_files", 0),
            "badcase_items": items
        })

    all_badcases.sort(key=lambda x: x.get("mark_time", ""), reverse=True)
    
    return templates.TemplateResponse(request, "badcases.html", {
        "badcases": all_badcases,
        "badcase_groups": badcase_groups,
        "distances": DEFAULT_DISTANCES,
        "angles": DEFAULT_ANGLES,
        "noise_levels": DEFAULT_NOISE_LEVELS
    })


# ========== API路由 ==========
@app.post("/api/upload")
async def upload_files(
    task_name: str = Form(""),
    task_type: str = Form("wake"),
    voiceprint_in_count: int = Form(10),
    voiceprint_out_count: int = Form(10),
    silence_duration: int = Form(3),
    sample_rate: int = Form(16000),
    bit_depth: int = Form(16),
    channels: int = Form(1),
    distance: str = Form("3m"),
    angle: str = Form("90°"),
    noise_level: str = Form("安静40db"),
    files: List[UploadFile] = File(...)
):
    """上传并合成音频"""
    if task_type not in TASK_TYPES:
        task_type = "wake"
    voiceprint_in_count = max(0, voiceprint_in_count)
    voiceprint_out_count = max(0, voiceprint_out_count)

    if not task_name:
        task_name = f"测试任务_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    task_id = generate_task_id()
    task_dir = str(TASKS_DIR / task_id)
    temp_dir = str(UPLOADS_DIR / task_id)
    os.makedirs(temp_dir, exist_ok=True)
    
    try:
        wav_files = []
        
        for upload_file in files:
            file_path = os.path.join(temp_dir, upload_file.filename)
            with open(file_path, "wb") as f:
                shutil.copyfileobj(upload_file.file, f)
            
            # 如果是ZIP文件，解压
            if upload_file.filename.lower().endswith('.zip'):
                extract_dir = os.path.join(temp_dir, "extracted")
                extracted = extract_zip(file_path, extract_dir)
                wav_files.extend(extracted)
            elif upload_file.filename.lower().endswith('.wav'):
                wav_files.append(file_path)
        
        if not wav_files:
            # 清理
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise HTTPException(status_code=400, detail="未找到有效的WAV音频文件")
        
        # 去重并排序（按原始文件名）
        seen = set()
        unique_files = []
        for f in wav_files:
            basename = os.path.basename(f)
            if basename not in seen:
                seen.add(basename)
                unique_files.append(f)
        
        # 按文件名排序
        unique_files.sort(key=lambda x: os.path.basename(x))
        
        environment = {
            "distance": distance,
            "angle": angle,
            "noise_level": noise_level
        }
        
        config = create_task(
            task_name=task_name,
            file_paths=unique_files,
            task_dir=task_dir,
            silence_duration=silence_duration,
            sample_rate=sample_rate,
            bit_depth=bit_depth,
            channels=channels,
            environment=environment,
            task_type=task_type,
            voiceprint_in_count=voiceprint_in_count,
            voiceprint_out_count=voiceprint_out_count
        )
        
        # 清理上传临时目录
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        return JSONResponse(content={
            "success": True,
            "task_id": task_id,
            "task": config
        })
        
    except Exception as e:
        # 清理
        shutil.rmtree(temp_dir, ignore_errors=True)
        shutil.rmtree(task_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"合成失败: {str(e)}")


@app.get("/api/tasks")
async def api_tasks():
    """获取所有任务列表"""
    tasks = get_all_tasks(str(TASKS_DIR))
    return JSONResponse(content={"tasks": tasks})


@app.get("/api/tasks/{task_id}")
async def api_task_detail(task_id: str):
    """获取任务详情"""
    task_dir = str(TASKS_DIR / task_id)
    config = load_task_config(task_dir)
    if not config:
        raise HTTPException(status_code=404, detail="任务不存在")
    config["task_type"] = config.get("task_type", "wake")
    
    timestamps = load_timestamps(task_dir)
    badcases = load_badcases(task_dir)
    
    return JSONResponse(content={
        "task": config,
        "timestamps": timestamps,
        "badcases": badcases
    })


@app.get("/api/tasks/{task_id}/audio")
async def api_task_audio(task_id: str):
    """获取任务音频文件"""
    task_dir = str(TASKS_DIR / task_id)
    audio_path = os.path.join(task_dir, "audio.wav")
    if not os.path.exists(audio_path):
        raise HTTPException(status_code=404, detail="音频文件不存在")
    return FileResponse(audio_path, media_type="audio/wav", filename="audio.wav")


@app.post("/api/tasks/{task_id}/badcases")
async def api_add_badcase(
    task_id: str,
    filename: str = Form(...),
    start_time: float = Form(...),
    end_time: float = Form(...),
    error_type: str = Form(""),
    note: str = Form("")
):
    """添加badcase"""
    task_dir = str(TASKS_DIR / task_id)
    config = load_task_config(task_dir)
    if not config:
        raise HTTPException(status_code=404, detail="任务不存在")
    config["task_type"] = config.get("task_type", "wake")

    task_type = config.get("task_type", "wake")
    if task_type == "voiceprint":
        error_type = error_type.upper()
        if error_type not in {"FP", "FN"}:
            raise HTTPException(status_code=400, detail="声纹识别任务必须选择 FP 或 FN")
    else:
        error_type = ""
    
    badcase = add_badcase(
        task_dir=task_dir,
        filename=filename,
        start_time=start_time,
        end_time=end_time,
        note=note,
        environment=config.get("environment", {}),
        error_type=error_type
    )
    
    return JSONResponse(content={"success": True, "badcase": badcase})


@app.delete("/api/tasks/{task_id}/badcases/{badcase_id}")
async def api_delete_badcase(task_id: str, badcase_id: int):
    """删除badcase"""
    task_dir = str(TASKS_DIR / task_id)
    if delete_badcase(task_dir, badcase_id):
        return JSONResponse(content={"success": True})
    raise HTTPException(status_code=404, detail="badcase不存在")


@app.delete("/api/tasks/{task_id}/badcases")
async def api_clear_badcases(task_id: str):
    """清空当前任务的全部badcase"""
    task_dir = str(TASKS_DIR / task_id)
    if not load_task_config(task_dir):
        raise HTTPException(status_code=404, detail="任务不存在")
    deleted_count = clear_badcases(task_dir)
    return JSONResponse(content={"success": True, "deleted_count": deleted_count})


@app.put("/api/tasks/{task_id}/badcases/{badcase_id}")
async def api_update_badcase(task_id: str, badcase_id: int, note: str = Form(...)):
    """更新badcase备注"""
    task_dir = str(TASKS_DIR / task_id)
    if update_badcase_note(task_dir, badcase_id, note):
        return JSONResponse(content={"success": True})
    raise HTTPException(status_code=404, detail="badcase不存在")


@app.put("/api/tasks/{task_id}/environment")
async def api_update_environment(task_id: str, request: Request):
    """更新任务环境参数"""
    task_dir = str(TASKS_DIR / task_id)
    data = await request.json()
    environment = data.get("environment", {})
    if update_task_environment(task_dir, environment):
        return JSONResponse(content={"success": True})
    raise HTTPException(status_code=404, detail="任务不存在")


@app.delete("/api/tasks/{task_id}")
async def api_delete_task(task_id: str):
    """删除任务"""
    task_dir = str(TASKS_DIR / task_id)
    if delete_task(task_dir):
        return JSONResponse(content={"success": True})
    raise HTTPException(status_code=404, detail="任务不存在")


# ========== 数据集 API ==========
@app.put("/api/tasks/{task_id}/name")
async def api_update_task_name(task_id: str, request: Request):
    """Update task name."""
    task_dir = str(TASKS_DIR / task_id)
    data = await request.json()
    task_name = str(data.get("task_name", "")).strip()
    if not task_name:
        raise HTTPException(status_code=400, detail="????????")
    if update_task_name(task_dir, task_name):
        return JSONResponse(content={"success": True, "task_name": task_name})
    raise HTTPException(status_code=404, detail="?????")


@app.post("/api/datasets")
async def api_create_dataset(
    dataset_name: str = Form(""),
    files: List[UploadFile] = File(...)
):
    """上传并创建音频数据集"""
    if not dataset_name:
        dataset_name = f"数据集_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    temp_dir = str(UPLOADS_DIR / f"dataset_tmp_{datetime.now().strftime('%Y%m%d%H%M%S')}")
    os.makedirs(temp_dir, exist_ok=True)
    
    try:
        wav_files = []
        
        for upload_file in files:
            file_path = os.path.join(temp_dir, upload_file.filename)
            with open(file_path, "wb") as f:
                shutil.copyfileobj(upload_file.file, f)
            
            if upload_file.filename.lower().endswith('.zip'):
                extract_dir = os.path.join(temp_dir, "extracted")
                extracted = extract_zip(file_path, extract_dir)
                wav_files.extend(extracted)
            elif upload_file.filename.lower().endswith('.wav'):
                wav_files.append(file_path)
        
        if not wav_files:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise HTTPException(status_code=400, detail="未找到有效的WAV音频文件")
        
        # 去重并排序
        seen = set()
        unique_files = []
        for f in wav_files:
            basename = os.path.basename(f)
            if basename not in seen:
                seen.add(basename)
                unique_files.append(f)
        unique_files.sort(key=lambda x: os.path.basename(x))
        
        meta = create_dataset(
            dataset_name=dataset_name,
            file_paths=unique_files,
            datasets_dir=str(DATASETS_DIR)
        )
        
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        return JSONResponse(content={"success": True, "dataset": meta})
        
    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"创建数据集失败: {str(e)}")


@app.get("/api/datasets")
async def api_datasets():
    """获取所有数据集列表"""
    datasets = get_all_datasets(str(DATASETS_DIR))
    return JSONResponse(content={"datasets": datasets})


@app.get("/api/datasets/{dataset_id}")
async def api_dataset_detail(dataset_id: str):
    """获取数据集详情"""
    dataset_dir = str(DATASETS_DIR / dataset_id)
    meta = load_dataset_meta(dataset_dir)
    if not meta:
        raise HTTPException(status_code=404, detail="数据集不存在")
    
    file_paths = get_dataset_file_paths(dataset_dir)
    return JSONResponse(content={
        "dataset": meta,
        "file_paths": file_paths
    })


@app.get("/api/datasets/{dataset_id}/lowest-volume")
async def api_dataset_lowest_volume(dataset_id: str, limit: int = Query(20, ge=1, le=200)):
    """获取数据集中音量最低的WAV文件"""
    dataset_dir = str(DATASETS_DIR / dataset_id)
    meta = load_dataset_meta(dataset_dir)
    if not meta:
        raise HTTPException(status_code=404, detail="数据集不存在")

    results = find_lowest_volume_files(dataset_dir, limit=limit)
    return JSONResponse(content={
        "success": True,
        "dataset": meta,
        "results": results
    })


@app.get("/api/datasets/{dataset_id}/audio/{filename}")
async def api_dataset_audio_file(dataset_id: str, filename: str):
    """播放数据集中的单个WAV文件"""
    dataset_dir = DATASETS_DIR / dataset_id
    meta = load_dataset_meta(str(dataset_dir))
    if not meta:
        raise HTTPException(status_code=404, detail="数据集不存在")

    safe_filename = os.path.basename(filename)
    audio_path = dataset_dir / "files" / safe_filename
    if not audio_path.exists() or not audio_path.is_file() or audio_path.suffix.lower() != ".wav":
        raise HTTPException(status_code=404, detail="音频文件不存在")

    return FileResponse(str(audio_path), media_type="audio/wav", filename=safe_filename)


@app.delete("/api/datasets/{dataset_id}")
async def api_delete_dataset(dataset_id: str):
    """删除数据集"""
    dataset_dir = str(DATASETS_DIR / dataset_id)
    if delete_dataset(dataset_dir):
        return JSONResponse(content={"success": True})
    raise HTTPException(status_code=404, detail="数据集不存在")


# ========== 基于数据集创建任务 API ==========
@app.post("/api/tasks/from-dataset")
async def api_create_task_from_dataset(
    dataset_id: str = Form(...),
    task_name: str = Form(""),
    task_type: str = Form("wake"),
    voiceprint_in_count: int = Form(10),
    voiceprint_out_count: int = Form(10),
    silence_duration: int = Form(3),
    sample_rate: int = Form(16000),
    bit_depth: int = Form(16),
    channels: int = Form(1),
    distance: str = Form("3m"),
    angle: str = Form("90°"),
    noise_level: str = Form("安静40db")
):
    """基于已有数据集创建合成任务（可更换测试环境）"""
    if task_type not in TASK_TYPES:
        task_type = "wake"
    voiceprint_in_count = max(0, voiceprint_in_count)
    voiceprint_out_count = max(0, voiceprint_out_count)

    dataset_dir = str(DATASETS_DIR / dataset_id)
    meta = load_dataset_meta(dataset_dir)
    if not meta:
        raise HTTPException(status_code=404, detail="数据集不存在")
    
    file_paths = get_dataset_file_paths(dataset_dir)
    if not file_paths:
        raise HTTPException(status_code=400, detail="数据集内没有有效的WAV文件")
    
    if not task_name:
        task_name = f"{meta['dataset_name']}_{distance}_{angle}_{noise_level}"
    
    task_id = generate_task_id()
    task_dir = str(TASKS_DIR / task_id)
    
    try:
        environment = {
            "distance": distance,
            "angle": angle,
            "noise_level": noise_level
        }
        
        config = create_task(
            task_name=task_name,
            file_paths=file_paths,
            task_dir=task_dir,
            silence_duration=silence_duration,
            sample_rate=sample_rate,
            bit_depth=bit_depth,
            channels=channels,
            environment=environment,
            source_dataset_id=dataset_id,
            task_type=task_type,
            voiceprint_in_count=voiceprint_in_count,
            voiceprint_out_count=voiceprint_out_count
        )
        
        return JSONResponse(content={
            "success": True,
            "task_id": task_id,
            "task": config
        })
        
    except Exception as e:
        shutil.rmtree(task_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"合成失败: {str(e)}")


# ========== SSH API ==========
@app.post("/api/ssh/connect")
async def api_ssh_connect(
    task_id: str = Form(...),
    host: str = Form(...),
    port: int = Form(22),
    username: str = Form(...),
    password: str = Form(...)
):
    """建立SSH连接"""
    session = SSHSession()
    try:
        session.connect(host, port, username, password)
        if task_id in ssh_sessions:
            ssh_sessions[task_id].disconnect()
        ssh_sessions[task_id] = session
        return JSONResponse(content={"success": True, "message": f"已连接到 {host}"})
    except Exception as e:
        return JSONResponse(content={"success": False, "message": str(e)}, status_code=400)


@app.post("/api/ssh/disconnect")
async def api_ssh_disconnect(task_id: str = Form(...)):
    """断开SSH连接"""
    if task_id in ssh_sessions:
        ssh_sessions[task_id].disconnect()
        del ssh_sessions[task_id]
    return JSONResponse(content={"success": True})


@app.get("/api/ssh/output")
async def api_ssh_output(task_id: str):
    """获取SSH输出"""
    if task_id not in ssh_sessions:
        return JSONResponse(content={"success": False, "output": "", "connected": False})
    session = ssh_sessions[task_id]
    output = session.get_output()
    return JSONResponse(content={
        "success": True,
        "output": output,
        "connected": session.connected,
        "host": session.host
    })


@app.post("/api/ssh/send")
async def api_ssh_send(task_id: str = Form(...), command: str = Form(...)):
    """发送SSH命令"""
    if task_id not in ssh_sessions:
        return JSONResponse(content={"success": False, "message": "未连接"})
    ssh_sessions[task_id].send_command(command)
    return JSONResponse(content={"success": True})


# ========== 任务报告导出 ==========
@app.get("/api/tasks/{task_id}/export")
async def api_export_task_report(task_id: str):
    """导出任务完整测试报告（含唤醒率、环境、badcase、备注）"""
    task_dir = str(TASKS_DIR / task_id)
    config = load_task_config(task_dir)
    if not config:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    timestamps = load_timestamps(task_dir)
    badcases = load_badcases(task_dir)
    
    export_path = str(UPLOADS_DIR / f"task_report_{task_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
    export_task_report_to_csv(config, timestamps, badcases, export_path)

    download_name = sanitize_download_filename(config.get("task_name", task_id), fallback=task_id)
    return FileResponse(export_path, media_type="text/csv", filename=f"{download_name}.csv")


@app.get("/api/export/badcases")
async def api_export_badcases(
    task_id: Optional[str] = Query(None),
    task_type: Optional[str] = Query(None),
    distance: Optional[str] = Query(None),
    angle: Optional[str] = Query(None),
    noise_level: Optional[str] = Query(None),
    selected: Optional[List[str]] = Query(None)
):
    """导出badcase为CSV"""
    all_badcases = []
    task_name_map = {}
    selected_keys = {value for value in (selected or []) if value}
    tasks = get_all_tasks(str(TASKS_DIR))
    task_configs = {task["task_id"]: task for task in tasks}

    iterable_tasks = [task_configs[task_id]] if task_id and task_id in task_configs else tasks
    for task in iterable_tasks:
        tid = task["task_id"]
        task_dir = str(TASKS_DIR / tid)
        badcases = load_badcases(task_dir)
        for badcase in badcases:
            item = dict(badcase)
            item["task_id"] = tid
            item["task_name"] = task["task_name"]
            item["task_type"] = task.get("task_type", "wake")
            item["selected_key"] = f"{tid}:{badcase.get('id', '')}"
            all_badcases.append(item)
        task_name_map[tid] = task["task_name"]
    
    # 筛选
    if task_type:
        all_badcases = [b for b in all_badcases if b.get("task_type", "wake") == task_type]
    if distance:
        all_badcases = [b for b in all_badcases if b.get("environment", {}).get("distance") == distance]
    if angle:
        all_badcases = [b for b in all_badcases if b.get("environment", {}).get("angle") == angle]
    if noise_level:
        all_badcases = [b for b in all_badcases if b.get("environment", {}).get("noise_level") == noise_level]
    if selected_keys:
        all_badcases = [b for b in all_badcases if b.get("selected_key") in selected_keys]

    export_path = str(UPLOADS_DIR / f"badcases_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")

    selected_task_ids = {str(b.get("task_id", "")) for b in all_badcases if b.get("task_id")}
    if len(selected_task_ids) == 1:
        task_name = task_name_map.get(next(iter(selected_task_ids)), "badcases")
    elif selected_keys:
        task_name = "selected_badcases"
    else:
        task_name = "all_badcases"

    export_badcases_to_csv(all_badcases, export_path, task_name, task_configs=task_configs)

    download_name = sanitize_download_filename(task_name, fallback="badcases")
    return FileResponse(export_path, media_type="text/csv", filename=f"{download_name}.csv")


# ========== 启动入口 ==========
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8023, reload=True)
