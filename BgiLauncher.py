#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BetterGI 智能启动器
根据日期自动匹配启动参数，支持紊乱爆发期与版本更新特殊处理。

v0.1.2（在 v0.1.1 基础上重新发布，功能一致）：
  1. 启动 BetterGI 前检查进程状态：若 Yuanshen.exe 未运行而 BetterGI.exe 正在运行，
     先 taskkill 掉 BetterGI.exe，再执行原有启动流程。
  2. 启动后脚本持续运行，实时采集 BetterGI 的终端输出（命令行启动时 BGI 会把日志打到终端），
     并合并写入日志目录中的合并日志文件，直至 BetterGI 进程关闭。

用法:
  直接双击/命令行运行 exe 本体即可（需管理员权限）
  BgiLauncher.py testbgi    测试 BetterGI 唤起
  BgiLauncher.py testtk     测试 taskkill 功能
  BgiLauncher.py testproc   测试进程检测与日志路径解析
"""

import csv
import ctypes
import io
import json
import logging
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, date, timedelta
from pathlib import Path

# ============================================================
# 常量定义
# ============================================================
APP_NAME = "BetterGI 智能启动器"
VERSION = "0.1.2"
BASE_DIR = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
CONFIG_FILE = BASE_DIR / "config.json"
LOG_DIR = BASE_DIR / "log"

# BetterGI 日志文件前缀（<BetterGI目录>/log/better-genshin-impactYYYYMMDD.log）
BGI_LOG_PREFIX = "better-genshin-impact"

# 原神 7.0 版本基准日期 (2026-08-12)
BASE_VERSION = (7, 0)
BASE_DATE = date(2026, 8, 12)

# 版本周期（天）
VERSION_CYCLE = 42

# 紊乱爆发期起始偏移（版本更新后第 N 天，从 0 开始计数）
BURST_START_DAY = 7   # 第 8 天 = 索引 7

# 紊乱爆发期持续时间（天）
BURST_DURATION = 10

# 紊乱爆发期结束时间
BURST_END_HOUR = 3
BURST_END_MINUTE = 59

# 版本更新当天维护结束时间
MAINTENANCE_END_HOUR = 10

# subprocess 静默窗口标志（Windows）
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# ============================================================
# 日志系统
# ============================================================
SESSION_LOG_DIR = LOG_DIR / date.today().strftime("%Y-%m-%d")
SESSION_TS = datetime.now().strftime("%H-%M-%S")


def setup_logger():
    """配置日志系统：按日期分目录，记录常规日志和错误日志"""
    global SESSION_LOG_DIR, SESSION_TS

    today_str = date.today().strftime("%Y-%m-%d")
    SESSION_LOG_DIR = LOG_DIR / today_str
    SESSION_LOG_DIR.mkdir(parents=True, exist_ok=True)

    SESSION_TS = datetime.now().strftime("%H-%M-%S")
    log_file = SESSION_LOG_DIR / f"{SESSION_TS}.log"
    error_file = SESSION_LOG_DIR / f"error-{SESSION_TS}.log"

    logger = logging.getLogger("BGI_Launcher")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    # 常规日志
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(fh)

    # 错误日志
    eh = logging.FileHandler(error_file, encoding="utf-8")
    eh.setLevel(logging.ERROR)
    eh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(eh)

    # 控制台输出
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(ch)

    return logger


logger = setup_logger()


# ============================================================
# UAC 管理员权限检测
# ============================================================
def is_admin():
    """检查当前进程是否具有管理员权限"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def request_admin():
    """以管理员权限重新启动自身"""
    try:
        script = sys.executable if getattr(sys, 'frozen', False) else __file__
        params = " ".join(f'"{a}"' for a in sys.argv[1:])
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, f'"{script}" {params}', None, 1
        )
    except Exception as e:
        logger.error(f"请求管理员权限失败: {e}")


