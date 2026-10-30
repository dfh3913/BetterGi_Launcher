#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BetterGI 智能启动器
根据实际启动时刻自动匹配启动参数，支持紊乱爆发期与版本更新特殊处理。

v0.1.4（新增）：
  崩溃自动重启：BetterGI 异常退出（.NET Fatal error / AccessViolationException 等致命错误，
  或非零退出码）且一条龙任务尚未完成时，按配置自动重启 BetterGI 并继续监听；
  任务已完成、用户关闭游戏、启动器主动终止等情况下不重启，重启次数与间隔可配置。

v0.1.3：
  1. 终端回显：由命令行启动本程序时，BetterGI 的运行日志会一并输出到当前终端
     （打包为窗口程序时通过 AttachConsole 附着到父控制台；无控制台时仅写日志文件）。
  2. 焦点守护：BetterGI 日志出现“不是原神 …… 暂停”时，自动把原神窗口切到前台；
     运行期按 F12 可取消 / 恢复该功能（不写入配置文件，仅本次运行生效）。
  3. 爆发期判定改为按“启动游戏的时间”精确到分钟：
     紊乱爆发期 = 版本更新后第 8 天 10:00 ~ 第 18 天 03:59（第 17 天 03:59 结束），
     修正旧版把结束日提前一天的问题；同时按官方维护窗口（06:00 停服、约 11:00 开服）提示。

v0.1.2：
  1. 启动 BetterGI 前检查进程状态：若 Yuanshen.exe 未运行而 BetterGI.exe 正在运行，
     先 taskkill 掉 BetterGI.exe，再执行原有启动流程。
  2. 启动后脚本持续运行，实时采集 BetterGI 的终端输出，并合并写入日志目录中的合并日志文件。

用法:
  直接双击/命令行运行 exe 本体即可（需管理员权限）
  BgiLauncher.py testbgi    测试 BetterGI 唤起
  BgiLauncher.py testtk     测试 taskkill 功能
  BgiLauncher.py testproc   测试进程检测与日志路径解析
  BgiLauncher.py testtime   测试版本 / 紊乱爆发期时间判定
