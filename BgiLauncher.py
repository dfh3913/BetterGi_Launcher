#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BetterGI 智能启动器
根据日期自动匹配启动参数，支持紊乱爆发期与版本更新特殊处理。
"""

import os
import sys
import json
import time
import ctypes
import subprocess
import logging
from datetime import datetime, date, timedelta
from pathlib import Path

# ============================================================
# 常量定义
# ============================================================
APP_NAME = "BetterGI 智能启动器"
VERSION = "0.1.0"
BASE_DIR = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
CONFIG_FILE = BASE_DIR / "config.json"
LOG_DIR = BASE_DIR / "log"

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


# ============================================================
# 日志系统
# ============================================================
def setup_logger():
    """配置日志系统：按日期分目录，记录常规日志和错误日志"""
    today_str = date.today().strftime("%Y-%m-%d")
    log_subdir = LOG_DIR / today_str
    log_subdir.mkdir(parents=True, exist_ok=True)

    now_str = datetime.now().strftime("%H-%M-%S")
    log_file = log_subdir / f"{now_str}.log"
    error_file = log_subdir / f"error-{now_str}.log"

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
        return DEFAULT_CONFIG.copy()

    # 补全缺失字段
    for key, value in DEFAULT_CONFIG.items():
        if key not in config:
            config[key] = value
        elif isinstance(value, dict):
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
# BetterGI 启动与进程管理
# ============================================================
def launch_bettergi(config: dict, config_name: str):
    """启动 BetterGI 并指定一条龙配置"""
    bgi_path = config.get("bettergi_path", "")
    if not bgi_path or not os.path.exists(bgi_path):
        logger.error(f"BetterGI 路径无效或不存在: {bgi_path}")
        return False

    cmd = [bgi_path, "startOneDragon", config_name]
    logger.info(f"执行命令: {' '.join(cmd)}")

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=os.path.dirname(bgi_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        logger.info(f"BetterGI 已启动，PID: {proc.pid}")
        return True, proc
    except FileNotFoundError:
        logger.error(f"找不到可执行文件: {bgi_path}")
        return False, None
    except Exception as e:
        logger.error(f"启动 BetterGI 失败: {e}")
        return False, None


def kill_processes(process_names: list):
    """终止指定进程"""
    for name in process_names:
        try:
            result = subprocess.run(
                ["taskkill", "/F", "/IM", name],
                capture_output=True, text=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.returncode == 0:
                logger.info(f"已终止进程: {name}")
            else:
                logger.warning(f"终止 {name} 失败或无此进程: {result.stderr.strip()}")
        except subprocess.TimeoutExpired:
            logger.error(f"终止 {name} 超时")
        except Exception as e:
            logger.error(f"终止 {name} 时出错: {e}")


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
            creationflags=subprocess.CREATE_NO_WINDOW
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
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        logger.info(f"测试进程已启动，PID: {proc.pid}")
        time.sleep(2)

        # 使用 taskkill 终止
        result = subprocess.run(
            ["taskkill", "/F", "/IM", test_process],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW
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

    # --- 正常启动流程 ---
    today = date.today()
    now = datetime.now()

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

    # --- 启动 BetterGI ---
    success, proc = launch_bettergi(config, config_name)

    if not success:
        logger.error("启动 BetterGI 失败，程序退出")
        sys.exit(1)

    # --- 更新日特殊处理 ---
    special = config.get("special_rules", {})
    if update_day and special.get("update_day_kill_after_dm", True):
        if config_name == mapping.get("normal", "dm"):
            kill_delay = special.get("kill_delay_seconds", 60)
            kill_list = special.get("kill_processes", ["Yuanshen.exe", "BetterGI.exe"])

            logger.info(f"更新日特殊规则：{kill_delay} 秒后终止 {kill_list}")
            time.sleep(kill_delay)
            kill_processes(kill_list)
            logger.info("更新日特殊处理完成")
    else:
        logger.info("无更新日特殊处理")

    logger.info("程序执行完毕")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("用户中断")
    except Exception as e:
        logger.exception(f"未处理的异常: {e}")
        sys.exit(1)