# ============================================================
# 配置文件管理
# ============================================================
DEFAULT_CONFIG = {
    "bettergi_path": "",
    "config_name_mapping": {
        "burst": "wz",
        "normal": "dm"
    },
    "pre_launch_check": {
        "enabled": True,
        "bgi_process": "BetterGI.exe",
        "game_process": "Yuanshen.exe",
        "kill_bgi_if_game_absent": True,
        "wait_after_kill_seconds": 3
    },
    "monitor": {
        "enabled": True,
        "poll_interval_seconds": 2,
        "startup_timeout_seconds": 120,
        "max_duration_hours": 12,
        "capture_stdout": True,
        "follow_log_file": False,
        "follow_log_file_fallback": True,
        "stdout_grace_seconds": 20
    },
    "special_rules": {
        "burst_first_day_as_normal": True,
        "update_day_kill_after_dm": True,
        "kill_delay_seconds": 60,
        "kill_processes": ["Yuanshen.exe", "BetterGI.exe"]
    }
}


def load_config():
    """加载配置文件，不存在则创建"""
    if not CONFIG_FILE.exists():
        logger.info("未找到配置文件，正在创建默认配置...")
        save_config(DEFAULT_CONFIG)
        # 首次启动时弹出文件选择对话框
        select_bgi_path_interactive()
        return load_config()

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"配置文件读取失败: {e}，使用默认配置")
        return json.loads(json.dumps(DEFAULT_CONFIG))

    # 补全缺失字段（深拷贝默认值，避免污染 DEFAULT_CONFIG）
    for key, value in DEFAULT_CONFIG.items():
        if key not in config:
            config[key] = json.loads(json.dumps(value))
        elif isinstance(value, dict) and isinstance(config.get(key), dict):
            for sub_key, sub_val in value.items():
                config[key].setdefault(sub_key, sub_val)

    return config


def save_config(config):
    """保存配置到文件"""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        logger.info(f"配置已保存至: {CONFIG_FILE}")
    except IOError as e:
        logger.error(f"配置保存失败: {e}")


def select_bgi_path_interactive():
    """弹出文件选择对话框，让用户选择 BetterGI.exe"""
    logger.info("请在弹出的对话框中选择 BetterGI.exe 的路径...")
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)

        file_path = filedialog.askopenfilename(
            title="请选择 BetterGI.exe",
            filetypes=[("可执行文件", "*.exe"), ("所有文件", "*.*")]
        )
        root.destroy()

        if file_path:
            config = load_config()
            config["bettergi_path"] = file_path
            save_config(config)
            logger.info(f"已选择 BetterGI 路径: {file_path}")
        else:
            logger.warning("未选择文件，配置文件中的路径为空，程序将无法启动 BetterGI")
    except Exception as e:
        logger.error(f"文件选择对话框出错: {e}")


# ============================================================
# 版本与日期计算
# ============================================================
def get_version_info(target_date: date):
    """
    根据目标日期计算版本号和版本内天数。
    返回: (major, minor, days_since_start)
    """
    delta = (target_date - BASE_DATE).days
    if delta < 0:
        # 早于基准日期，向前推算
        version_offset = delta // VERSION_CYCLE
        if delta % VERSION_CYCLE != 0:
            version_offset -= 1
        day_in_version = delta - version_offset * VERSION_CYCLE
        major = BASE_VERSION[0]
        minor = BASE_VERSION[1] + version_offset
    else:
        version_offset = delta // VERSION_CYCLE
        day_in_version = delta % VERSION_CYCLE
        major = BASE_VERSION[0]
        minor = BASE_VERSION[1] + version_offset

    # 处理 minor 溢出（每 10 个小版本进位）
    while minor >= 10:
        major += 1
        minor -= 10

    return major, minor, day_in_version


def get_version_start_date(major, minor):
    """获取指定版本开始日期"""
    offset = (major - BASE_VERSION[0]) * 10 + (minor - BASE_VERSION[1])
    return BASE_DATE + timedelta(days=offset * VERSION_CYCLE)