"""

import collections
import csv
import ctypes
import io
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from datetime import datetime, date, time as dtime, timedelta
from pathlib import Path

# ============================================================
# 常量定义
# ============================================================
APP_NAME = "BetterGI 智能启动器"
VERSION = "0.1.4"
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

# ---- 紊乱爆发期（幽境危战常驻战斗活动）----
# 官方公告口径：挑战开启后 10 天内为紊乱爆发期。
# 挑战开启时间 = 版本更新后第 8 天 10:00；爆发期最后一天为第 17 天，03:59 结束（04:00 为每日重置）。
# 实例（7.1 版本 / 2026-09-23 更新）：09-30 10:00 ~ 10-10 03:59
BURST_START_DAY = 7          # 版本更新后第 8 天（0 基索引）
BURST_START_HOUR = 10        # 开启时刻 10:00
BURST_DURATION_DAYS = 10     # 持续 10 天
BURST_END_DAY = BURST_START_DAY + BURST_DURATION_DAYS   # 第 18 天 04:00 之前（0 基索引 17）
BURST_END_HOUR = 4           # 每日 04:00 重置，即最后一天 03:59 结束

# ---- 版本更新维护窗口 ----
MAINTENANCE_START_HOUR = 6   # 官方公告：06:00 开始停服维护
SERVER_OPEN_HOUR = 11        # 官方公告：预计 5 小时，约 11:00 开服

# 焦点守护使用的 F1 ~ F12 虚拟键码
VK_CODES = {f"F{i}": 0x6F + i for i in range(1, 13)}

# subprocess 静默窗口标志（Windows）
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# ============================================================
# 终端输出（v0.1.3）
# ============================================================
CONSOLE_STREAM = None

GENERIC_WRITE = 0x40000000
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class ConsoleStream:
    """
    基于 WriteConsoleW 的控制台输出流。

    直接 open("CONOUT$") 是“按字节”写控制台，需要与控制台代码页（GBK / UTF-8）
    严格匹配；在 Windows Terminal、ConPTY、重定向等场景下极易出现中文乱码。
    WriteConsoleW 走 Unicode 接口，由系统自行转换，不受代码页影响。
    """

    def __init__(self, handle):
        self._handle = handle

    def write(self, text):
        if not text:
            return 0
        try:
            written = wintypes.DWORD(0)
            ctypes.windll.kernel32.WriteConsoleW(
                self._handle, text, len(text), ctypes.byref(written), None
            )
            return int(written.value)
        except Exception:
            return len(text)

    def flush(self):
        return None

    def isatty(self):
        return True


def open_console_stream():
    """通过 CreateFileW("CONOUT$") + WriteConsoleW 打开当前控制台"""
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateFileW.restype = ctypes.c_void_p
    kernel32.CreateFileW.argtypes = [
        ctypes.c_wchar_p, wintypes.DWORD, wintypes.DWORD,
        ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
    ]
    kernel32.WriteConsoleW.argtypes = [
        ctypes.c_void_p, ctypes.c_wchar_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
    ]
    handle = kernel32.CreateFileW(
        "CONOUT$", GENERIC_WRITE, FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None
    )
    if not handle or handle == INVALID_HANDLE_VALUE:
        return None
    return ConsoleStream(handle)


def stream_is_console(stream) -> bool:
    """判断给定流是否直接连着控制台（而不是管道 / 文件重定向）"""
    if os.name != "nt":
        return False
    try:
        import msvcrt
        fd = stream.fileno()
        handle = msvcrt.get_osfhandle(fd)
        if handle == -1:
            return False
        kernel32 = ctypes.windll.kernel32
        kernel32.GetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetConsoleMode.restype = wintypes.BOOL
        mode = wintypes.DWORD(0)
        return bool(kernel32.GetConsoleMode(ctypes.c_void_p(handle), ctypes.byref(mode)))
    except Exception:
        return False


def setup_console_stream():
    """
    获取可用于终端回显的输出流。

    - 控制台直接输出（cmd / Windows Terminal）：走 WriteConsoleW，Unicode 输出，
      不受控制台代码页影响；
    - 管道 / 重定向（IDE、日志收集、Git Bash 等）：统一切到 UTF-8，避免 GBK 乱码；
    - 打包为窗口程序（console=False）且 sys.stdout 为空：AttachConsole 附着到
      启动它的那个控制台后再输出。
    """
    global CONSOLE_STREAM

    out = sys.stdout
    if out is not None:
        try:
            out.write("")
            out.flush()
        except Exception:
            out = None

    # 情况 1：stdout 是管道 / 文件 —— 统一按 UTF-8 输出
    if out is not None and not stream_is_console(out):
        try:
            out.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
        CONSOLE_STREAM = out
        return out

    if os.name != "nt":
        CONSOLE_STREAM = out
        return out

    # 情况 2/3：控制台直连，或窗口程序没有 stdout —— 用 WriteConsoleW 输出
    try:
        kernel32 = ctypes.windll.kernel32
        # 窗口程序启动时没有控制台，需要附着到启动它的那个控制台；
        # 已经是控制台程序时 AttachConsole 会失败（已有控制台），忽略即可。
        kernel32.AttachConsole(-1)   # ATTACH_PARENT_PROCESS

        stream = open_console_stream() or out
        if stream is None:
            # 兜底：按控制台代码页写字节
            cp = kernel32.GetConsoleOutputCP()
            encoding = {65001: "utf-8", 936: "gbk", 54936: "gbk"}.get(cp, f"cp{cp}")
            try:
                stream = open("CONOUT$", "w", encoding=encoding, errors="replace", buffering=1)
            except LookupError:
                stream = open("CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1)
            except OSError:
                return None   # 没有任何控制台（双击启动）

        CONSOLE_STREAM = stream
        if sys.stdout is None:
            sys.stdout = stream
        if sys.stderr is None:
            sys.stderr = stream
        return stream
    except Exception:
        CONSOLE_STREAM = out
        return out


def console_write(text: str):
    """把一行文本回显到终端（无控制台时静默忽略）"""
    stream = CONSOLE_STREAM
    if stream is None:
        return
    try:
        stream.write(text if text.endswith("\n") else text + "\n")
        stream.flush()
    except (OSError, ValueError, AttributeError):
        pass


CONSOLE_STREAM = setup_console_stream()


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

    # 控制台输出（v0.1.3：窗口程序附着父控制台后就可用）
    if CONSOLE_STREAM is not None:
        ch = logging.StreamHandler(CONSOLE_STREAM)
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
    "focus_game": {
        "enabled": True,
        "trigger_keywords": ["不是原神", "暂停"],
        "delay_seconds": 3,
        "cooldown_seconds": 30,
        "retry_times": 6,
        "retry_interval_seconds": 5,
        "cancel_key": "F12"
    },
    "restart": {
        "enabled": True,
        "max_restarts": 3,
        "delay_seconds": 20,
        "require_game_running": True,
        "restart_on_clean_exit": False,
        "crash_keywords": [
            "Fatal error",
            "Unhandled exception",
            "AccessViolationException",
            "Attempted to read or write protected memory",
            "StackOverflowException",
            "OutOfMemoryException"
        ],
        "completion_keywords": [
            "一条龙和配置组任务结束",
            "主窗体退出"
        ]
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
    返回: (major, minor, days_since_start)  0 表示版本更新当天
    """
    delta = (target_date - BASE_DATE).days
    version_offset, day_in_version = divmod(delta, VERSION_CYCLE)

    major = BASE_VERSION[0]
    minor = BASE_VERSION[1] + version_offset

    # 处理 minor 溢出（每 10 个小版本进位 / 借位）
    while minor < 0:
        major -= 1
        minor += 10
    while minor >= 10:
        major += 1
        minor -= 10

    return major, minor, day_in_version


def get_version_start_date(major, minor):
    """获取指定版本开始日期"""
    offset = (major - BASE_VERSION[0]) * 10 + (minor - BASE_VERSION[1])
    return BASE_DATE + timedelta(days=offset * VERSION_CYCLE)


def get_burst_window(major, minor):
    """
    获取指定版本的紊乱爆发期区间。
    返回: (开始 datetime, 结束 datetime) —— 结束时刻为开区间，即最后一天 03:59 结束。
    """
    start_date = get_version_start_date(major, minor)
    burst_start = datetime.combine(
        start_date + timedelta(days=BURST_START_DAY), dtime(BURST_START_HOUR, 0)
    )
    burst_end = datetime.combine(
        start_date + timedelta(days=BURST_END_DAY), dtime(BURST_END_HOUR, 0)
    )
    return burst_start, burst_end


