# -*- coding: utf-8 -*-
"""KWS音频处理模块 - 负责音频合成、格式转换和时间戳生成"""
import os
import json
import zipfile
import shutil
import math
import wave
import audioop
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from pydub import AudioSegment


def generate_task_id() -> str:
    """生成任务ID"""
    return datetime.now().strftime("task_%Y%m%d_%H%M%S")


def extract_zip(zip_path: str, extract_to: str) -> List[str]:
    """解压ZIP文件，返回所有WAV文件路径列表"""
    wav_files = []
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(extract_to)
    
    # 递归查找所有wav文件并按文件名排序
    for root, dirs, files in os.walk(extract_to):
        for f in sorted(files):
            if f.lower().endswith('.wav'):
                wav_files.append(os.path.join(root, f))
    
    return wav_files


def list_wav_files(directory: str) -> List[str]:
    """列出目录下所有WAV文件"""
    wav_files = []
    for f in sorted(os.listdir(directory)):
        if f.lower().endswith('.wav'):
            wav_files.append(os.path.join(directory, f))
    return wav_files


def convert_audio(audio: AudioSegment, 
                  target_sample_rate: int = 16000,
                  target_channels: int = 1,
                  target_bit_depth: int = 16) -> AudioSegment:
    """将音频转换为目标格式"""
    # 设置声道数
    if audio.channels != target_channels:
        audio = audio.set_channels(target_channels)
    
    # 设置采样率
    if audio.frame_rate != target_sample_rate:
        audio = audio.set_frame_rate(target_sample_rate)
    
    # 设置采样宽度(bit depth)
    target_sample_width = target_bit_depth // 8
    if audio.sample_width != target_sample_width:
        audio = audio.set_sample_width(target_sample_width)
    
    return audio


def merge_audio_files(file_list: List[str],
                      silence_duration_ms: int = 3000,
                      target_sample_rate: int = 16000,
                      target_channels: int = 1,
                      target_bit_depth: int = 16) -> Tuple[AudioSegment, List[Dict[str, Any]]]:
    """
    合并多个音频文件，中间插入静音
    
    Returns:
        merged_audio: 合成后的音频
        timestamps: 每个音频片段的时间戳日志
    """
    merged = AudioSegment.empty()
    timestamps = []
    current_time_ms = 0
    silence = AudioSegment.silent(duration=silence_duration_ms)
    
    for idx, filepath in enumerate(file_list):
        try:
            audio = AudioSegment.from_wav(filepath)
        except Exception:
            # 尝试其他格式
            try:
                audio = AudioSegment.from_file(filepath)
            except Exception as e:
                print(f"无法读取文件 {filepath}: {e}")
                continue
        
        # 转换格式
        audio = convert_audio(audio, target_sample_rate, target_channels, target_bit_depth)
        
        duration_ms = len(audio)
        
        # 如果不是第一个文件，先加静音
        if idx > 0:
            merged += silence
            current_time_ms += silence_duration_ms
        
        start_ms = current_time_ms
        merged += audio
        current_time_ms += duration_ms
        end_ms = current_time_ms
        
        timestamps.append({
            "index": idx + 1,
            "filename": os.path.basename(filepath),
            "filepath": filepath,
            "start_time": round(start_ms / 1000.0, 3),
            "end_time": round(end_ms / 1000.0, 3),
            "duration": round(duration_ms / 1000.0, 3)
        })
    
    return merged, timestamps