def is_burst_period(target_date: date, config: dict):
    """
    判断目标日期是否处于紊乱爆发期。
    返回: (是否爆发期, 版本信息字符串, 说明)
    """
    major, minor, day_in = get_version_info(target_date)
    version_str = f"{major}.{minor}"

    special = config.get("special_rules", {})
    first_day_as_normal = special.get("burst_first_day_as_normal", True)

    burst_start = BURST_START_DAY
    burst_end = BURST_START_DAY + BURST_DURATION - 1

    # 版本更新当天（day_in == 0）固定为非爆发期
    if day_in == 0:
        return False, version_str, f"版本更新当天，使用常规配置"

    # 爆发期第一天视为非爆发期（可配置）
    if first_day_as_normal and day_in == burst_start:
        return False, version_str, f"紊乱爆发期第一天（视为非爆发期），使用常规配置"

    if burst_start <= day_in <= burst_end:
        # 检查结束时间（爆发期最后一天 03:59 结束）
        if day_in == burst_end:
            now = datetime.now()
            if now.hour > BURST_END_HOUR or (
                now.hour == BURST_END_HOUR and now.minute > BURST_END_MINUTE
            ):
                return False, version_str, f"紊乱爆发期已结束（03:59后），使用常规配置"

        return True, version_str, f"紊乱爆发期（第{day_in + 1}天），使用爆发期配置"

    return False, version_str, f"非爆发期（第{day_in + 1}天），使用常规配置"


def is_update_day(target_date: date):
    """判断是否为版本更新日"""
    major, minor, day_in = get_version_info(target_date)
    return day_in == 0


def is_maintenance_time():
    """判断当前是否在维护时间（10:00 之前）"""
    now = datetime.now()
    return now.hour < MAINTENANCE_END_HOUR


# ============================================================
# 进程管理
# ============================================================
def get_process_pids(image_name: str):
    """
    返回指定映像名称当前正在运行的 PID 列表（空列表表示未运行）。

    使用 tasklist 的 CSV 输出，只解析以引号开头的行，
    从而避免受系统语言（"没有运行的任务匹配指定标准"）的影响。
    """
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/FO", "CSV", "/NH"],
            capture_output=True, timeout=15,
            creationflags=CREATE_NO_WINDOW
        )
        output = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
    except subprocess.TimeoutExpired:
        logger.error(f"查询进程 {image_name} 超时")
        return []
    except Exception as e:
        logger.error(f"查询进程 {image_name} 出错: {e}")
        return []

    pids = []
    for row in csv.reader(io.StringIO(output)):
        if not row or len(row) < 2:
            continue
        if row[0].strip().lower() != image_name.lower():
            continue
        try:
            pids.append(int(row[1].strip()))
        except ValueError:
            pids.append(row[1].strip())
    return pids


def is_process_running(image_name: str) -> bool:
    """判断指定映像名称的进程是否正在运行"""
    return len(get_process_pids(image_name)) > 0


def kill_processes(process_names: list):
    """终止指定进程"""
    for name in process_names:
        try:
            result = subprocess.run(
                ["taskkill", "/F", "/IM", name],
                capture_output=True, text=True, timeout=10,
                creationflags=CREATE_NO_WINDOW
            )
            if result.returncode == 0:
                logger.info(f"已终止进程: {name}")
            else:
                msg = (result.stderr or result.stdout or "").strip()
                logger.warning(f"终止 {name} 失败或无此进程: {msg}")
        except subprocess.TimeoutExpired:
            logger.error(f"终止 {name} 超时")
        except Exception as e:
            logger.error(f"终止 {name} 时出错: {e}")