def is_burst_period(now_dt: datetime, config: dict = None):
    """
    以“实际启动游戏的时刻”判断是否处于紊乱爆发期（精确到分钟）。

    返回: (是否爆发期, 版本信息字符串, 说明)
    """
    major, minor, day_in = get_version_info(now_dt.date())
    version_str = f"{major}.{minor}"
    burst_start, burst_end = get_burst_window(major, minor)
    last_minute = burst_end - timedelta(minutes=1)

    if now_dt < burst_start:
        if day_in == 0:
            return False, version_str, (
                f"版本更新日（版本内第 {day_in + 1} 天），"
                f"紊乱爆发期尚未开始（{burst_start:%m-%d %H:%M} 开启），使用常规配置"
            )
        return False, version_str, (
            f"非爆发期（版本内第 {day_in + 1} 天），"
            f"紊乱爆发期将于 {burst_start:%m-%d %H:%M} 开始，使用常规配置"
        )

    if now_dt < burst_end:
        return True, version_str, (
            f"紊乱爆发期（版本内第 {day_in + 1} 天，至 {last_minute:%m-%d %H:%M} 结束），"
            f"使用爆发期配置"
        )

    return False, version_str, (
        f"非爆发期（版本内第 {day_in + 1} 天），"
        f"紊乱爆发期已于 {last_minute:%m-%d %H:%M} 结束，使用常规配置"
    )


def is_update_day(target_date: date):
    """判断是否为版本更新日"""
    _major, _minor, day_in = get_version_info(target_date)
    return day_in == 0


def is_maintenance_time(now_dt: datetime = None):
    """判断当前是否在版本更新日的停服维护窗口内（06:00 ~ 11:00）"""
    now_dt = now_dt or datetime.now()
    return MAINTENANCE_START_HOUR <= now_dt.hour < SERVER_OPEN_HOUR


def log_version_context(now_dt: datetime, config: dict):
    """输出一次完整的版本 / 爆发期上下文，便于事后核对判定依据"""
    major, minor, day_in = get_version_info(now_dt.date())
    version_start = get_version_start_date(major, minor)
    burst_start, burst_end = get_burst_window(major, minor)

    logger.info(f"时间基准: {now_dt:%Y-%m-%d %H:%M:%S}（读取系统时间，精确到分钟）")
    logger.info(f"当前版本: {major}.{minor}（版本内第 {day_in + 1} 天 / 共 {VERSION_CYCLE} 天）")
    logger.info(
        f"版本更新: {version_start:%Y-%m-%d} "
        f"{MAINTENANCE_START_HOUR:02d}:00 停服维护，预计 {SERVER_OPEN_HOUR:02d}:00 开服"
    )
    logger.info(
        f"紊乱爆发期: {burst_start:%Y-%m-%d %H:%M} ~ "
        f"{(burst_end - timedelta(minutes=1)):%Y-%m-%d %H:%M}"
    )

    if config is not None and not config.get("special_rules", {}).get(
        "burst_first_day_as_normal", True
    ):
        logger.warning(
            "special_rules.burst_first_day_as_normal = false 已不再生效："
            "爆发期严格以真实时间 10:00 为起点，10:00 之前始终使用常规配置"
        )


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


def is_game_running(config: dict) -> bool:
    """判断原神进程是否在运行（兼容国服 YuanShen.exe / 国际服 GenshinImpact.exe）"""
    game_proc = config.get("pre_launch_check", {}).get("game_process", "Yuanshen.exe")
    for name in {game_proc, "YuanShen.exe", "GenshinImpact.exe"}:
        if is_process_running(name):
            return True
    return False


def wait_before_restart(config: dict, seconds: float, rcfg: dict):
    """
    重启前的等待（v0.1.4）。

    等待期间若游戏被关闭，则放弃重启 —— 否则会把用户主动退出的游戏又拉起来。
    返回: (是否继续重启, 放弃原因)
    """
    require_game = bool((rcfg or {}).get("require_game_running", True))
    deadline = time.monotonic() + max(0.0, seconds)
    while time.monotonic() < deadline:
        if require_game and not is_game_running(config):
            return False, "等待期间游戏已退出（判定为用户主动收尾）"
        time.sleep(min(1.0, max(0.05, deadline - time.monotonic())))
    if require_game and not is_game_running(config):
        return False, "重启前游戏已退出（判定为用户主动收尾）"
    return True, ""


# ============================================================
# 窗口前台切换（v0.1.3）
# ============================================================
def _enum_top_level_windows():
    """枚举所有顶层窗口句柄"""
    user32 = ctypes.windll.user32
    hwnds = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def _callback(hwnd, _lparam):
        hwnds.append(hwnd)
        return True

    user32.EnumWindows(WNDENUMPROC(_callback), 0)
    return hwnds


def find_game_window(game_process: str = "Yuanshen.exe"):
    """
    查找原神主窗口句柄：按进程 PID 匹配顶层可见窗口，取面积最大的那个。
    兼容国服 YuanShen.exe 与国际服 GenshinImpact.exe。
    """
    pids = set()
    for name in {game_process, "YuanShen.exe", "GenshinImpact.exe"}:
        pids.update(get_process_pids(name))
    if not pids:
        return None

    user32 = ctypes.windll.user32
    best_hwnd, best_area = None, -1

    for hwnd in _enum_top_level_windows():
        try:
            if not user32.IsWindowVisible(hwnd):
                continue
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value not in pids:
                continue
            if user32.GetWindowTextLengthW(hwnd) <= 0:
                continue
            rect = wintypes.RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                continue
            area = max(0, rect.right - rect.left) * max(0, rect.bottom - rect.top)
            if area > best_area:
                best_hwnd, best_area = hwnd, area
        except Exception:
            continue

    return best_hwnd