def create_task(task_name: str,
                file_paths: List[str],
                task_dir: str,
                silence_duration: int = 3,
                sample_rate: int = 16000,
                bit_depth: int = 16,
                channels: int = 1,
                environment: Optional[Dict[str, str]] = None,
                source_dataset_id: Optional[str] = None,
                task_type: str = "wake",
                voiceprint_in_count: int = 10,
                voiceprint_out_count: int = 10) -> Dict[str, Any]:
    """
    创建合成任务
    
    Args:
        task_name: 任务名称
        file_paths: 待合成的音频文件路径列表
        task_dir: 任务存储目录
        silence_duration: 音频间隔时间(秒)
        sample_rate: 采样率
        bit_depth: 位深
        channels: 声道数
        environment: 环境参数字典
        voiceprint_in_count: 声纹库内音频条数
        voiceprint_out_count: 声纹库外音频条数
    
    Returns:
        task_info: 任务信息字典
    """
    os.makedirs(task_dir, exist_ok=True)
    
    task_id = os.path.basename(task_dir)
    create_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 合成音频
    merged_audio, timestamps = merge_audio_files(
        file_paths,
        silence_duration_ms=silence_duration * 1000,
        target_sample_rate=sample_rate,
        target_channels=channels,
        target_bit_depth=bit_depth
    )
    
    total_duration = len(merged_audio) / 1000.0
    
    # 保存合成后的音频
    output_audio_path = os.path.join(task_dir, "audio.wav")
    merged_audio.export(output_audio_path, format="wav")
    
    # 保存时间戳日志
    log_path = os.path.join(task_dir, "log.json")
    with open(log_path, 'w', encoding='utf-8') as f:
        json.dump(timestamps, f, ensure_ascii=False, indent=2)
    
    # 保存任务配置
    config = {
        "task_id": task_id,
        "task_name": task_name,
        "create_time": create_time,
        "silence_duration": silence_duration,
        "sample_rate": sample_rate,
        "bit_depth": bit_depth,
        "channels": channels,
        "environment": environment or {"distance": "3m", "angle": "90°", "noise_level": "安静40db"},
        "task_type": task_type,
        "voiceprint_in_count": max(0, int(voiceprint_in_count or 0)),
        "voiceprint_out_count": max(0, int(voiceprint_out_count or 0)),
        "total_files": len(timestamps),
        "total_duration": round(total_duration, 3),
        "audio_file": "audio.wav",
        "log_file": "log.json",
        "badcases_file": "badcases.json",
        "source_dataset_id": source_dataset_id
    }
    
    config_path = os.path.join(task_dir, "config.json")
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    
    # 初始化badcases文件
    badcases_path = os.path.join(task_dir, "badcases.json")
    with open(badcases_path, 'w', encoding='utf-8') as f:
        json.dump([], f, ensure_ascii=False, indent=2)
    
    return config