def pre_launch_process_check(config: dict):
    """
    启动 BetterGI 前的进程状态检查。

    规则：若 游戏进程(Yuanshen.exe) 不在运行 而 BetterGI.exe 正在运行，
          说明残留了无人值守的上一轮 BetterGI，先 taskkill 掉，再走原有启动流程。
    """
    check_cfg = config.get("pre_launch_check", {})
    if not check_cfg.get("enabled", True):
        logger.info("启动前进程检查已禁用（pre_launch_check.enabled = false）")
        return

    bgi_proc = check_cfg.get("bgi_process", "BetterGI.exe")
    game_proc = check_cfg.get("game_process", "Yuanshen.exe")
    kill_if_absent = check_cfg.get("kill_bgi_if_game_absent", True)

    game_pids = get_process_pids(game_proc)
    bgi_pids = get_process_pids(bgi_proc)
    logger.info(
        f"启动前进程检查: {game_proc} = {game_pids if game_pids else '未运行'}，"
        f"{bgi_proc} = {bgi_pids if bgi_pids else '未运行'}"
    )

    # 情况 1：BetterGI 未运行 —— 直接进入启动流程
    if not bgi_pids:
        logger.info(f"{bgi_proc} 未运行，无需清理，直接进入启动流程")
        return

    # 情况 2：游戏正在运行 —— 保留现有 BetterGI，不打扰正在进行的任务
    if game_pids:
        logger.info(
            f"{game_proc} 正在运行（PID: {', '.join(map(str, game_pids))}），"
            f"保留现有 {bgi_proc}，不执行 taskkill"
        )
        return

    # 情况 3：游戏未运行但 BetterGI 残留 —— 先杀掉
    if not kill_if_absent:
        logger.info(f"检测到 {bgi_proc} 残留，但 kill_bgi_if_game_absent = false，跳过清理")
        return

    logger.warning(
        f"检测到 {bgi_proc} 正在运行（PID: {', '.join(map(str, bgi_pids))}）"
        f"而 {game_proc} 未运行，先终止 {bgi_proc} 后再执行启动流程"
    )
    kill_processes([bgi_proc])

    wait_after = float(check_cfg.get("wait_after_kill_seconds", 3) or 0)
    if wait_after > 0:
        logger.info(f"等待 {wait_after:g} 秒，确保进程完全退出并释放文件句柄")
        time.sleep(wait_after)

    remain = get_process_pids(bgi_proc)
    if remain:
        logger.error(f"{bgi_proc} 仍存在残留进程（PID: {', '.join(map(str, remain))}），继续尝试启动")
    else:
        logger.info(f"{bgi_proc} 已全部终止，继续执行启动流程")


# ============================================================
# BetterGI 启动
# ============================================================
def launch_bettergi(config: dict, config_name: str):
    """
    启动 BetterGI 并指定一条龙配置。

    返回: (是否成功, Popen 对象或 None)
    注意：stdout/stderr 必须由调用方持续读取（本项目由 BgiOutputWriter 的读取线程负责），
          否则管道缓冲区写满后 BetterGI 会被阻塞。
    """
    bgi_path = config.get("bettergi_path", "")
    if not bgi_path or not os.path.exists(bgi_path):
        logger.error(f"BetterGI 路径无效或不存在: {bgi_path}")
        return False, None

    cmd = [bgi_path, "startOneDragon", config_name]
    logger.info(f"执行命令: {' '.join(cmd)}")

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=os.path.dirname(bgi_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW
        )
        logger.info(f"BetterGI 已启动，PID: {proc.pid}")
        return True, proc
    except FileNotFoundError:
        logger.error(f"找不到可执行文件: {bgi_path}")
        return False, None
    except Exception as e:
        logger.error(f"启动 BetterGI 失败: {e}")
        return False, None


# ============================================================
# BetterGI 日志采集（终端输出 + 日志文件跟随）
# ============================================================
def decode_output(raw) -> str:
    """解码子进程输出：优先 UTF-8，回退 GBK（中文 Windows 默认控制台代码页）"""
    if isinstance(raw, str):
        return raw
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, AttributeError):
            continue
    return raw.decode("utf-8", errors="replace")


def get_bgi_log_dir(bgi_path: str) -> Path:
    """BetterGI 日志目录：<BetterGI.exe 所在目录>/log"""
    return Path(bgi_path).parent / "log"


def capture_bgi_log_baseline(bgi_path: str):
    """
    记录启动前 BetterGI 日志文件的大小基线，返回 (Path, size) 或 None。
    这样监听时只消费本次启动之后新增的内容，不会把当天早先的会话日志重复搬进来。
    """
    log_dir = get_bgi_log_dir(bgi_path)
    if not log_dir.is_dir():
        return None
    candidates = []
    for p in log_dir.glob(f"{BGI_LOG_PREFIX}*.log"):
        try:
            candidates.append((p.stat().st_mtime, p, p.stat().st_size))
        except OSError:
            continue
    if not candidates:
        return None
    candidates.sort()
    _, path, size = candidates[-1]
    return path, size


class MergedLogWriter:
    """线程安全的合并日志写入器"""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._fh = None
        self.lines = 0
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = open(self.path, "a", encoding="utf-8", errors="replace")
        except OSError as e:
            logger.error(f"无法创建合并日志文件 {self.path}: {e}")

    def write(self, text: str):
        if self._fh is None:
            return
        with self._lock:
            try:
                self._fh.write(text.rstrip("\r\n") + "\n")
                self._fh.flush()
                self.lines += 1
            except (OSError, ValueError) as e:
                logger.error(f"写入合并日志失败: {e}")

    def comment(self, text: str):
        """写入一条带时间戳的说明行（便于日后阅读合并日志）"""
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.write(f"#### [{stamp}] {text}")

    def close(self):
        if self._fh is None:
            return
        with self._lock:
            try:
                self._fh.close()
            except (OSError, ValueError):
                pass
            self._fh = None