def bring_window_to_foreground(hwnd, retries: int = 3) -> bool:
    """
    把指定窗口切到前台。

    Windows 有前台锁定（foreground lock），普通 SetForegroundWindow 常常无效，
    这里组合使用 AttachThreadInput + SetForegroundWindow + SwitchToThisWindow 提高成功率。
    """
    if not hwnd:
        return False

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    try:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)   # SW_RESTORE
        else:
            user32.ShowWindow(hwnd, 5)   # SW_SHOW
    except Exception:
        pass

    for _ in range(max(1, retries)):
        try:
            if user32.GetForegroundWindow() == hwnd:
                return True

            cur_tid = kernel32.GetCurrentThreadId()
            fg_hwnd = user32.GetForegroundWindow()
            fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0

            attached = False
            if fg_tid and fg_tid != cur_tid:
                attached = bool(user32.AttachThreadInput(cur_tid, fg_tid, True))
            try:
                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)
                user32.SetActiveWindow(hwnd)
                user32.SetFocus(hwnd)
            finally:
                if attached:
                    user32.AttachThreadInput(cur_tid, fg_tid, False)

            # 兜底：未公开但常用的切换接口
            try:
                user32.SwitchToThisWindow(hwnd, True)
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"切换窗口到前台出错: {e}")

        time.sleep(0.3)
        try:
            if user32.GetForegroundWindow() == hwnd:
                return True
        except Exception:
            break

    return False


# ============================================================
# 焦点守护：日志出现“不是原神 …… 暂停”时把原神切到前台（v0.1.3）
# ============================================================
class FocusGuard:
    """
    监听 BetterGI 日志：出现“不是原神 …… 暂停”时，延迟若干秒把原神窗口切到前台。
    运行期按 cancel_key（默认 F12）可取消 / 恢复该功能，状态不写入配置文件。
    """

    def __init__(self, config: dict, game_process: str = "Yuanshen.exe", writer=None):
        cfg = (config or {}).get("focus_game", {}) or {}
        self.config_enabled = bool(cfg.get("enabled", True))
        keywords = cfg.get("trigger_keywords") or ["不是原神", "暂停"]
        self.keywords = [str(k) for k in keywords if str(k).strip()]
        self.delay = max(0.0, float(cfg.get("delay_seconds", 3) or 0))
        self.cooldown = max(0.0, float(cfg.get("cooldown_seconds", 30) or 0))
        self.retries = max(1, int(cfg.get("retry_times", 6) or 1))
        self.retry_interval = max(1.0, float(cfg.get("retry_interval_seconds", 5) or 5))

        key_name = str(cfg.get("cancel_key", "F12") or "F12").strip().upper()
        self.cancel_key_name = key_name if key_name in VK_CODES else "F12"
        self.cancel_vk = VK_CODES[self.cancel_key_name]

        self.game_process = game_process
        self.writer = writer

        self._lock = threading.Lock()
        self._armed = True
        self._busy = False
        self._last_trigger = 0.0
        self._cancel_event = threading.Event()
        self._stop_event = threading.Event()
        self._hotkey_thread = None

        self.trigger_count = 0
        self.focus_count = 0

    # ---------- 日志辅助 ----------
    def _note(self, level: int, message: str):
        logger.log(level, message)
        if self.writer is not None:
            self.writer.comment(message)

    # ---------- 生命周期 ----------
    def start(self):
        if not self.config_enabled:
            logger.info("自动切前台已禁用（focus_game.enabled = false）")
            return
        self._stop_event.clear()
        self._hotkey_thread = threading.Thread(
            target=self._hotkey_loop, daemon=True, name="FocusGuardHotkey"
        )
        self._hotkey_thread.start()
        logger.info(
            f"自动切前台已启用：日志出现“{' / '.join(self.keywords)}”时切换到原神窗口；"
            f"运行期按 {self.cancel_key_name} 取消 / 恢复（不写入配置文件）"
        )

    def stop(self):
        self._stop_event.set()
        self._cancel_event.set()
        thread = self._hotkey_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2)

    # ---------- 热键 ----------
    def _hotkey_loop(self):
        try:
            user32 = ctypes.windll.user32
        except Exception:
            return
        prev_pressed = False
        while not self._stop_event.is_set():
            try:
                pressed = bool(user32.GetAsyncKeyState(self.cancel_vk) & 0x8000)
            except Exception:
                pressed = False
            if pressed and not prev_pressed:
                self._toggle()
            prev_pressed = pressed
            time.sleep(0.05)

    def _toggle(self):
        with self._lock:
            self._armed = not self._armed
            armed = self._armed
        if not armed:
            self._cancel_event.set()
            self._note(
                logging.WARNING,
                f"按下 {self.cancel_key_name}：已取消自动切前台"
                f"（本次运行内不再自动切换，再按一次可恢复）",
            )
        else:
            self._cancel_event.clear()
            self._note(logging.INFO, f"按下 {self.cancel_key_name}：已恢复自动切前台")

    # ---------- 触发 ----------
    @staticmethod
    def _normalize(text: str) -> str:
        """去掉空白与常见中英文标点，便于跨格式匹配"""
        return re.sub(r"[\s，。！？、：；,.!?:;\"'“”‘’（）()\[\]【】<>《》]", "", text or "")

    def _is_trigger(self, line: str) -> bool:
        if not self.keywords:
            return False
        text = self._normalize(line)
        return all(self._normalize(kw) in text for kw in self.keywords)

    def feed(self, line: str):
        """由日志采集层回调：每收到一行 BetterGI 日志调用一次"""
        if not self.config_enabled or not line:
            return
        with self._lock:
            if not self._armed or self._busy:
                return
            now = time.monotonic()
            if now - self._last_trigger < self.cooldown:
                return
            if not self._is_trigger(line):
                return
            self._last_trigger = now
            self._busy = True
        threading.Thread(target=self._do_focus, daemon=True, name="FocusGuardWorker").start()

    # ---------- 切前台 ----------
    def _sleep_cancellable(self, seconds: float) -> bool:
        """可被 F12 / 停止信号打断的等待；返回 True 表示被取消"""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if (self._stop_event.is_set() or self._cancel_event.is_set()
                    or not self._armed):
                return True
            time.sleep(0.1)
        return False

    def _do_focus(self):
        try:
            self._cancel_event.clear()
            self.trigger_count += 1
            self._note(
                logging.WARNING,
                "BetterGI 报告当前焦点窗口不是原神（日志命中“不是原神 … 暂停”），"
                "准备把原神切到前台",
            )

            if self.delay > 0:
                self._note(
                    logging.INFO,
                    f"{self.delay:g} 秒后把原神切到前台，按 {self.cancel_key_name} 可取消",
                )
                if self._sleep_cancellable(self.delay):
                    self._cancel_event.clear()
                    if self._stop_event.is_set():
                        return
                    self._note(logging.INFO, "已取消本次切换原神到前台")
                    return

            hwnd = None
            for attempt in range(1, self.retries + 1):
                hwnd = find_game_window(self.game_process)
                if hwnd:
                    break
                if attempt < self.retries:
                    self._note(
                        logging.INFO,
                        f"暂未找到原神窗口（第 {attempt}/{self.retries} 次），"
                        f"{self.retry_interval:g} 秒后重试",
                    )
                    if self._sleep_cancellable(self.retry_interval):
                        self._cancel_event.clear()
                        if self._stop_event.is_set():
                            return
                        self._note(logging.INFO, "已取消本次切换原神到前台")
                        return

            if not hwnd:
                self._note(
                    logging.WARNING,
                    f"未找到原神窗口（进程 {self.game_process} 未运行或无可切窗口），放弃本次切换",
                )
                return

            if bring_window_to_foreground(hwnd, retries=3):
                self.focus_count += 1
                self._note(logging.INFO, f"已把原神窗口切到前台（HWND=0x{int(hwnd):X}）")
            else:
                self._note(
                    logging.WARNING,
                    "尝试把原神切到前台失败（可能受系统前台锁定或独占全屏影响）",
                )
        except Exception as e:
            logger.exception(f"自动切前台出错: {e}")
        finally:
            with self._lock:
                self._busy = False