def load_task_config(task_dir: str) -> Optional[Dict[str, Any]]:
    """加载任务配置"""
    config_path = os.path.join(task_dir, "config.json")
    if not os.path.exists(config_path):
        return None
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_timestamps(task_dir: str) -> List[Dict[str, Any]]:
    """加载时间戳日志"""
    log_path = os.path.join(task_dir, "log.json")
    if not os.path.exists(log_path):
        return []
    with open(log_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_badcases(task_dir: str) -> List[Dict[str, Any]]:
    """加载badcase记录"""
    badcases_path = os.path.join(task_dir, "badcases.json")
    if not os.path.exists(badcases_path):
        return []
    with open(badcases_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_badcases(task_dir: str, badcases: List[Dict[str, Any]]) -> None:
    """保存badcase记录"""
    badcases_path = os.path.join(task_dir, "badcases.json")
    with open(badcases_path, 'w', encoding='utf-8') as f:
        json.dump(badcases, f, ensure_ascii=False, indent=2)


def add_badcase(task_dir: str, 
                filename: str,
                start_time: float,
                end_time: float,
                note: str = "",
                environment: Optional[Dict[str, str]] = None,
                error_type: str = "") -> Dict[str, Any]:
    """添加badcase"""
    badcases = load_badcases(task_dir)
    
    badcase_id = 1
    if badcases:
        badcase_id = max(b.get("id", 0) for b in badcases) + 1
    
    badcase = {
        "id": badcase_id,
        "filename": filename,
        "start_time": start_time,
        "end_time": end_time,
        "mark_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "environment": environment or {},
        "error_type": error_type,
        "note": note
    }
    
    badcases.append(badcase)
    save_badcases(task_dir, badcases)
    return badcase


def delete_badcase(task_dir: str, badcase_id: int) -> bool:
    """删除badcase"""
    badcases = load_badcases(task_dir)
    original_len = len(badcases)
    badcases = [b for b in badcases if b.get("id") != badcase_id]
    if len(badcases) < original_len:
        save_badcases(task_dir, badcases)
        return True
    return False


def clear_badcases(task_dir: str) -> int:
    """清空badcase记录，返回删除数量"""
    badcases = load_badcases(task_dir)
    count = len(badcases)
    save_badcases(task_dir, [])
    return count


def update_badcase_note(task_dir: str, badcase_id: int, note: str) -> bool:
    """更新badcase备注"""
    badcases = load_badcases(task_dir)
    for b in badcases:
        if b.get("id") == badcase_id:
            b["note"] = note
            save_badcases(task_dir, badcases)
            return True
    return False


def update_task_environment(task_dir: str, environment: Dict[str, str]) -> bool:
    """更新任务环境参数"""
    config = load_task_config(task_dir)
    if not config:
        return False
    config["environment"] = environment
    config_path = os.path.join(task_dir, "config.json")
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    return True


def delete_task(task_dir: str) -> bool:
    """删除任务"""
    try:
        if os.path.exists(task_dir):
            shutil.rmtree(task_dir)
        return True
    except Exception:
        return False


# ========== 数据集管理 ==========

def update_task_name(task_dir: str, task_name: str) -> bool:
    """Update task name."""
    config = load_task_config(task_dir)
    if not config:
        return False
    config["task_name"] = task_name
    config_path = os.path.join(task_dir, "config.json")
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    return True


def generate_dataset_id() -> str:
    """生成数据集ID"""
    return datetime.now().strftime("dataset_%Y%m%d_%H%M%S")


def create_dataset(dataset_name: str, file_paths: List[str], datasets_dir: str) -> Dict[str, Any]:
    """
    创建音频数据集
    
    Args:
        dataset_name: 数据集名称
        file_paths: 音频文件路径列表
        datasets_dir: 数据集根目录
    
    Returns:
        dataset_info: 数据集信息字典
    """
    dataset_id = generate_dataset_id()
    dataset_dir = os.path.join(datasets_dir, dataset_id)
    files_dir = os.path.join(dataset_dir, "files")
    os.makedirs(files_dir, exist_ok=True)
    
    create_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 复制文件到数据集目录，去重并按文件名排序
    seen = set()
    copied_files = []
    for filepath in file_paths:
        basename = os.path.basename(filepath)
        if basename in seen:
            continue
        seen.add(basename)
        dest = os.path.join(files_dir, basename)
        shutil.copy2(filepath, dest)
        copied_files.append(basename)
    
    copied_files.sort()
    
    meta = {
        "dataset_id": dataset_id,
        "dataset_name": dataset_name,
        "create_time": create_time,
        "total_files": len(copied_files),
        "files": copied_files
    }
    
    meta_path = os.path.join(dataset_dir, "meta.json")
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    
    return meta


def load_dataset_meta(dataset_dir: str) -> Optional[Dict[str, Any]]:
    """加载数据集元数据"""
    meta_path = os.path.join(dataset_dir, "meta.json")
    if not os.path.exists(meta_path):
        return None
    with open(meta_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def delete_dataset(dataset_dir: str) -> bool:
    """删除数据集"""
    try:
        if os.path.exists(dataset_dir):
            shutil.rmtree(dataset_dir)
        return True
    except Exception:
        return False


def get_all_datasets(datasets_base_dir: str) -> List[Dict[str, Any]]:
    """获取所有数据集列表"""
    datasets = []
    if not os.path.exists(datasets_base_dir):
        return datasets
    
    for dataset_id in sorted(os.listdir(datasets_base_dir)):
        dataset_dir = os.path.join(datasets_base_dir, dataset_id)
        if not os.path.isdir(dataset_dir):
            continue
        meta = load_dataset_meta(dataset_dir)
        if meta:
            datasets.append(meta)
    
    # 按创建时间倒序
    datasets.sort(key=lambda x: x.get("create_time", ""), reverse=True)
    return datasets


def get_dataset_file_paths(dataset_dir: str) -> List[str]:
    """获取数据集内所有音频文件的完整路径"""
    files_dir = os.path.join(dataset_dir, "files")
    if not os.path.exists(files_dir):
        return []
    
    wav_files = []
    for f in sorted(os.listdir(files_dir)):
        if f.lower().endswith('.wav'):
            wav_files.append(os.path.join(files_dir, f))
    return wav_files


def analyze_wav_volume(filepath: str) -> Dict[str, Any]:
    """分析单个WAV文件音量，返回RMS dBFS和Peak dBFS。"""
    with wave.open(filepath, 'rb') as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        frame_rate = wav_file.getframerate()
        frame_count = wav_file.getnframes()
        frames = wav_file.readframes(frame_count)

    duration = frame_count / frame_rate if frame_rate else 0.0
    rms = audioop.rms(frames, sample_width) if frames and sample_width else 0
    peak = audioop.max(frames, sample_width) if frames and sample_width else 0
    max_possible = float(1 << (sample_width * 8 - 1)) if sample_width else 1.0
    dbfs = 20 * math.log10(rms / max_possible) if rms > 0 else -120.0
    peak_dbfs = 20 * math.log10(peak / max_possible) if peak > 0 else -120.0

    return {
        "filename": os.path.basename(filepath),
        "filepath": filepath,
        "duration": round(duration, 3),
        "sample_rate": frame_rate,
        "channels": channels,
        "sample_width": sample_width,
        "rms": rms,
        "peak": peak,
        "dbfs": round(dbfs, 2),
        "peak_dbfs": round(peak_dbfs, 2)
    }


def find_lowest_volume_files(dataset_dir: str, limit: int = 20) -> List[Dict[str, Any]]:
    """查找数据集中Peak dBFS最低的音频文件。"""
    file_paths = get_dataset_file_paths(dataset_dir)
    results = []
    for filepath in file_paths:
        try:
            results.append(analyze_wav_volume(filepath))
        except Exception as exc:
            results.append({
                "filename": os.path.basename(filepath),
                "filepath": filepath,
                "error": str(exc),
                "duration": 0,
                "sample_rate": 0,
                "channels": 0,
                "sample_width": 0,
                "rms": None,
                "peak": None,
                "dbfs": None,
                "peak_dbfs": None
            })

    results.sort(key=lambda item: (item.get("peak_dbfs") is None, item.get("peak_dbfs") if item.get("peak_dbfs") is not None else float("inf"), item.get("filename", "")))
    return results[:max(1, limit)]


# ========== 任务相关函数结束 ==========


def get_all_tasks(tasks_base_dir: str) -> List[Dict[str, Any]]:
    """获取所有任务列表"""
    tasks = []
    if not os.path.exists(tasks_base_dir):
        return tasks
    
    for task_id in sorted(os.listdir(tasks_base_dir)):
        task_dir = os.path.join(tasks_base_dir, task_id)
        if not os.path.isdir(task_dir):
            continue
        config = load_task_config(task_dir)
        if config:
            config["task_type"] = config.get("task_type", "wake")
            badcases = load_badcases(task_dir)
            badcase_count = len(badcases)
            total_files = config.get("total_files", 0)

            config["badcase_count"] = badcase_count
            if config["task_type"] == "voiceprint":
                voiceprint_in_count = max(0, int(config.get("voiceprint_in_count", 0) or 0))
                voiceprint_in_count = min(voiceprint_in_count, total_files)
                voiceprint_out_count = max(0, total_files - voiceprint_in_count)
                fn_count = sum(1 for b in badcases if str(b.get("error_type", "")).upper() == "FN")
                fp_count = sum(1 for b in badcases if str(b.get("error_type", "")).upper() == "FP")
                frr = round(fn_count / voiceprint_in_count, 4) if voiceprint_in_count > 0 else 0.0
                far = round(fp_count / voiceprint_out_count, 4) if voiceprint_out_count > 0 else 0.0

                config["voiceprint_in_count"] = voiceprint_in_count
                config["voiceprint_out_count"] = voiceprint_out_count
                config["fn_count"] = fn_count
                config["fp_count"] = fp_count
                config["frr"] = frr
                config["far"] = far
            else:
                wake_count = total_files - badcase_count
                wake_rate = round(wake_count / total_files, 4) if total_files > 0 else 0.0
                config["wake_count"] = wake_count
                config["wake_rate"] = wake_rate
            tasks.append(config)
    
    # 按创建时间倒序
    tasks.sort(key=lambda x: x.get("create_time", ""), reverse=True)
    return tasks


def export_badcases_to_csv(badcases: List[Dict[str, Any]],
                           output_path: str,
                           task_name: str = "",
                           task_configs: Optional[Dict[str, Dict[str, Any]]] = None) -> str:
    """导出badcase为CSV文件"""
    import csv

    fp_count = sum(1 for b in badcases if str(b.get("error_type", "")).upper() == "FP")
    fn_count = sum(1 for b in badcases if str(b.get("error_type", "")).upper() == "FN")
    task_configs = task_configs or {}

    selected_task_ids = {str(b.get("task_id", "")) for b in badcases if b.get("task_id")}
    all_wake = bool(selected_task_ids) and all(
        (task_configs.get(task_id, {}) or {}).get("task_type", "wake") != "voiceprint"
        for task_id in selected_task_ids
    )
    all_voiceprint = bool(selected_task_ids) and all(
        (task_configs.get(task_id, {}) or {}).get("task_type", "wake") == "voiceprint"
        for task_id in selected_task_ids
    )

    total_audio = 0
    total_in_count = 0
    total_out_count = 0
    if all_voiceprint or all_wake:
        for task_id in selected_task_ids:
            config = task_configs.get(task_id, {}) or {}
            total_files = max(0, int(config.get("total_files", 0) or 0))
            total_audio += total_files
            if all_voiceprint:
                in_count = max(0, int(config.get("voiceprint_in_count", 0) or 0))
                in_count = min(in_count, total_files)
                out_count = max(0, total_files - in_count)
                total_in_count += in_count
                total_out_count += out_count

    frr = (fn_count / total_in_count) if total_in_count > 0 else 0.0
    far = (fp_count / total_out_count) if total_out_count > 0 else 0.0
    voiceprint_error_count = fp_count + fn_count
    voiceprint_correct_count = max(0, total_audio - voiceprint_error_count)
    voiceprint_accuracy = (voiceprint_correct_count / total_audio) if total_audio > 0 else 0.0
    wake_rate = ((total_audio - len(badcases)) / total_audio) if total_audio > 0 else 0.0
    
    headers = ["ID", "任务名称", "文件名", "开始时间(秒)", "结束时间(秒)",
               "标记时间", "错误类型", "测试距离", "测试角度", "噪音等级", "备注"]
    
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(["Badcase汇总"])
        if all_voiceprint:
            writer.writerow(["总音频", total_audio])
            writer.writerow(["FP数", fp_count])
            writer.writerow(["FN数", fn_count])
            writer.writerow(["正确数", voiceprint_correct_count])
            writer.writerow(["错误数", voiceprint_error_count])
            writer.writerow(["正确率", f"{voiceprint_accuracy:.2%}"])
            writer.writerow(["FRR", f"{frr:.2%}"])
            writer.writerow(["FAR", f"{far:.2%}"])
            writer.writerow(["RAR", f"{far:.2%}"])
            writer.writerow(["总数", len(badcases)])
        elif all_wake:
            writer.writerow(["总音频", total_audio])
            writer.writerow(["Badcase数", len(badcases)])
            writer.writerow(["唤醒成功数", max(0, total_audio - len(badcases))])
            writer.writerow(["唤醒率", f"{wake_rate:.2%}"])
        else:
            writer.writerow(["FP数", fp_count])
            writer.writerow(["FN数", fn_count])
            writer.writerow(["总数", len(badcases)])
        writer.writerow([])
        writer.writerow(headers)
        for b in badcases:
            env = b.get("environment", {})
            writer.writerow([
                b.get("id", ""),
                b.get("task_name", task_name),
                b.get("filename", ""),
                b.get("start_time", ""),
                b.get("end_time", ""),
                b.get("mark_time", ""),
                b.get("error_type", ""),
                env.get("distance", ""),
                env.get("angle", ""),
                env.get("noise_level", ""),
                b.get("note", "")
            ])
    
    return output_path


def export_task_report_to_csv(config: Dict[str, Any],
                              timestamps: List[Dict[str, Any]],
                              badcases: List[Dict[str, Any]],
                              output_path: str) -> str:
    """
    导出任务完整测试报告为CSV
    
    包含:
    - 汇总信息: 任务名称、测试环境、总音频数、badcase数、唤醒数、唤醒率
    - 明细信息: 每个音频文件的唤醒状态及badcase备注
    """
    import csv
    
    total_files = config.get("total_files", 0)
    badcase_count = len(badcases)
    task_type = config.get("task_type", "wake")
    passed_count = total_files - badcase_count
    pass_rate = round(passed_count / total_files, 4) if total_files > 0 else 0.0
    env = config.get("environment", {})
    
    # 构建 badcase 查找表: filename -> 标记信息
    badcase_map: Dict[str, Dict[str, str]] = {}
    for b in badcases:
        fname = b.get("filename", "")
        note = b.get("note", "")
        error_type = b.get("error_type", "")
        if fname in badcase_map:
            if note:
                existing_note = badcase_map[fname].get("note", "")
                badcase_map[fname]["note"] = f"{existing_note}; {note}" if existing_note else note
            if error_type:
                badcase_map[fname]["error_type"] = error_type
        else:
            badcase_map[fname] = {"note": note, "error_type": error_type}

    voiceprint_rows = []
    voiceprint_counts = {"TP": 0, "TN": 0, "FP": 0, "FN": 0}
    voiceprint_in_count = max(0, int(config.get("voiceprint_in_count", 10) or 0))
    voiceprint_out_count = max(0, int(config.get("voiceprint_out_count", max(0, total_files - voiceprint_in_count)) or 0))
    if task_type == "voiceprint":
        for position, ts in enumerate(timestamps, start=1):
            fname = ts.get("filename", "")
            mark = badcase_map.get(fname, {})
            marked_error_type = str(mark.get("error_type", "")).upper()
            default_result = "TP" if position <= voiceprint_in_count else "TN"
            final_result = marked_error_type if marked_error_type in {"FP", "FN"} else default_result
            voiceprint_counts[final_result] = voiceprint_counts.get(final_result, 0) + 1
            voiceprint_rows.append({
                "ts": ts,
                "default_result": default_result,
                "marked_error_type": marked_error_type,
                "final_result": final_result,
                "note": mark.get("note", "")
            })

    tp_count = voiceprint_counts.get("TP", 0)
    tn_count = voiceprint_counts.get("TN", 0)
    fp_count = voiceprint_counts.get("FP", 0)
    fn_count = voiceprint_counts.get("FN", 0)
    voiceprint_correct_count = tp_count + tn_count
    voiceprint_error_count = fp_count + fn_count
    voiceprint_accuracy = voiceprint_correct_count / total_files if total_files > 0 else 0.0
    frr = fn_count / (tp_count + fn_count) if (tp_count + fn_count) > 0 else 0.0
    far = fp_count / (tn_count + fp_count) if (tn_count + fp_count) > 0 else 0.0
    
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        
        # ===== 汇总信息 =====
        writer.writerow(["任务测试报告"])
        writer.writerow([])
        writer.writerow(["任务名称", config.get("task_name", "")])
        writer.writerow(["任务ID", config.get("task_id", "")])
        writer.writerow(["创建时间", config.get("create_time", "")])
        writer.writerow(["测试距离", env.get("distance", "")])
        writer.writerow(["测试角度", env.get("angle", "")])
        writer.writerow(["噪音等级", env.get("noise_level", "")])
        writer.writerow(["采样率(Hz)", config.get("sample_rate", "")])
        writer.writerow(["位深(bit)", config.get("bit_depth", "")])
        writer.writerow(["声道数", config.get("channels", "")])
        writer.writerow(["音频间隔(秒)", config.get("silence_duration", "")])
        writer.writerow(["总音频数", total_files])
        if task_type == "voiceprint":
            writer.writerow(["声纹库内条数", voiceprint_in_count])
            writer.writerow(["声纹库外条数", voiceprint_out_count])
            writer.writerow(["TP数", tp_count])
            writer.writerow(["TN数", tn_count])
            writer.writerow(["FP数", fp_count])
            writer.writerow(["FN数", fn_count])
            writer.writerow(["正确数", voiceprint_correct_count])
            writer.writerow(["错误数", voiceprint_error_count])
            writer.writerow(["正确率", f"{voiceprint_accuracy:.2%}"])
            writer.writerow(["FRR", f"{frr:.2%}"])
            writer.writerow(["FAR", f"{far:.2%}"])
        else:
            writer.writerow(["Badcase数", badcase_count])
            writer.writerow(["唤醒成功数", passed_count])
            writer.writerow(["唤醒率", f"{pass_rate:.2%}"])
        writer.writerow([])
        
        # ===== 明细信息 =====
        if task_type == "voiceprint":
            writer.writerow(["序号", "文件名", "开始时间(秒)", "结束时间(秒)", "时长(秒)", "默认结果", "标注类型", "最终结果", "备注"])
            for row in voiceprint_rows:
                ts = row["ts"]
                writer.writerow([
                    ts.get("index", ""),
                    ts.get("filename", ""),
                    ts.get("start_time", ""),
                    ts.get("end_time", ""),
                    ts.get("duration", ""),
                    row["default_result"],
                    row["marked_error_type"],
                    row["final_result"],
                    row["note"]
                ])
        else:
            writer.writerow(["序号", "文件名", "开始时间(秒)", "结束时间(秒)", "时长(秒)", "是否唤醒", "Badcase备注"])
            for ts in timestamps:
                fname = ts.get("filename", "")
                mark = badcase_map.get(fname, {})
                note = mark.get("note", "")
                is_wake = "否" if fname in badcase_map else "是"
                writer.writerow([
                    ts.get("index", ""),
                    fname,
                    ts.get("start_time", ""),
                    ts.get("end_time", ""),
                    ts.get("duration", ""),
                    is_wake,
                    note
                ])
    
    return output_path