class BgiStdoutReader(threading.Thread):
    """
    后台线程：持续读取 BetterGI 子进程的终端输出并写入合并日志。
    命令行启动 BetterGI 时，其运行日志会直接打印到终端，这正是我们要采集的内容。
    """

    def __init__(self, stream, writer: MergedLogWriter, tag: str = "stdout"):
        super().__init__(daemon=True, name="BgiStdoutReader")
        self._stream = stream
        self._writer = writer
        self._tag = tag
        self.lines = 0

    def run(self):
        try:
            for raw in iter(self._stream.readline, b""):
                line = decode_output(raw).rstrip("\r\n")
                if not line:
                    continue
                self._writer.write(line)
                self.lines += 1
        except (OSError, ValueError) as e:
            logger.debug(f"读取 BetterGI {self._tag} 结束: {e}")
        finally:
            try:
                self._stream.close()
            except (OSError, ValueError):
                pass


class BgiLogFollower:
    """
    跟随 BetterGI 日志文件（<BGI目录>/log/better-genshin-impactYYYYMMDD.log），
    把新增内容增量合并到合并日志中。用于兜底：当终端没有输出时（例如 BGI 把任务
    交接给了已存在的实例），仍然能拿到日志。
    """

    def __init__(self, bgi_path: str, writer: MergedLogWriter, baseline=None):
        self.log_dir = get_bgi_log_dir(bgi_path)
        self.writer = writer
        self._baseline = {}
        if baseline:
            path, size = baseline
            self._baseline[str(path)] = int(size)
        self._path = None
        self._handle = None
        self._pos = 0
        self.lines = 0

    def _pick_log_file(self):
        if not self.log_dir.is_dir():
            return None
        candidates = []
        for p in self.log_dir.glob(f"{BGI_LOG_PREFIX}*.log"):
            try:
                candidates.append((p.stat().st_mtime, p))
            except OSError:
                continue
        if not candidates:
            return None
        candidates.sort()
        return candidates[-1][1]

    def _switch_to(self, path: Path):
        if self._handle:
            try:
                self._handle.close()
            except (OSError, ValueError):
                pass
        self._handle = open(path, "r", encoding="utf-8", errors="replace")
        start = self._baseline.get(str(path))
        if start is None:
            # 首次附加到已存在的日志文件时，用启动前记录的基线；
            # 中途出现的新文件（例如跨零点）则从头读起。
            start = 0
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        start = min(start, size)
        self._handle.seek(start)
        self._pos = start
        self._path = path
        logger.info(f"开始跟随 BetterGI 日志文件: {path}（起始偏移 {start} 字节）")
        self.writer.comment(f"开始跟随 BetterGI 日志文件: {path}")

    def poll(self) -> int:
        """读取一次增量，返回本次新增的行数"""
        path = self._pick_log_file()
        if path is None:
            return 0
        try:
            if self._handle is None or self._path != path:
                self._switch_to(path)
            else:
                size = path.stat().st_size
                if size < self._pos:
                    # 文件被截断/重建，从头读
                    self._handle.seek(0)
                    self._pos = 0
        except OSError as e:
            logger.debug(f"跟随 BetterGI 日志出错: {e}")
            return 0

        written = 0
        while True:
            try:
                pos_before = self._handle.tell()
                line = self._handle.readline()
            except (OSError, ValueError) as e:
                logger.debug(f"读取 BetterGI 日志出错: {e}")
                break
            if not line:
                break
            if not line.endswith("\n"):
                # 不完整的行（BGI 正在写入），回退等待下次读取
                self._handle.seek(pos_before)
                break
            self.writer.write(line)
            written += 1
            self.lines += 1
        try:
            self._pos = self._handle.tell()
        except (OSError, ValueError):
            pass
        return written

    def close(self):
        if self._handle:
            try:
                self._handle.close()
            except (OSError, ValueError):
                pass
            self._handle = None