# ============================================================
# BetterGI 启动
# ============================================================
def launch_bettergi(config: dict, config_name: str):
    """
    启动 BetterGI 并指定一条龙配置。

    返回: (是否成功, Popen 对象或 None)
    注意：stdout/stderr 必须由调用方持续读取（本项目由 BgiStdoutReader 的读取线程负责），
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
    """
    线程安全的合并日志写入器。

    同时承担两件事：
      1. 把 BetterGI 原始日志写入合并日志文件；
      2. 按需回显到终端（v0.1.3），并把原始行交给监听回调（例如 FocusGuard）。
    """

    def __init__(self, path: Path, listeners=None):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._fh = None
        self._listeners = list(listeners or [])
        self.lines = 0
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = open(self.path, "a", encoding="utf-8", errors="replace")
        except OSError as e:
            logger.error(f"无法创建合并日志文件 {self.path}: {e}")

    def add_listener(self, callback):
        """注册“收到一行 BetterGI 原始日志”的回调"""
        if callback is not None:
            self._listeners.append(callback)

    def remove_listener(self, callback):
        """注销回调（重启监听时避免重复注册）"""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def write(self, text: str, echo: bool = False, notify: bool = True):
        line = text.rstrip("\r\n")
        if self._fh is not None:
            with self._lock:
                try:
                    self._fh.write(line + "\n")
                    self._fh.flush()
                    self.lines += 1
                except (OSError, ValueError) as e:
                    logger.error(f"写入合并日志失败: {e}")

        if echo:
            console_write(line)

        if notify and self._listeners:
            for callback in list(self._listeners):
                try:
                    callback(line)
                except Exception as e:
                    logger.debug(f"日志监听回调出错: {e}")

    def comment(self, text: str):
        """写入一条带时间戳的说明行（便于日后阅读合并日志），不触发监听回调"""
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.write(f"#### [{stamp}] {text}", echo=False, notify=False)

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
    后台线程：持续读取 BetterGI 子进程的终端输出，写入合并日志，
    并在检测到控制台时同步回显到当前终端（v0.1.3）。
    """

    def __init__(self, stream, writer: MergedLogWriter, tag: str = "stdout", echo: bool = True):
        super().__init__(daemon=True, name="BgiStdoutReader")
        self._stream = stream
        self._writer = writer
        self._tag = tag
        self.echo = echo and CONSOLE_STREAM is not None
        self.lines = 0

    def run(self):
        try:
            for raw in iter(self._stream.readline, b""):
                line = decode_output(raw).rstrip("\r\n")
                if not line:
                    continue
                self._writer.write(line, echo=self.echo)
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

    def __init__(self, bgi_path: str, writer: MergedLogWriter, baseline=None, echo: bool = False):
        self.log_dir = get_bgi_log_dir(bgi_path)
        self.writer = writer
        self.echo = echo and CONSOLE_STREAM is not None
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
            self.writer.write(line, echo=self.echo)
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


