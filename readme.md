# BetterGI 智能启动器

> **本项目由 Kimi K3 编写的 Vibe 项目**
>
> 一个根据日期自动匹配启动参数、智能切换 BetterGI 一条龙配置、并持续监听 BetterGI 运行日志的 Windows 自动化工具。

- 当前版本：**v0.1.2**
- 适用场景：原神 7.x 版本的紊乱爆发期 / 常规期配置自动切换

---

## 📖 目录

- [项目简介](#项目简介)
- [功能特性](#功能特性)
- [系统要求](#系统要求)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
  - [1. 获取程序](#1-获取程序)
  - [2. 首次运行](#2-首次运行)
  - [3. 配置任务计划](#3-配置任务计划)
- [配置文件详解](#配置文件详解)
- [启动前进程检查](#启动前进程检查)
- [运行日志监听与合并](#运行日志监听与合并)
- [日期与版本规则](#日期与版本规则)
  - [版本周期计算](#版本周期计算)
  - [紊乱爆发期判定](#紊乱爆发期判定)
  - [版本更新日特殊处理](#版本更新日特殊处理)
- [命令行与测试模式](#命令行与测试模式)
- [日志系统](#日志系统)
- [打包指南](#打包指南)
- [常见问题 FAQ](#常见问题-faq)
- [更新日志](#更新日志)
- [开发说明](#开发说明)
- [附录：最初提示词](#附录最初提示词)
- [免责声明](#免责声明)

---

## 项目简介

**BetterGI 智能启动器** 是一个专为 [BetterGI](https://bettergi.com/)（一款原神自动化工具）设计的辅助启动程序。

原神的每个版本持续 42 天，其中包含为期 10 天的“紊乱爆发期”。在爆发期与非爆发期，玩家通常需要使用不同的 BetterGI 一条龙配置。此外，版本更新当天存在停服维护，需要特殊处理。

手动切换配置既繁琐又容易遗忘。本项目通过读取系统日期，自动计算当前版本与版本内天数，判断是否处于紊乱爆发期，并据此选择对应的配置名称启动 BetterGI。

程序执行流程：

```
管理员权限校验
   └─ 加载 config.json
        └─ 计算版本 / 判断爆发期 → 决定配置名（wz / dm）
             └─ 【v0.1.1】启动前进程检查：游戏未运行但 BetterGI 残留 → 先 taskkill
                  └─ 记录 BetterGI 日志文件基线
                       └─ 启动 BetterGI.exe startOneDragon <配置名>
                            └─ 【v0.1.1】持续监听（终端输出 + 日志文件兜底）并合并写入日志
                                 └─ 直至 BetterGI 进程关闭（或更新日延迟终止到期）→ 收尾退出
```

本项目由 **Kimi K3** 以 Vibe 编程方式生成，代码简洁、易于维护，适合无人值守的自动化场景。

---

## 功能特性

- ✅ **自动版本计算**：基于原神 7.0 版本（2026-08-12）为基准，自动推算任意日期的版本号与版本内天数。
- ✅ **紊乱爆发期识别**：准确判断爆发期，自动切换 `wz` / `dm` 配置。
- ✅ **爆发期第一天可配置**：默认将爆发期第一天视为非爆发期，可在配置文件中修改。
- ✅ **版本更新日特殊处理**：更新当天启动 `dm` 后，延迟指定秒数自动终止游戏与 BetterGI 进程。
- ✅ **启动前进程检查**（v0.1.1）：启动前检查 `Yuanshen.exe` / `BetterGI.exe` 运行状态，若游戏未运行而 BetterGI 残留，先 `taskkill` 清理再启动，避免新一轮任务被前一天的残留进程卡住。
- ✅ **持续日志监听与合并**（v0.1.1）：命令行启动的 BetterGI 会把运行日志打印到终端，启动器持续读取该终端输出（并支持日志文件跟随兜底），实时合并写入日志目录，直至 BetterGI 进程关闭才退出。
- ✅ **UAC 权限保护**：启动时检测管理员权限，若无权限则弹窗提示并退出，确保任务计划程序以最高权限运行。
- ✅ **首次运行引导**：自动创建配置文件，并弹出文件选择对话框让用户选择 `BetterGI.exe` 路径。
- ✅ **完整日志系统**：按日期分目录记录日志，常规日志、错误日志、BetterGI 合并日志分离，便于排查问题。
- ✅ **测试模式**：内置 `testbgi` / `testtk` / `testproc` 参数，可快速验证 BetterGI 唤起、taskkill、进程检测与日志路径。
- ✅ **高度可配置**：配置名称、进程检查规则、监听策略、爆发期规则、终止进程列表、延迟时间等均可通过 `config.json` 调整。
- ✅ **单文件打包**：支持 PyInstaller 打包为独立 exe，附带自定义图标。

---

## 系统要求

| 项目            | 要求                                                                                                                              |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| 操作系统          | Windows 10 / Windows 11                                                                                                         |
| 运行权限          | **管理员权限**（必需，用于 taskkill 终止游戏 / BetterGI 进程）                                                                                    |
| Python 版本（开发） | Python 3.8 或更高                                                                                                                  |
| BetterGI 版本   | 0.45.3 及以上（支持 `startOneDragon <配置名称>`）                                                                                          |
| 依赖库           | 标准库（`csv`, `ctypes`, `io`, `json`, `logging`, `os`, `subprocess`, `sys`, `threading`, `time`, `datetime`, `pathlib`, `tkinter`） |

> **注意**：`tkinter` 用于首次运行时的文件选择对话框，Windows 官方 Python 安装包默认包含。若使用精简版 Python，请确保安装 `tkinter`。

---

## 项目结构

```
BgiLauncher/
├── BgiLauncher.py                 # 主程序源码
├── config.json                    # 配置文件（首次运行自动生成）
├── readme.md                      # 本说明文档
├── BetterGI_Launcher.spec         # PyInstaller 打包脚本
├── BlackScreen_240x240_32bit.ico  # 程序图标
├── .gitignore                     # 忽略 build/ dist/ log/ 等产物
├── log/                           # 运行日志目录（自动创建，已被 git 忽略）
│   └── 2026-10-05/
│       ├── 22-50-15.log                 # 启动器常规日志
│       ├── error-22-50-15.log           # 启动器错误日志
│       └── bettergi-merge-22-50-15.log  # BetterGI 运行日志合并文件（v0.1.1）
└── dist/
    └── BetterGI_Launcher.exe      # 打包后的可执行文件
```

---

## 快速开始

### 1. 获取程序

**方式一：直接下载打包好的 exe**

从发布页面下载 `BetterGI_Launcher.exe`，放置于任意目录（建议单独建文件夹，例如 `D:\Tools\BetterGI_Launcher\`）。

**方式二：从源码运行**

确保已安装 Python 3.8+，然后以管理员身份打开终端并执行：

```bash
python BgiLauncher.py
```

**方式三：自行打包**

参考 [打包指南](#打包指南)。

### 2. 首次运行

1. **右键点击** `BetterGI_Launcher.exe`，选择 **“以管理员身份运行”**。
2. 程序启动后，若未找到 `config.json`，会自动创建默认配置，并弹出文件选择对话框。
3. 在对话框中定位到你的 `BetterGI.exe`，例如：
   ```
   D:\Tools\Mhy tools\BetterGI\BetterGI.exe
   ```
4. 选择完成后，程序保存配置并立即执行一次启动流程。
5. 程序会在同目录下创建 `log` 文件夹，并写入本次运行日志与 BetterGI 合并日志。

> **提示**：如果未选择文件或路径无效，程序会记录错误日志并退出。你可以手动编辑 `config.json` 修正路径。

### 3. 配置任务计划

为了实现每日 7:20 自动运行：

1. 打开 **任务计划程序**（Task Scheduler）。
2. 点击 **“创建任务”**（不是“创建基本任务”）。
3. **常规**选项卡：
   - 名称：`BetterGI 智能启动器`
   - 勾选 **“使用最高权限运行”**（至关重要，否则会因缺少 UAC 权限而弹窗退出）。
   - 配置：选择你的 Windows 版本。
4. **触发器**选项卡：
   - 新建触发器 → 每天 → 开始时间设置为 `07:20:00`。
   - 勾选 **“启用”**。
5. **操作**选项卡：
   - 新建操作 → 启动程序 → 程序或脚本：选择 `BetterGI_Launcher.exe` 的完整路径。
   - 起始于（可选）：填写 exe 所在目录，例如 `D:\Tools\BetterGI_Launcher\`。
6. **条件**选项卡：
   - 取消勾选 **“只有在计算机使用交流电源时才启动此任务”**（如果是笔记本）。
   - 根据需求勾选 **“如果计算机空闲则启动”** 等。
7. **设置**选项卡：
   - 勾选 **“如果任务失败，按以下频率重新启动”**，可设置 1 分钟、3 次。
   - **务必取消勾选 “如果任务运行时间超过以下时间，停止任务”**。v0.1.1 起启动器会常驻运行直至 BetterGI 关闭（可能长达数小时），若保留该限制会导致监听被强行掐断。
8. 保存任务。可右键手动运行一次进行测试。

---

## 配置文件详解

首次运行自动生成 `config.json`，内容如下：

```json
{
  "bettergi_path": "D:\\Tools\\Mhy tools\\BetterGI\\BetterGI.exe",
  "config_name_mapping": {
    "burst": "wz",
    "normal": "dm"
  },
  "pre_launch_check": {
    "enabled": true,
    "bgi_process": "BetterGI.exe",
    "game_process": "Yuanshen.exe",
    "kill_bgi_if_game_absent": true,
    "wait_after_kill_seconds": 3
  },
  "monitor": {
    "enabled": true,
    "poll_interval_seconds": 2,
    "startup_timeout_seconds": 120,
    "max_duration_hours": 12,
    "capture_stdout": true,
    "follow_log_file": false,
    "follow_log_file_fallback": true,
    "stdout_grace_seconds": 20
  },
  "special_rules": {
    "burst_first_day_as_normal": true,
    "update_day_kill_after_dm": true,
    "kill_delay_seconds": 60,
    "kill_processes": ["Yuanshen.exe", "BetterGI.exe"]
  }
}
```

### 字段说明

| 字段路径                                       | 类型     | 默认值                                | 说明                                           |
| ------------------------------------------ | ------ | ---------------------------------- | -------------------------------------------- |
| `bettergi_path`                            | string | `""`                               | `BetterGI.exe` 的完整路径。首次运行时会弹出文件选择对话框，也可手动编辑。 |
| `config_name_mapping.burst`                | string | `"wz"`                             | 紊乱爆发期使用的 BetterGI 一条龙配置名称。                   |
| `config_name_mapping.normal`               | string | `"dm"`                             | 非爆发期使用的配置名称。                                 |
| `pre_launch_check.enabled`                 | bool   | `true`                             | 是否启用启动前进程检查。                                 |
| `pre_launch_check.bgi_process`             | string | `"BetterGI.exe"`                   | BetterGI 的进程映像名称。                            |
| `pre_launch_check.game_process`            | string | `"Yuanshen.exe"`                   | 原神游戏的进程映像名称。                                 |
| `pre_launch_check.kill_bgi_if_game_absent` | bool   | `true`                             | 游戏未运行而 BetterGI 残留时，是否先 taskkill 掉 BetterGI。 |
| `pre_launch_check.wait_after_kill_seconds` | number | `3`                                | taskkill 之后等待多少秒再启动，确保文件句柄释放。                |
| `monitor.enabled`                          | bool   | `true`                             | 是否启用持续监听。设为 `false` 时启动后立即退出（退化为 v0.1.0 行为）。 |
| `monitor.poll_interval_seconds`            | number | `2`                                | 进程状态检查与日志抓取的轮询间隔（秒）。                         |
| `monitor.startup_timeout_seconds`          | number | `120`                              | 启动后多少秒内仍未检测到 BetterGI 进程则放弃监听。               |
| `monitor.max_duration_hours`               | number | `12`                               | 单次监听的最大时长保护，`0` 表示不限制。                       |
| `monitor.capture_stdout`                   | bool   | `true`                             | 是否采集 BetterGI 子进程的终端输出（**主日志来源**）。           |
| `monitor.follow_log_file`                  | bool   | `false`                            | 是否始终跟随 BetterGI 日志文件（次来源，默认关闭以避免与终端输出重复）。    |
| `monitor.follow_log_file_fallback`         | bool   | `true`                             | 终端迟迟没有输出时，是否自动启用日志文件跟随兜底。                    |
| `monitor.stdout_grace_seconds`             | number | `20`                               | 判定“终端没有输出”的宽限时间（秒）。                          |
| `special_rules.burst_first_day_as_normal`  | bool   | `true`                             | 爆发期第一天是否视为非爆发期。`true` 表示第一天仍用 `dm`。          |
| `special_rules.update_day_kill_after_dm`   | bool   | `true`                             | 版本更新日是否执行终止进程操作。                             |
| `special_rules.kill_delay_seconds`         | number | `60`                               | 启动 `dm` 后等待多少秒再终止进程。                         |
| `special_rules.kill_processes`             | array  | `["Yuanshen.exe", "BetterGI.exe"]` | 需要终止的进程名称列表。                                 |

### 适配其他配置名称

如果你的 BetterGI 一条龙配置名称不是 `wz` 和 `dm`，只需修改 `config_name_mapping`：

```json
"config_name_mapping": {
  "burst": "你的爆发期配置名",
  "normal": "你的常规配置名"
}
```

例如，若配置名为 `爆发` 和 `日常`：

```json
"config_name_mapping": {
  "burst": "爆发",
  "normal": "日常"
}
```

### 关闭更新日终止进程

若你不希望更新日自动终止游戏，设置：

```json
"update_day_kill_after_dm": false
```

### 调整终止延迟

若希望启动后等待 120 秒再终止：

```json
"kill_delay_seconds": 120
```

---

## 启动前进程检查

*（v0.1.1 新增）*

无人值守场景下，某天的 BetterGI 任务可能因异常而未正常收尾，第二天 7:20 再次运行时就会遇到“**游戏没开，但 BetterGI 还挂在那里**”的状态，直接启动新流程往往达不到预期效果。因此启动器在调用 BetterGI **之前**会先检查两个进程：

| 检查结果                                        | 处理动作                                                                               |
| ------------------------------------------- | ---------------------------------------------------------------------------------- |
| `Yuanshen.exe` 未运行，`BetterGI.exe` 未运行       | 无需清理，直接进入启动流程                                                                      |
| `Yuanshen.exe` **正在运行**，`BetterGI.exe` 正在运行 | **保留**现有 BetterGI，不执行 taskkill（避免打断正在进行中的任务）                                       |
| `Yuanshen.exe` 未运行，`BetterGI.exe` **正在运行**  | **先 `taskkill /F /IM BetterGI.exe`**，等待 `wait_after_kill_seconds` 秒确认退出后，再执行原有启动流程 |


检测通过 `tasklist /FI "IMAGENAME eq xxx.exe" /FO CSV /NH` 实现，解析时只认同以引号开头的数据行，因此不受系统语言影响（不会把“信息: 没有运行的任务匹配指定标准”误判为“存在进程”）。

不希望启用时可设置：

```json
"pre_launch_check": { "enabled": false }
```

---

## 运行日志监听与合并

*（v0.1.1 新增）*

启动 BetterGI 之后，启动器**不会立即退出**，而是持续运行：

1. **采集终端输出（主来源）**

   通过命令行 `BetterGI.exe startOneDragon <配置名>` 启动的 BetterGI 会把运行日志直接打印到终端。启动器用管道接管子进程的 `stdout/stderr`，在后台线程中逐行读取，实时写入合并日志文件。
   > 附带修掉了一个隐患：原实现虽然设置了 `stdout=PIPE`，却从未读取，管道缓冲区写满后子进程会被阻塞。现在输出由专门的读取线程持续消费。
2. **跟随日志文件（兜底来源）**

   若某种情况下终端一直没有输出（例如 BetterGI 把任务交接给了已在运行的实例），启动器会在 `stdout_grace_seconds` 秒后自动启用日志文件跟随：

   `BetterGI.exe` 同目录下的 `log/better-genshin-impactYYYYMMDD.log`。

   跟随策略为**增量读取**：启动前先记录该文件的字节基线，只搬运本次启动之后新增的内容，不会把当天早些时候的旧会话日志重复写进来；文件被截断时自动回到开头，跨零点出现新日志文件时自动切换。
3. **结束条件**
   - BetterGI 进程被关闭（正常收尾）；
   - 或更新日特殊规则到期并执行了 taskkill；
   - 或超过 `max_duration_hours` 的保护时长。

结束后启动器会在合并日志中写入收尾标记，并记录子进程退出码，然后自身退出。

> 只想让它“启动完就退出”（即 v0.1.0 行为）时，设置 `"monitor": { "enabled": false }`。

---

## 日期与版本规则

### 版本周期计算

- 原神每个版本持续 **42 天**。
- 基准版本：**7.0**，开始日期 **2026-08-12**。
- 后续版本依次为 7.1（2026-09-23）、7.2（2026-11-04）……
- 版本号递增规则：主版本号不变，次版本号 +1；当次版本号达到 10 时，主版本号 +1，次版本号归零（例如 7.9 → 8.0）。
- 程序通过计算目标日期与基准日期的天数差，除以 42 得到版本偏移量，再取余得到版本内天数（0 表示版本更新当天）。

### 紊乱爆发期判定

- 紊乱爆发期：版本更新后 **第 8 天 10:00** 开始，持续 **10 天**，至 **第 17 天 03:59** 结束。
- 以 7.0 版本为例：
  - 版本开始：2026-08-12
  - 爆发期开始：2026-08-19 10:00（第 8 天）
  - 爆发期结束：2026-08-29 03:59（第 17 天）
- 程序判定逻辑：
  1. 若 `day_in == 0`（版本更新当天），强制视为非爆发期。
  2. 若 `day_in == 7`（爆发期第一天）且 `burst_first_day_as_normal = true`，视为非爆发期。
  3. 若 `day_in` 在 `[7, 16]` 范围内（即第 8 天至第 17 天），且最后一天未超过 03:59，则视为爆发期。
  4. 其他情况均为非爆发期。

> **注意**：程序在每日 7:20 运行，因此爆发期第一天（第 8 天）的 10:00 尚未到达，默认视为非爆发期，符合实际需求。该行为可通过 `burst_first_day_as_normal` 修改。

### 版本更新日特殊处理

- 版本更新当天（`day_in == 0`），游戏停服维护至 **10:00**。
- 程序在更新日启动 `dm` 配置后，等待 `kill_delay_seconds` 秒（默认 60 秒），然后依次终止 `kill_processes` 列表中的进程。
- v0.1.1 起，该延迟在监听循环中到期触发（不再阻塞式 `sleep`），终止后监听会立即检测到 BetterGI 已退出并收尾。
- 该功能由 `update_day_kill_after_dm` 控制，默认开启。若不需要，可设为 `false`。

---

## 命令行与测试模式

程序支持以下命令行参数：

| 参数         | 说明                                           |
| ---------- | -------------------------------------------- |
| （无）        | 正常启动流程，根据日期自动选择配置并启动 BetterGI，随后持续监听日志直至其退出。 |
| `testbgi`  | 测试模式：验证是否能够唤起带有 UAC 权限的 BetterGI。            |
| `testtk`   | 测试模式：验证 taskkill 功能是否正常。                     |
| `testproc` | 测试模式：输出当前进程状态、BetterGI 日志目录、日志基线大小与合并日志目标路径。 |

### 测试 BetterGI 唤起

```bash
BetterGI_Launcher.exe testbgi
```

程序会输出 BetterGI 路径、路径是否存在、当前管理员权限，并尝试执行 `BetterGI.exe --help`。若成功，说明 BetterGI 可正常唤起。

### 测试 taskkill

```bash
BetterGI_Launcher.exe testtk
```

程序会启动一个 `notepad.exe`，等待 2 秒后使用 `taskkill /F /IM notepad.exe` 终止它，并输出结果。若成功，说明 taskkill 功能正常。

### 测试进程检测与日志路径

```bash
BetterGI_Launcher.exe testproc
```

输出示例：

```
[INFO] BetterGI.exe: 未运行
[INFO] Yuanshen.exe: 运行中 PID=12345
[INFO] BetterGI 路径: D:\Tools\Mhy tools\BetterGI\BetterGI.exe
[INFO] 日志目录: D:\Tools\Mhy tools\BetterGI\log（存在: True）
[INFO] 当前日志基线: D:\Tools\Mhy tools\BetterGI\log\better-genshin-impact20261005.log（19354 字节）
```

配置新环境后建议先跑一次 `testproc`，确认进程名与日志目录识别正确。

---

## 日志系统

- 日志根目录：程序所在目录下的 `log` 文件夹，按日期分目录：`log/YYYY-MM-DD/`。
- 每次运行最多生成三个日志文件：

| 文件                            | 内容                           |
| ----------------------------- | ---------------------------- |
| `HH-MM-SS.log`                | 启动器常规日志（DEBUG 及以上）           |
| `error-HH-MM-SS.log`          | 启动器错误日志（仅 ERROR 及以上）         |
| `bettergi-merge-HH-MM-SS.log` | BetterGI 运行日志合并文件（v0.1.1 新增） |

- 合并日志示例（`####` 开头的行为启动器添加的时间戳标记，其余行均为 BetterGI 原始输出，未经改写）：
  ```
  # BetterGI 运行日志合并文件
  # 生成时间: 2026-10-05 22:50:31
  # 启动器版本: v0.1.1
  # BetterGI: D:\Tools\Mhy tools\BetterGI\BetterGI.exe
  # 一条龙配置: wz（紊乱爆发期（第13天），使用爆发期配置）
  # ==========================================================
  #### [2026-10-05 22:50:31] 检测到 BetterGI.exe 进程，开始采集运行日志
  [20:11:40.756] [INF] [...][...] BetterGenshinImpact.ViewModel.Pages.OneDragonFlowViewModel
  启用一条龙配置：wz
  #### [2026-10-05 23:41:07] 监听结束：BetterGI.exe 进程已关闭；合并日志行数 1024
  ```
- 日志格式：`时间 [级别] 消息`。
- 控制台同时输出 INFO 及以上级别的日志，方便调试。
- 所有异常均会记录到错误日志，便于无人值守时事后排查。

---

## 打包指南

### 使用 PyInstaller 打包

1. 安装 PyInstaller：

```bash
pip install pyinstaller
```

1. 使用仓库自带的 spec 文件打包（推荐，图标与参数已固化）：

```bash
pyinstaller BetterGI_Launcher.spec
```

或等价的命令行方式：

```bash
pyinstaller --onefile --windowed --icon="BlackScreen_240x240_32bit.ico" --name "BetterGI_Launcher" BgiLauncher.py
```

1. 打包完成后，可执行文件位于 `dist/BetterGI_Launcher.exe`。

### 参数说明

| 参数           | 说明                                                             |
| ------------ | -------------------------------------------------------------- |
| `--onefile`  | 打包为单个 exe 文件，便于分发。                                             |
| `--windowed` | 不显示控制台窗口（GUI 模式）。v0.1.1 起程序常驻监听，无控制台更适合无人值守；需要观察实时输出时可按源码方式运行。 |
| `--icon`     | 指定图标文件路径，必须为 `.ico` 格式。                                        |
| `--name`     | 指定输出的 exe 名称。                                                  |

### 图标要求

- 仓库内路径：`BlackScreen_240x240_32bit.ico`
- 格式：ICO，尺寸建议包含 256x256、128x128、64x64、48x48、32x32、16x16 等多分辨率。
- 若图标文件不存在，PyInstaller 会报错，请确保路径正确。

### 打包后的目录结构

```
dist/
└── BetterGI_Launcher.exe
```

首次运行时，exe 会在同目录下生成 `config.json` 和 `log` 文件夹。

---

## 常见问题 FAQ

### Q1：程序启动后弹窗提示“权限不足”并退出？

**原因**：未以管理员身份运行。

**解决**：右键 exe → “以管理员身份运行”。若通过任务计划程序，请勾选“使用最高权限运行”。

### Q2：首次运行没有弹出文件选择对话框？

**原因**：可能已存在 `config.json`，或 `tkinter` 不可用。

**解决**：删除 `config.json` 后重新运行；确保 Python 安装包含 `tkinter`。也可手动编辑 `config.json` 填写 `bettergi_path`。

### Q3：BetterGI 启动失败，日志显示“路径无效”？

**原因**：`bettergi_path` 配置错误或文件不存在。

**解决**：检查路径是否正确，注意反斜杠转义（JSON 中需使用 `\\`）。建议使用绝对路径。

### Q4：配置名称 `wz` / `dm` 不存在怎么办？

**原因**：BetterGI 中未创建对应名称的一条龙配置。

**解决**：在 BetterGI 中创建名为 `wz` 和 `dm` 的配置，或修改 `config.json` 中的 `config_name_mapping` 为实际配置名。

### Q5：更新日终止进程没有生效？

**原因**：`update_day_kill_after_dm` 为 `false`，或当天不是版本更新日。

**解决**：检查配置；确认日期计算是否正确（基准日期 2026-08-12，周期 42 天）。

### Q6：日志文件在哪里？

**位置**：程序同目录下的 `log/YYYY-MM-DD/` 文件夹。

**排查**：优先查看 `error-*.log`，其中记录了所有错误信息；BetterGI 自身的运行过程看 `bettergi-merge-*.log`。

### Q7：如何修改爆发期第一天视为非爆发期的行为？

**修改**：将 `config.json` 中 `special_rules.burst_first_day_as_normal` 设为 `false`。

**效果**：爆发期第一天（第 8 天）将直接使用 `wz` 配置。

### Q8：支持其他版本的日期计算吗？

**支持**：基准版本和日期在代码中定义为 `BASE_VERSION = (7, 0)` 和 `BASE_DATE = date(2026, 8, 12)`。若未来版本周期变化，可修改这两个常量。

### Q9：为什么程序启动后一直不退出、任务管理器里一直有它？

**原因**：v0.1.1 起启动器会常驻，持续监听 BetterGI 日志，直到 BetterGI 进程关闭才自行退出，这是刻意设计。

**解决**：若想要“启动完就退出”，设置 `"monitor": { "enabled": false }`。

### Q10：合并日志是空的，或只有启动器标记？

**原因**：BetterGI 的终端输出未被采集到（例如进程被交接给了已运行的实例），且文件兜底尚未触发或未开启。

**解决**：先执行 `BgiLauncher.exe testproc` 确认进程名与日志目录识别正确；必要时把 `monitor.follow_log_file` 设为 `true`（始终跟随日志文件），或调小 `stdout_grace_seconds` 让兜底更快生效。

### Q11：日志里出现了重复的 BetterGI 内容？

**原因**：同时开启了终端输出采集与日志文件跟随（`capture_stdout` 与 `follow_log_file` 均为 `true`）——两者记录的是同一批日志。

**解决**：保持 `follow_log_file = false`（默认），依赖兜底机制即可。

### Q12：想临时禁用启动前的进程清理逻辑？

**设置**：`"pre_launch_check": { "enabled": false }`；或仅关闭清理动作 `"kill_bgi_if_game_absent": false`。

---

## 更新日志

### v0.1.2

- 模型标记：本版本由 **Kimi K3** 编写与维护。
- 说明：功能与 v0.1.1 一致。v0.1.1 期间工作区曾回滚至 v0.1.0 代码，本版本以 v0.1.1 代码为基础重新整理并正式发布。
- 启动 BetterGI 前进程检查：若 `Yuanshen.exe` 未运行而 `BetterGI.exe` 正在运行，先 `taskkill` 掉 BetterGI，再执行原有启动流程。
- 启动后脚本持续运行，监听并合并 BetterGI 日志（终端输出为主、日志文件跟随兜底），直至 BetterGI 进程被关闭。
- 验证：发布前对核心模块（版本计算、爆发期判定、进程检测、输出解码、日志基线解析）完成功能级冒烟测试，全部通过。
- 文档：`readme.md` 更新至 v0.1.2，附录收录本次需求提示词。

### v0.1.1

- 新增：启动 BetterGI 前检查进程状态。若 `Yuanshen.exe` 未运行而 `BetterGI.exe` 正在运行，先 `taskkill` 掉 BetterGI，再执行原有启动流程。
- 新增：启动后持续运行，采集 BetterGI 的终端输出（主）并支持日志文件跟随（兜底），实时合并写入 `bettergi-merge-*.log`，直至 BetterGI 进程关闭才退出。
- 修复：`launch_bettergi()` 原先设置 `stdout=PIPE` 却从不读取，存在管道写满导致子进程阻塞的隐患。
- 修复：`launch_bettergi()` 成功/失败分支返回值格式不一致（`True, proc` 与 `False`）的问题。
- 优化：更新日延迟终止改为在监听循环中到期触发，不再阻塞式 `sleep`。
- 优化：配置加载改为深拷贝默认值，避免共享可变对象；兼容已有 `config.json`（自动补全新增字段）。
- 新增：`testproc` 测试模式。
- 文档：重写 `readme.md`，修正原文档中 Markdown 转义符损坏（`\#`、`\*\*`、`&nbsp;`）的问题，并补充 v0.1.1 新特性说明。

### v0.1.0

- 首个版本：日期驱动的配置自动匹配（`wz` / `dm`）、紊乱爆发期判定、版本更新日延迟终止进程、UAC 权限校验、按日期分目录的日志系统、`testbgi` / `testtk` 测试模式、PyInstaller 单文件打包。

---

## 开发说明

### 代码结构

`BgiLauncher.py` 为单文件程序，主要模块：

- **日志系统**：`setup_logger()` 创建按日期分目录的日志。
- **UAC 检测**：`is_admin()`、`request_admin()`。
- **配置管理**：`load_config()`、`save_config()`、`select_bgi_path_interactive()`。
- **日期计算**：`get_version_info()`、`is_burst_period()`、`is_update_day()`、`is_maintenance_time()`。
- **进程管理**：`get_process_pids()`、`is_process_running()`、`kill_processes()`、`pre_launch_process_check()`。
- **启动**：`launch_bettergi()`。
- **日志采集**：`decode_output()`、`capture_bgi_log_baseline()`、`MergedLogWriter`、`BgiStdoutReader`、`BgiLogFollower`、`monitor_bettergi()`。
- **测试模式**：`test_bgi()`、`test_taskkill()`、`test_process()`。
- **主流程**：`main()`。

### 扩展建议

- 若需支持更多特殊日期规则，可在 `special_rules` 中增加字段，并在 `main()` 中读取。
- 若需发送通知（如邮件、钉钉、微信），可在 `monitor_bettergi()` 的收尾处或 `MergedLogWriter.write()` 中加钩子（例如匹配到“任务完成”关键字时推送）。
- 若需多语言，可将日志和提示文本提取为常量。

### 贡献

欢迎提交 Issue 和 Pull Request。请确保代码风格一致，并附上测试日志。

---

## 附录：最初提示词

以下为用户最初给出的完整需求提示词，v0.1.0 即根据此需求编写。

```text
写一个python，用于在不同的日期，匹配不同的启动参数，启动我的Bettergi

配置文件包括四项，在首次启动时 自动创建 bgi路径允许弹出一个文件资源管理器，然后用户自行选择

1、better文件路径 参考“D:\Tools\Mhy tools\BetterGI\BetterGI.exe"

2、bgi启动参数的的匹配规则——以兼容其他配置名称或日期要求

3、后面提到的紊乱爆发期与版本更新特殊优化的开启状态

bettergi文档：

# 执行 BetterGI 一条龙页面上选定的配置
BetterGI.exe startOneDragon
BetterGI.exe --startOneDragon
start bettergi://startOneDragon

# 执行给定的一条龙配置（如果找不到就用页面上选定的）（需要 0.45.3 及以上版本）
BetterGI.exe startOneDragon <配置名称>
BetterGI.exe --startOneDragon <配置名称>

原神的每个版本持续42天，如7.0版本 开始自2026/08/12 结束自2026/09/23
7.1版本 开始自2026/09/23 结束自2026/11/4

每个版本更新的第八天 开启为期十天的紊乱爆发期 如7.0版本的紊乱爆发期自 2026/08/19 10:00 至 2026/08/29 03:59

在版本的紊乱爆发期，你需要启动的配置名称为 wz
在非紊乱爆发期 你要启动的配置名称是 dm

但由于脚本的自动运行时间是每日7:20 这意味着 在每个的紊乱爆发期开启的第一天，视为非紊乱爆发期 该项可在配置文件中修改

此外 每个版本更新当天，会有持续至10:00的停服维护 因此，在版本更新当天，执行附带启动参数dm 一分钟之后 执行taskkill Yuanshen.exe 与 BetterGi.exe 该项亦可在配置文件中设置

最终输出应该是一个python程序与一个配置文件，一份readme.md
然后使用 D:\asus\Documents\mic\BlackScreen_240x240_32bit.ico 作为图标打包该程序
并允许附带启动参数 testbgi 来测试是否能唤起带有uac权限的bgi testtk 来测试是否能够正常执行taskkill
启动时若不带uac 则直接弹窗，并报错退出
由于无人值守，日志文件报错至同目录下log文件夹，参考：
└─log
   └─2026-10-05
           19-40-00.log
           error-19-40-00.log
```

### v0.1.2 追加需求

```text
做这几件事，对该项目进行修改：
1、启动bettergi前先检查bettergi.exe 的运行状态 若yuanshen.exe不在运行 bettergi.exe在运行 就先taskkill掉bettergi 然后再执行之前的启动流程
2、脚本持续运行，监听并记录bettergi日志，直至bettergi进程被关闭
3、修改readme.md 然后提交到git 版本号0.1.2
4、打包程序为exe
补充信息：由终端附带启动参数拉起的bettergi 会输出日志至控制台
```

## 免责声明

1. 本工具仅用于辅助启动 BetterGI，不修改游戏文件，不提供任何游戏内作弊功能。
2. 使用本工具产生的一切后果由使用者自行承担。
3. 请遵守 BetterGI 的许可协议以及原神官方的用户协议。
4. 本项目由 Kimi K3 生成，作者不对其稳定性、安全性作任何明示或暗示的担保。

---

**Enjoy your automated journey with BetterGI!** 🎮✨