def monitor_bettergi(config: dict, bgi_path: str, proc, writer: MergedLogWriter,
                     baseline=None, pending_kill=None):
    """
    持续监听 BetterGI：采集终端输出（主）+ 日志文件（兜底），
    直到 BetterGI 进程被关闭（或触发更新日终止、或超过最大监听时长）。
    """
    mon = config.get("monitor", {})
    bgi_proc = config.get("pre_launch_check", {}).get("bgi_process", "BetterGI.exe")
    interval = max(0.2, float(mon.get("poll_interval_seconds", 2) or 2))
    startup_timeout = float(mon.get("startup_timeout_seconds", 120) or 0)
    max_hours = float(mon.get("max_duration_hours", 12) or 0)
    capture_stdout = bool(mon.get("capture_stdout", True))
    follow_file = bool(mon.get("follow_log_file", False))
    file_fallback = bool(mon.get("follow_log_file_fallback", True))
    stdout_grace = float(mon.get("stdout_grace_seconds", 20) or 0)

    reader = None
    if capture_stdout and proc is not None and proc.stdout is not None:
        reader = BgiStdoutReader(proc.stdout, writer)
        reader.start()
        logger.info("已启动终端输出采集线程（BetterGI stdout）")
    else:
        logger.info("终端输出采集已关闭")

    follower = None
    if follow_file:
        follower = BgiLogFollower(bgi_path, writer, baseline)
        logger.info("已启用 BetterGI 日志文件跟随（配置开启）")

    start = time.monotonic()
    detected = False
    killed = False
    reason = "BetterGI 进程已关闭"

    logger.info(f"进入监听状态：每 {interval:g} 秒检查一次 {bgi_proc} 进程状态")

    try:
        while True:
            running = is_process_running(bgi_proc)

            if running:
                if not detected:
                    detected = True
                    logger.info(f"已检测到 BetterGI 进程，开始持续监听日志")
                    logger.info(f"合并日志文件: {writer.path}")
                    writer.comment(f"检测到 {bgi_proc} 进程，开始采集运行日志")
                if follower:
                    follower.poll()
            else:
                if not detected:
                    # 启动宽限期：进程可能还没起来
                    if follower:
                        follower.poll()
                    if startup_timeout and (time.monotonic() - start) > startup_timeout:
                        reason = f"{startup_timeout:.0f} 秒内未检测到 {bgi_proc} 进程"
                        logger.error(reason + "，结束监听")
                        break
                else:
                    # 进程已退出：再抓一次尾部日志后结束
                    if follower:
                        follower.poll()
                    reason = f"{bgi_proc} 进程已关闭"
                    logger.info(f"检测到 {bgi_proc} 已退出，停止日志监听")
                    break

            elapsed = time.monotonic() - start

            # 兜底：终端始终没有输出时，自动切换到日志文件跟随
            if (follower is None and file_fallback and not follow_file
                    and (reader is None or reader.lines == 0)
                    and elapsed > stdout_grace):
                logger.warning(
                    f"启动 {stdout_grace:g} 秒后仍未采集到终端输出，"
                    f"自动启用 BetterGI 日志文件跟随作为兜底"
                )
                follower = BgiLogFollower(bgi_path, writer, baseline)
                follower.poll()

            # 更新日计划终止
            if pending_kill and time.monotonic() >= pending_kill["at"] and not killed:
                killed = True
                logger.info(
                    f"更新日特殊规则：延迟 {pending_kill['delay']:g} 秒到期，"
                    f"终止 {pending_kill['processes']}"
                )
                writer.comment(f"更新日特殊规则：终止 {pending_kill['processes']}")
                kill_processes(pending_kill["processes"])
                pending_kill = None

            # 最大监听时长保护（无人值守时防止永久驻留）
            if max_hours > 0 and elapsed > max_hours * 3600:
                reason = f"已达到最大监听时长 {max_hours:g} 小时"
                logger.warning(reason + "，停止监听")
                break

            time.sleep(interval)
    finally:
        # 收尾：再抓一次日志，等待采集线程退出
        if follower:
            try:
                follower.poll()
            except Exception:
                pass
        if reader is not None:
            reader.join(timeout=5)
        if follower:
            follower.close()

    # proc 退出码（若子进程已结束）
    exit_code = proc.poll() if proc is not None else None
    writer.comment(f"监听结束：{reason}；合并日志行数 {writer.lines}")
    logger.info(
        f"监听结束 -> {reason}，合并日志行数 {writer.lines}"
        + (f"，子进程退出码 {exit_code}" if exit_code is not None else "")
    )
    return reason, exit_code