class MonitorOutcome:
    """一次监听的结果，供重启判定使用"""

    def __init__(self, reason, exit_code, completed, crash, killed, elapsed, lines):
        self.reason = reason
        self.exit_code = exit_code
        self.completed = completed
        self.crash = crash
        self.killed = killed
        self.elapsed = elapsed
        self.lines = lines

    def __str__(self):
        parts = [self.reason, f"退出码 {self.exit_code}"]
        if self.completed:
            parts.append("任务已完成")
        if self.crash:
            parts.append("检测到崩溃特征")
        if self.killed:
            parts.append("启动器主动终止")
        return "，".join(parts)


def monitor_bettergi(config: dict, bgi_path: str, proc, writer: MergedLogWriter,
                     baseline=None, pending_kill=None):
    """
    持续监听 BetterGI：采集终端输出（主）+ 日志文件（兜底），
    直到 BetterGI 进程被关闭（或触发更新日终止、或超过最大监听时长）。

    同时顺带判断本次退出是“任务已完成”还是“异常/崩溃退出”，
    返回 MonitorOutcome 供上层决定是否重启（v0.1.4）。
    """
    mon = config.get("monitor", {})
    rcfg = config.get("restart", {}) or {}
    bgi_proc = config.get("pre_launch_check", {}).get("bgi_process", "BetterGI.exe")
    interval = max(0.2, float(mon.get("poll_interval_seconds", 2) or 2))
    startup_timeout = float(mon.get("startup_timeout_seconds", 120) or 0)
    max_hours = float(mon.get("max_duration_hours", 12) or 0)
    capture_stdout = bool(mon.get("capture_stdout", True))
    follow_file = bool(mon.get("follow_log_file", False))
    file_fallback = bool(mon.get("follow_log_file_fallback", True))
    stdout_grace = float(mon.get("stdout_grace_seconds", 20) or 0)

    crash_keywords = [str(k) for k in (rcfg.get("crash_keywords") or []) if str(k).strip()]
    completion_keywords = [str(k) for k in (rcfg.get("completion_keywords") or []) if str(k).strip()]

    # 最近若干行日志，用于判断崩溃 / 完成
    recent_lines = collections.deque(maxlen=600)
    state = {"completed": False, "crash": False}

    def _record(line: str):
        recent_lines.append(line)
        if not state["completed"] and any(k in line for k in completion_keywords):
            state["completed"] = True
        if not state["crash"] and any(k.lower() in line.lower() for k in crash_keywords):
            state["crash"] = True
            logger.warning(f"BetterGI 日志出现崩溃特征: {line[:160]}")

    writer.add_listener(_record)

    reader = None
    if capture_stdout and proc is not None and proc.stdout is not None:
        reader = BgiStdoutReader(proc.stdout, writer, echo=True)
        reader.start()
        logger.info("已启动终端输出采集线程（BetterGI stdout）")
        if reader.echo:
            logger.info("终端回显: 已开启，BetterGI 日志将同步打印到当前终端")
    else:
        logger.info("终端输出采集已关闭")

    follower = None
    if follow_file:
        follower = BgiLogFollower(bgi_path, writer, baseline, echo=(reader is None))
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
                follower = BgiLogFollower(
                    bgi_path, writer, baseline,
                    echo=(reader is None or reader.lines == 0)
                )
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
        # 收尾：再抓一次日志，等待采集线程退出（要把崩溃前最后几行收完）
        if follower:
            try:
                follower.poll()
            except Exception:
                pass
        if reader is not None:
            reader.join(timeout=5)
        if follower:
            follower.close()
        writer.remove_listener(_record)

    # proc 退出码（若子进程已结束）
    exit_code = proc.poll() if proc is not None else None
    elapsed = time.monotonic() - start

    # 崩溃特征也可能只出现在日志文件里，这里再兜一遍
    for line in reversed(recent_lines):
        if any(k.lower() in line.lower() for k in crash_keywords):
            state["crash"] = True
            break

    writer.comment(f"监听结束：{reason}；合并日志行数 {writer.lines}")
    logger.info(
        f"监听结束 -> {reason}，合并日志行数 {writer.lines}"
        + (f"，子进程退出码 {exit_code}" if exit_code is not None else "")
    )
    logger.info(
        f"本次退出判定：任务完成={state['completed']}，"
        f"崩溃特征={state['crash']}，主动终止={killed}"
    )
    return MonitorOutcome(reason, exit_code, state["completed"], state["crash"],
                          killed, elapsed, writer.lines)