# ============================================================
# 测试模式
# ============================================================
def test_bgi(config: dict):
    """测试模式：验证是否能够唤起带有 UAC 权限的 BetterGI"""
    logger.info("=" * 50)
    logger.info("[测试模式] testbgi - 验证 BetterGI 唤起")
    logger.info("=" * 50)

    bgi_path = config.get("bettergi_path", "")
    logger.info(f"BetterGI 路径: {bgi_path}")
    logger.info(f"路径存在: {os.path.exists(bgi_path)}")
    logger.info(f"当前管理员权限: {is_admin()}")

    if not os.path.exists(bgi_path):
        logger.error("BetterGI 路径无效，测试失败")
        return

    try:
        # 以管理员身份启动一个简单的命令来验证 UAC 兼容性
        result = subprocess.run(
            [bgi_path, "--help"],
            capture_output=True, text=True, timeout=15,
            creationflags=CREATE_NO_WINDOW
        )
        logger.info(f"BetterGI --help 退出码: {result.returncode}")
        logger.info("BetterGI 可正常唤起")
    except subprocess.TimeoutExpired:
        logger.warning("BetterGI --help 超时（可能已弹出 GUI 窗口）")
        logger.info("BetterGI 可正常唤起")
    except Exception as e:
        logger.error(f"唤起 BetterGI 失败: {e}")


def test_taskkill(config: dict):
    """测试模式：验证 taskkill 功能"""
    logger.info("=" * 50)
    logger.info("[测试模式] testtk - 验证 taskkill 功能")
    logger.info("=" * 50)

    test_process = "notepad.exe"
    logger.info(f"启动测试进程: {test_process}")

    try:
        proc = subprocess.Popen(
            [test_process],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=CREATE_NO_WINDOW
        )
        logger.info(f"测试进程已启动，PID: {proc.pid}")
        time.sleep(2)

        # 使用 taskkill 终止
        result = subprocess.run(
            ["taskkill", "/F", "/IM", test_process],
            capture_output=True, text=True, timeout=10,
            creationflags=CREATE_NO_WINDOW
        )
        logger.info(f"taskkill 退出码: {result.returncode}")
        logger.info(f"taskkill 输出: {result.stdout.strip()}")

        if result.returncode == 0:
            logger.info("taskkill 功能正常")
        else:
            logger.error(f"taskkill 失败: {result.stderr.strip()}")

    except FileNotFoundError:
        logger.error("找不到 notepad.exe，无法测试")
    except Exception as e:
        logger.error(f"taskkill 测试出错: {e}")


def test_process(config: dict):
    """测试模式：验证进程检测与日志路径解析"""
    logger.info("=" * 50)
    logger.info("[测试模式] testproc - 验证进程检测与日志路径解析")
    logger.info("=" * 50)

    check_cfg = config.get("pre_launch_check", {})
    bgi_proc = check_cfg.get("bgi_process", "BetterGI.exe")
    game_proc = check_cfg.get("game_process", "Yuanshen.exe")

    for name in (bgi_proc, game_proc):
        pids = get_process_pids(name)
        logger.info(f"{name}: {'运行中 PID=' + ', '.join(map(str, pids)) if pids else '未运行'}")

    bgi_path = config.get("bettergi_path", "")
    log_dir = get_bgi_log_dir(bgi_path)
    logger.info(f"BetterGI 路径: {bgi_path}")
    logger.info(f"日志目录: {log_dir}（存在: {log_dir.is_dir()}）")

    baseline = capture_bgi_log_baseline(bgi_path)
    if baseline:
        logger.info(f"当前日志基线: {baseline[0]}（{baseline[1]} 字节）")
    else:
        logger.info("当前日志基线: 未找到匹配的日志文件")

    logger.info(f"合并日志将写入: {SESSION_LOG_DIR / ('bettergi-merge-' + SESSION_TS + '.log')}")