def evaluate_restart(config: dict, outcome: MonitorOutcome, attempt: int,
                     session_start: float):
    """
    判断是否需要重启 BetterGI（v0.1.4）。

    返回: (是否重启, 原因说明)
    """
    rcfg = config.get("restart", {}) or {}
    if not rcfg.get("enabled", True):
        return False, "自动重启已禁用（restart.enabled = false）"

    if outcome.killed:
        return False, "本次退出由启动器主动终止（更新日规则），不重启"

    if outcome.completed:
        return False, "一条龙任务已完成（命中完成标记），不重启"

    if "未检测到" in outcome.reason:
        return False, "BetterGI 未能成功启动，不自动重启"

    max_restarts = max(0, int(rcfg.get("max_restarts", 3) or 0))
    if attempt >= max_restarts:
        return False, f"已达最大重启次数 {max_restarts}"

    max_hours = float(config.get("monitor", {}).get("max_duration_hours", 12) or 0)
    if max_hours > 0 and (time.monotonic() - session_start) > max_hours * 3600:
        return False, f"本次运行已超过最大时长 {max_hours:g} 小时，不再重启"

    # 游戏已经退出：多半是正常收尾或用户主动关闭，重启会把游戏又拉起来
    if rcfg.get("require_game_running", True):
        game_proc = config.get("pre_launch_check", {}).get("game_process", "Yuanshen.exe")
        if not is_process_running(game_proc):
            return False, f"游戏进程 {game_proc} 已退出，判定为收尾 / 手动关闭，不重启"

    clean_exit = outcome.exit_code in (0, None) and not outcome.crash
    if clean_exit and not rcfg.get("restart_on_clean_exit", False):
        return False, f"BetterGI 正常退出（退出码 {outcome.exit_code}，无崩溃特征），不重启"

    if outcome.crash:
        return True, "BetterGI 崩溃退出（日志出现 Fatal error 等致命错误）且任务未完成"
    if clean_exit:
        return True, "已开启 restart_on_clean_exit，BetterGI 正常退出也按任务未完成重启"
    return True, f"BetterGI 异常退出（退出码 {outcome.exit_code}）且任务未完成"


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

    hwnd = find_game_window(game_proc)
    if hwnd:
        logger.info(f"原神主窗口: HWND=0x{int(hwnd):X}")
    else:
        logger.info("原神主窗口: 未找到（游戏未运行或窗口尚未创建）")

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
    logger.info(f"终端回显: {'已启用' if CONSOLE_STREAM is not None else '未检测到控制台'}")


def test_time(config: dict):
    """测试模式：验证版本 / 紊乱爆发期时间判定"""
    logger.info("=" * 50)
    logger.info("[测试模式] testtime - 验证版本与紊乱爆发期判定")
    logger.info("=" * 50)

    now_dt = datetime.now()
    major, minor, day_in = get_version_info(now_dt.date())
    burst_start, burst_end = get_burst_window(major, minor)
    mapping = config.get("config_name_mapping", {})

    logger.info(f"当前系统时间: {now_dt:%Y-%m-%d %H:%M:%S}")
    logger.info(f"当前版本: {major}.{minor}（版本内第 {day_in + 1} 天 / 共 {VERSION_CYCLE} 天）")
    logger.info(
        f"版本更新: {get_version_start_date(major, minor):%Y-%m-%d} "
        f"{MAINTENANCE_START_HOUR:02d}:00 停服维护，预计 {SERVER_OPEN_HOUR:02d}:00 开服"
    )
    logger.info(
        f"紊乱爆发期: {burst_start:%Y-%m-%d %H:%M} ~ "
        f"{(burst_end - timedelta(minutes=1)):%Y-%m-%d %H:%M}"
    )

    burst, _ver, reason = is_burst_period(now_dt, config)
    name = mapping.get("burst" if burst else "normal", "wz" if burst else "dm")
    logger.info(f"判定结果: {reason} -> 一条龙配置 {name}")

    logger.info("-" * 50)
    logger.info("后续版本时间表（供核对）:")
    base_start = get_version_start_date(major, minor)
    for i in range(4):
        ver_start = base_start + timedelta(days=i * VERSION_CYCLE)
        v_major, v_minor, _ = get_version_info(ver_start)
        b_start, b_end = get_burst_window(v_major, v_minor)
        logger.info(
            f"  {v_major}.{v_minor}: 更新 {ver_start:%Y-%m-%d} "
            f"{MAINTENANCE_START_HOUR:02d}:00 / 开服约 {SERVER_OPEN_HOUR:02d}:00，"
            f"爆发期 {b_start:%m-%d %H:%M} ~ {(b_end - timedelta(minutes=1)):%m-%d %H:%M}"
        )