# ============================================================
# 主流程
# ============================================================
def main():
    logger.info("=" * 60)
    logger.info(f"{APP_NAME} v{VERSION} 启动")
    logger.info(f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # --- UAC 权限检查 ---
    if not is_admin():
        logger.error("当前未以管理员权限运行！")
        logger.error("请右键以管理员身份运行本程序。")
        try:
            ctypes.windll.user32.MessageBoxW(
                0,
                "本程序需要管理员权限才能正常运行。\n\n"
                "请右键以管理员身份运行。",
                f"{APP_NAME} - 权限不足",
                0x10 | 0x40000  # MB_ICONERROR | MB_TOPMOST
            )
        except Exception:
            pass
        sys.exit(1)

    logger.info("管理员权限验证通过")

    # --- 加载配置 ---
    config = load_config()

    # --- 处理命令行参数 ---
    args = sys.argv[1:] if not getattr(sys, 'frozen', False) else sys.argv[1:]

    if "testbgi" in args:
        test_bgi(config)
        return

    if "testtk" in args:
        test_taskkill(config)
        return

    if "testproc" in args:
        test_process(config)
        return

    # --- 正常启动流程 ---
    today = date.today()

    # 获取版本信息
    major, minor, day_in = get_version_info(today)
    version_str = f"{major}.{minor}"
    logger.info(f"当前版本: {version_str}，版本内第 {day_in + 1} 天")

    # 判断是否为更新日
    update_day = is_update_day(today)
    maintenance = is_maintenance_time()

    if update_day:
        logger.info(f"今天是版本更新日（{version_str}）")

    # 判断爆发期
    burst, ver_str, reason = is_burst_period(today, config)
    logger.info(f"日期判断结果: {reason}")

    # 确定配置名称
    mapping = config.get("config_name_mapping", {})
    if burst:
        config_name = mapping.get("burst", "wz")
    else:
        config_name = mapping.get("normal", "dm")

    logger.info(f"使用配置名称: {config_name}")

    bgi_path = config.get("bettergi_path", "")

    # --- 启动前进程检查（v0.1.1）---
    pre_launch_process_check(config)

    # --- 记录 BetterGI 日志基线（仅消费本次启动后的新增日志）---
    baseline = capture_bgi_log_baseline(bgi_path)
    if baseline:
        logger.info(f"BetterGI 日志基线: {baseline[0]}（{baseline[1]} 字节）")

    # --- 启动 BetterGI ---
    success, proc = launch_bettergi(config, config_name)

    if not success:
        logger.error("启动 BetterGI 失败，程序退出")
        sys.exit(1)

    # --- 更新日特殊处理：计划延迟终止 ---
    special = config.get("special_rules", {})
    pending_kill = None
    if update_day and special.get("update_day_kill_after_dm", True):
        if config_name == mapping.get("normal", "dm"):
            kill_delay = float(special.get("kill_delay_seconds", 60) or 0)
            kill_list = special.get("kill_processes", ["Yuanshen.exe", "BetterGI.exe"])
            logger.info(f"更新日特殊规则：{kill_delay:g} 秒后终止 {kill_list}")
            pending_kill = {
                "at": time.monotonic() + kill_delay,
                "delay": kill_delay,
                "processes": kill_list,
            }
    else:
        logger.info("无更新日特殊处理")

    # --- 持续监听 BetterGI 日志，直至进程关闭（v0.1.1）---
    mon = config.get("monitor", {})
    if mon.get("enabled", True):
        merged_path = SESSION_LOG_DIR / f"bettergi-merge-{SESSION_TS}.log"
        writer = MergedLogWriter(merged_path)
        try:
            writer.write(f"# BetterGI 运行日志合并文件")
            writer.write(f"# 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            writer.write(f"# 启动器版本: v{VERSION}")
            writer.write(f"# BetterGI: {bgi_path}")
            writer.write(f"# 一条龙配置: {config_name}（{reason}）")
            writer.write("# " + "=" * 58)

            monitor_bettergi(config, bgi_path, proc, writer,
                             baseline=baseline, pending_kill=pending_kill)
        finally:
            writer.close()
    else:
        logger.info("监听功能已禁用（monitor.enabled = false），启动完成后直接退出")

    logger.info("程序执行完毕")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("用户中断")
    except Exception as e:
        logger.exception(f"未处理的异常: {e}")
        sys.exit(1)