# ============================================================
# 主流程
# ============================================================
def main():
    logger.info("=" * 60)
    logger.info(f"{APP_NAME} v{VERSION} 启动")
    logger.info(f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    if CONSOLE_STREAM is not None:
        logger.info("终端回显: 已启用（BetterGI 运行日志将同步输出到当前终端）")
    else:
        logger.info("终端回显: 未检测到控制台（日志仅写入文件；从命令行运行可看到实时输出）")

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
    args = sys.argv[1:]

    if "testbgi" in args:
        test_bgi(config)
        return

    if "testtk" in args:
        test_taskkill(config)
        return

    if "testproc" in args:
        test_process(config)
        return

    if "testtime" in args:
        test_time(config)
        return

    # --- 正常启动流程 ---
    # v0.1.3：一切判定以“实际启动游戏的系统时间”为准，精确到分钟
    now_dt = datetime.now()
    log_version_context(now_dt, config)

    bgi_path = config.get("bettergi_path", "")

    # --- 启动前进程检查（v0.1.1）---
    pre_launch_process_check(config)

    # --- 记录 BetterGI 日志基线（仅消费本次启动后的新增日志）---
    baseline = capture_bgi_log_baseline(bgi_path)
    if baseline:
        logger.info(f"BetterGI 日志基线: {baseline[0]}（{baseline[1]} 字节）")

    # --- 判定时刻尽量贴近真正拉起 BetterGI 的时间（前面的检查可能已耗时数秒）---
    now_dt = datetime.now()
    update_day = is_update_day(now_dt.date())

    if update_day:
        logger.info(f"今天是版本更新日（{now_dt:%Y-%m-%d}）")
        if is_maintenance_time(now_dt):
            logger.info(
                f"当前仍处于停服维护窗口（{MAINTENANCE_START_HOUR:02d}:00 ~ "
                f"{SERVER_OPEN_HOUR:02d}:00），游戏尚不可登录"
            )

    # 判断爆发期（按真实时间窗口，10:00 前自然落入常规配置）
    burst, ver_str, reason = is_burst_period(now_dt, config)
    logger.info(f"启动时刻: {now_dt:%Y-%m-%d %H:%M:%S}（版本 {ver_str}）")
    logger.info(f"爆发期判定结果: {reason}")

    # 确定配置名称
    mapping = config.get("config_name_mapping", {})
    if burst:
        config_name = mapping.get("burst", "wz")
    else:
        config_name = mapping.get("normal", "dm")

    logger.info(f"使用配置名称: {config_name}（版本 {ver_str}，判定时刻 {now_dt:%H:%M:%S}）")

    # --- 更新日特殊处理（启动前先算好延迟终止计划）---
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

    # --- 持续监听 BetterGI 日志，直至进程关闭（v0.1.1）；异常退出时自动重启（v0.1.4）---
    mon = config.get("monitor", {})
    if not mon.get("enabled", True):
        success, _proc = launch_bettergi(config, config_name)
        if not success:
            logger.error("启动 BetterGI 失败，程序退出")
            sys.exit(1)
        logger.info("监听功能已禁用（monitor.enabled = false），启动完成后直接退出")
        logger.info("程序执行完毕")
        return

    merged_path = SESSION_LOG_DIR / f"bettergi-merge-{SESSION_TS}.log"
    writer = MergedLogWriter(merged_path)

    # --- 焦点守护（v0.1.3）---
    check_cfg = config.get("pre_launch_check", {})
    game_proc = check_cfg.get("game_process", "Yuanshen.exe")
    guard = FocusGuard(config, game_proc, writer)
    writer.add_listener(guard.feed)
    guard.start()

    rcfg = config.get("restart", {}) or {}
    max_restarts = max(0, int(rcfg.get("max_restarts", 3) or 0))
    restart_delay = max(0.0, float(rcfg.get("delay_seconds", 20) or 0))

    session_start = time.monotonic()
    attempt = 0
    last_outcome = None

    try:
        writer.write("# BetterGI 运行日志合并文件", notify=False)
        writer.write(f"# 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", notify=False)
        writer.write(f"# 启动器版本: v{VERSION}", notify=False)
        writer.write(f"# BetterGI: {bgi_path}", notify=False)
        writer.write(f"# 一条龙配置: {config_name}（{reason}）", notify=False)
        writer.write(f"# 判定时刻: {now_dt:%Y-%m-%d %H:%M:%S}（版本 {ver_str}）", notify=False)
        writer.write(
            f"# 崩溃自动重启: {'启用' if rcfg.get('enabled', True) else '禁用'}"
            f"（最多 {max_restarts} 次，间隔 {restart_delay:g} 秒）",
            notify=False
        )
        writer.write("# " + "=" * 58, notify=False)

        while True:
            success, proc = launch_bettergi(config, config_name)
            if not success:
                logger.error("启动 BetterGI 失败，程序退出")
                if attempt == 0:
                    sys.exit(1)
                break

            if attempt > 0:
                logger.info(f"第 {attempt}/{max_restarts} 次重启已拉起 BetterGI，PID: {proc.pid}")
                writer.comment(f"第 {attempt}/{max_restarts} 次重启，PID: {proc.pid}")

            outcome = monitor_bettergi(config, bgi_path, proc, writer,
                                       baseline=baseline, pending_kill=pending_kill)
            last_outcome = outcome
            # 更新日终止是一次性规则，重启后不再重复计时
            pending_kill = None

            need_restart, why = evaluate_restart(config, outcome, attempt, session_start)
            if not need_restart:
                logger.info(f"不自动重启：{why}")
                writer.comment(f"不自动重启：{why}")
                break

            attempt += 1
            logger.warning(
                f"BetterGI 异常退出且任务未完成 → {restart_delay:g} 秒后进行第 "
                f"{attempt}/{max_restarts} 次重启（{why}）"
            )
            writer.comment(
                f"第 {attempt}/{max_restarts} 次重启准备：{why}；等待 {restart_delay:g} 秒"
            )

            ok, abort_why = wait_before_restart(config, restart_delay, rcfg)
            if not ok:
                logger.info(f"放弃重启：{abort_why}")
                writer.comment(f"放弃重启：{abort_why}")
                break

            logger.info("重启前再次检查进程状态…")
            pre_launch_process_check(config)
            baseline = capture_bgi_log_baseline(bgi_path)
    finally:
        guard.stop()
        if guard.config_enabled:
            writer.comment(
                f"焦点守护统计：触发 {guard.trigger_count} 次，"
                f"成功切前台 {guard.focus_count} 次"
            )
            logger.info(
                f"焦点守护统计：触发 {guard.trigger_count} 次，"
                f"成功切前台 {guard.focus_count} 次"
            )
        if attempt:
            writer.comment(f"本次运行共重启 {attempt} 次")
            logger.info(f"本次运行共重启 {attempt} 次")
        writer.close()

    if last_outcome is not None:
        logger.info(f"最后一次监听结果：{last_outcome}")
    logger.info("程序执行完毕")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("用户中断")
    except Exception as e:
        logger.exception(f"未处理的异常: {e}")
        sys.exit(1)
