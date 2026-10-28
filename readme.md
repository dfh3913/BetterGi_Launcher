# BetterGI 智能启动器

> **本项目是由 DeepSeek v4.1f 编写的 Vibe 项目**
>
> 一个按“实际启动游戏的时间”自动匹配启动参数、智能切换 BetterGI 一条龙配置、并在原神失焦时自动把它拉回前台的 Windows 自动化工具。

- 当前版本：**v0.1.3**
- 适用场景：原神 7.x 版本的紊乱爆发期 / 常规期配置自动切换

---

## 📖 目录

- [项目简介](#项目简介)
- [功能特性](#功能特性)
- [系统要求](#系统要求)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [配置文件详解](#配置文件详解)
- [终端日志回显](#终端日志回显)
- [焦点守护：原神失焦自动切前台](#焦点守护原神失焦自动切前台)
- [启动前进程检查](#启动前进程检查)
- [运行日志监听与合并](#运行日志监听与合并)
- [日期与版本规则](#日期与版本规则)
- [命令行与测试模式](#命令行与测试模式)
- [日志系统](#日志系统)
- [打包指南](#打包指南)
- [常见问题 FAQ](#常见问题-faq)
- [更新日志](#更新日志)
- [开发说明](#开发说明)
- [附录：需求提示词](#附录需求提示词)
- [免责声明](#免责声明)

---

## 项目简介

**BetterGI 智能启动器** 是一个专为 [BetterGI](https://bettergi.com/)（一款原神自动化工具）设计的辅助启动程序。

原神每个版本持续 42 天。版本更新后的第 8 天 10:00 起，「幽境危战」的**紊乱爆发期**开启，持续约 10 天（至第 18 天 03:59）。爆发期与非爆发期，玩家通常需要使用不同的 BetterGI 一条龙配置（默认 `wz` / `dm`）。此外，版本更新当天 06:00 起停服维护，约 11:00 开服。

手动切换配置既繁琐又容易遗忘。本项目会读取**系统时间**，按真实的时间窗口判断是否处于紊乱爆发期，据此选择配置名称启动 BetterGI，并在运行期间持续接管日志、处理原神失焦。

程序执行流程：

```
管理员权限校验
   └─ 加载 config.json
        └─ 读取系统时间 → 精确判定版本 / 紊乱爆发期（10:00 边界）→ 决定配置名 wz / dm
             └─ 启动前进程检查：游戏未运行但 BetterGI 残留 → 先 taskkill
                  └─ 记录 BetterGI 日志文件基线
                       └─ 启动 BetterGI.exe startOneDragon <配置名>
                            └─ 持续监听：终端输出（主）+ 日志文件（兜底）
                                 ├─ v0.1.3 回显到当前终端
                                 ├─ v0.1.3 命中“不是原神…暂停”→ 把原神切到前台（F12 取消）
                                 └─ 直至 BetterGI 进程关闭 / 更新日延迟终止到期 → 收尾退出
```

---

## 功能特性

- ✅ **按启动时刻精确判定**（v0.1.3）：读取系统时间（精确到分钟），按官方真实窗口判断爆发期，10:00 前后自动区分，不再依赖“脚本固定 7:20 运行”的假设。
- ✅ **紊乱爆发期识别**：自动切换 `wz` / `dm` 配置，并修正旧版把爆发期结束日提前一天的问题。
- ✅ **终端日志回显**（v0.1.3）：从命令行启动本程序时，BetterGI 的运行日志同步打印到当前终端；打包为窗口程序时通过 `AttachConsole` 附着父控制台。
- ✅ **焦点守护**（v0.1.3）：BetterGI 日志出现“不是原神 …… 暂停”时，自动找到原神窗口并切到前台；运行期按 **F12** 可取消 / 恢复（不写入配置文件）。
- ✅ **启动前进程检查**（v0.1.1）：游戏未运行而 BetterGI 残留时先 `taskkill` 清理再启动，避免新一轮任务被前一天的残留进程卡住。
- ✅ **持续日志监听与合并**（v0.1.1）：实时读取 BetterGI 终端输出（日志文件跟随兜底），合并写入 `bettergi-merge-*.log`，直至 BetterGI 进程关闭才退出。
- ✅ **版本更新日特殊处理**：更新当天启动 `dm` 后，延迟指定秒数终止游戏与 BetterGI 进程。
- ✅ **UAC 权限保护**：无管理员权限时弹窗提示并退出，确保任务计划以最高权限运行。
- ✅ **首次运行引导**：自动创建配置文件，并弹出文件选择对话框选择 `BetterGI.exe`。
- ✅ **完整日志系统**：按日期分目录，常规日志、错误日志、BetterGI 合并日志分离。
- ✅ **测试模式**：`testbgi` / `testtk` / `testproc` / `testtime`，可快速验证唤起、taskkill、进程检测与时间判定。
- ✅ **高度可配置**：配置名称、进程检查、监听策略、焦点守护、终止进程列表等均可通过 `config.json` 调整。
- ✅ **单文件打包**：支持 PyInstaller 打包为独立 exe，附带自定义图标。

---

## 系统要求

| 项目            | 要求                                                                                                                              |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| 操作系统          | Windows 10 / Windows 11                                                                                                         |
| 运行权限          | **管理员权限**（必需，用于 taskkill、切换原神窗口到前台）                                                                                         |
| Python 版本（开发） | Python 3.8 或更高                                                                                                                  |
| BetterGI 版本   | 0.45.3 及以上（支持 `startOneDragon <配置名称>`）                                                                                          |
| 依赖库           | 仅标准库（`csv`, `ctypes`, `io`, `json`, `logging`, `os`, `re`, `subprocess`, `sys`, `threading`, `time`, `datetime`, `pathlib`, `tkinter`） |

> **注意**：`tkinter` 仅用于首次运行时的文件选择对话框，Windows 官方 Python 安装包默认包含。

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
│   └── 2026-10-28/
│       ├── 21-39-51.log                 # 启动器常规日志
│       ├── error-21-39-51.log           # 启动器错误日志
│       └── bettergi-merge-21-39-51.log  # BetterGI 运行日志合并文件
└── dist/
    └── BetterGI_Launcher.exe      # 打包后的可执行文件
```

---

## 快速开始

### 1. 获取程序

**方式一：直接使用打包好的 exe**

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
2. 若未找到 `config.json`，程序会自动创建默认配置，并弹出文件选择对话框。
3. 在对话框中定位到你的 `BetterGI.exe`，例如：
   ```
   D:\Tools\Mhy tools\BetterGI\BetterGI.exe
   ```
4. 选择完成后，程序保存配置并立即执行一次启动流程。
5. 程序会在同目录下创建 `log` 文件夹，写入本次运行日志与 BetterGI 合并日志。

> **提示**：如果未选择文件或路径无效，程序会记录错误日志并退出。可手动编辑 `config.json` 修正路径。

### 3. 配置任务计划

为了实现每日 7:20 自动运行：

1. 打开 **任务计划程序**（Task Scheduler）。
2. 点击 **“创建任务”**（不是“创建基本任务”）。
3. **常规**选项卡：
   - 名称：`BetterGI 智能启动器`
   - 勾选 **“使用最高权限运行”**（至关重要，否则会因缺少 UAC 权限而弹窗退出）。
   - 配置：选择你的 Windows 版本。
4. **触发器**选项卡：
   - 新建触发器 → 每天 → 开始时间设置为 `07:20:00` → 勾选“启用”。
5. **操作**选项卡：
   - 新建操作 → 启动程序 → 程序或脚本：选择 `BetterGI_Launcher.exe` 的完整路径。
   - 起始于（可选）：填写 exe 所在目录，例如 `D:\Tools\BetterGI_Launcher\`。
6. **条件**选项卡：
   - 取消勾选 **“只有在计算机使用交流电源时才启动此任务”**（笔记本）。
7. **设置**选项卡：
   - 勾选 **“如果任务失败，按以下频率重新启动”**，可设置 1 分钟、3 次。
   - **务必取消勾选 “如果任务运行时间超过以下时间，停止任务”**。启动器会常驻运行直至 BetterGI 关闭（可能长达数小时），保留该限制会掐断监听。
8. 保存任务，可右键手动运行一次测试。

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
  "focus_game": {
    "enabled": true,
    "trigger_keywords": ["不是原神", "暂停"],
    "delay_seconds": 3,
    "cooldown_seconds": 30,
    "retry_times": 6,
    "retry_interval_seconds": 5,
    "cancel_key": "F12"
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

| 字段路径                                       | 类型     | 默认值                                | 说明                                                        |
| ------------------------------------------ | ------ | ---------------------------------- | --------------------------------------------------------- |
| `bettergi_path`                            | string | `""`                               | `BetterGI.exe` 的完整路径。首次运行会弹出文件选择对话框，也可手动编辑。                 |
| `config_name_mapping.burst`                | string | `"wz"`                             | 紊乱爆发期使用的 BetterGI 一条龙配置名称。                                 |
| `config_name_mapping.normal`               | string | `"dm"`                             | 非爆发期使用的配置名称。                                              |
| `pre_launch_check.enabled`                 | bool   | `true`                             | 是否启用启动前进程检查。                                              |
| `pre_launch_check.bgi_process`             | string | `"BetterGI.exe"`                   | BetterGI 的进程映像名称。                                         |
| `pre_launch_check.game_process`            | string | `"Yuanshen.exe"`                   | 原神游戏的进程映像名称（国际服为 `GenshinImpact.exe`，程序会自动兼容）。            |
| `pre_launch_check.kill_bgi_if_game_absent` | bool   | `true`                             | 游戏未运行而 BetterGI 残留时，是否先 taskkill 掉 BetterGI。              |
| `pre_launch_check.wait_after_kill_seconds` | number | `3`                                | taskkill 之后等待多少秒再启动。                                      |
| `monitor.enabled`                          | bool   | `true`                             | 是否启用持续监听。设为 `false` 时启动后立即退出。                             |
| `monitor.poll_interval_seconds`            | number | `2`                                | 进程状态检查与日志抓取的轮询间隔（秒）。                                      |
| `monitor.startup_timeout_seconds`          | number | `120`                              | 启动后多少秒内仍未检测到 BetterGI 进程则放弃监听。                             |
| `monitor.max_duration_hours`               | number | `12`                               | 单次监听最大时长保护，`0` 表示不限制。                                     |
| `monitor.capture_stdout`                   | bool   | `true`                             | 是否采集 BetterGI 子进程的终端输出（**主日志来源**）。                        |
| `monitor.follow_log_file`                  | bool   | `false`                            | 是否始终跟随 BetterGI 日志文件（次来源，默认关闭以避免重复）。                       |
| `monitor.follow_log_file_fallback`         | bool   | `true`                             | 终端迟迟没有输出时，是否自动启用日志文件跟随兜底。                                 |
| `monitor.stdout_grace_seconds`             | number | `20`                               | 判定“终端没有输出”的宽限时间（秒）。                                       |
| `focus_game.enabled`                       | bool   | `true`                             | 是否启用“原神失焦自动切前台”。**默认开启**；运行期按 F12 可临时取消（不写回配置）。             |
| `focus_game.trigger_keywords`              | array  | `["不是原神", "暂停"]`                   | 触发关键词。日志行需**同时**包含全部关键词（忽略空格与标点）才触发。                       |
| `focus_game.delay_seconds`                 | number | `3`                                | 命中后延迟多少秒再切换，留出按 F12 取消的时间。                                |
| `focus_game.cooldown_seconds`              | number | `30`                               | 两次自动切换之间的最小间隔（秒），避免日志刷屏导致反复抢焦点。                           |
| `focus_game.retry_times`                   | number | `6`                                | 找不到原神窗口时的重试次数（游戏可能还没启动完）。                                 |
| `focus_game.retry_interval_seconds`        | number | `5`                                | 每次重试的间隔（秒）。                                               |
| `focus_game.cancel_key`                    | string | `"F12"`                            | 取消 / 恢复快捷键，支持 `F1` ~ `F12`。                                |
| `special_rules.burst_first_day_as_normal`  | bool   | `true`                             | **已由精确时间判定取代**（10:00 前必然走常规配置），保留仅为向后兼容；设为 `false` 会在日志中提示该项失效。 |
| `special_rules.update_day_kill_after_dm`   | bool   | `true`                             | 版本更新日是否执行终止进程操作。                                          |
| `special_rules.kill_delay_seconds`         | number | `60`                               | 启动 `dm` 后等待多少秒再终止进程。                                      |
| `special_rules.kill_processes`             | array  | `["Yuanshen.exe", "BetterGI.exe"]` | 需要终止的进程名称列表。                                              |

### 适配其他配置名称

若你的一条龙配置名不是 `wz` / `dm`，只改 `config_name_mapping` 即可：

```json
"config_name_mapping": {
  "burst": "爆发",
  "normal": "日常"
}
```

### 关闭自动切前台

```json
"focus_game": { "enabled": false }
```

运行期也可以直接按 **F12** 临时取消，无需修改配置文件。

---

## 终端日志回显

*（v0.1.3 新增）*

BetterGI 由命令行启动时会把运行日志打印到终端。启动器接管了这份输出（`stdout/stderr` 管道），因此默认情况下这些日志只会进入合并日志文件，看不到实时进度。v0.1.3 起：

- **以 `python BgiLauncher.py` 或控制台程序方式运行时**，BetterGI 的每一行日志都会原样打印到当前终端；
- **打包为窗口程序（`console=False`）时**，程序启动会调用 `AttachConsole(ATTACH_PARENT_PROCESS)` 附着到启动它的那个控制台，再通过 `WriteConsoleW` 输出。也就是说，在 cmd / PowerShell / Windows Terminal 里运行 exe 同样能看到 BetterGI 日志；双击启动（没有父控制台）则只写日志文件，不会报错。

> 输出编码做了区分处理：控制台直连走 `WriteConsoleW`（Unicode，不受 `chcp` 代码页影响）；stdout 被重定向到管道 / 文件时统一按 UTF-8 写出，避免中文乱码。

回显内容为 BetterGI 的原始行，不加前缀，便于直接阅读；启动器自身的提示仍带 `[INFO]` / `[WARNING]` 前缀，两者可以区分。

> 从日志文件兜底采集到的内容，只有在“终端确实没有输出、走了兜底”时才会一并回显，避免同一行打印两次。

---

## 焦点守护：原神失焦自动切前台

*（v0.1.3 新增）*

无人值守时，如果中途有别的窗口抢走焦点，BetterGI 会打印类似日志并暂停：

```
[20:53:58.344] [WRN] [Primary:S2:P22860:T1791463519647] BetterGenshinImpact.GameTask.Common.TaskControl
当前获取焦点的窗口为: Idle，不是原神，暂停
```

启动器会实时匹配这行日志（检测“**不是原神**”与“**暂停**”两个关键词，忽略空格与标点，即需求中的六个字“不是原神暂停”），并在 `delay_seconds` 秒后：

1. 通过 `tasklist` 找到 `YuanShen.exe` / `GenshinImpact.exe` 的进程；
2. 枚举其顶层可见窗口，取面积最大的那个作为游戏主窗口；
3. 依次尝试 `ShowWindow` + `AttachThreadInput` + `SetForegroundWindow` + `SwitchToThisWindow`，绕过 Windows 的前台锁定，把原神切到前台；
4. 校验 `GetForegroundWindow()` 是否等于目标窗口，失败会重试。

### 按 F12 取消

运行期间按下 **F12** 即可取消自动切前台：

- 若正处于延迟倒计时中，本次切换立即作废；
- 本次运行内不再自动切换（再按一次 F12 恢复）；
- 状态只保存在内存里，**不会写入 `config.json`**，下次启动仍按配置文件的 `focus_game.enabled` 执行。

按键通过 `GetAsyncKeyState` 轮询（50 ms），不依赖窗口焦点，游戏全屏时同样有效。

### 相关日志

```
[WARNING] BetterGI 报告当前焦点窗口不是原神（日志命中“不是原神 … 暂停”），准备把原神切到前台
[INFO] 3 秒后把原神切到前台，按 F12 可取消
[INFO] 已把原神窗口切到前台（HWND=0x1A2B3C）
```

若游戏尚未启动完，会按 `retry_interval_seconds` 重试 `retry_times` 次；仍找不到则放弃本次切换并记录警告。

---

## 启动前进程检查

*（v0.1.1 新增）*

无人值守场景下，某天的 BetterGI 任务可能因异常而未正常收尾，第二天再次运行时就会遇到“**游戏没开，但 BetterGI 还挂在那里**”的状态。因此启动器在调用 BetterGI **之前**会先检查两个进程：

| 检查结果                                        | 处理动作                                                                               |
| ------------------------------------------- | ---------------------------------------------------------------------------------- |
| `Yuanshen.exe` 未运行，`BetterGI.exe` 未运行       | 无需清理，直接进入启动流程                                                                      |
| `Yuanshen.exe` **正在运行**，`BetterGI.exe` 正在运行 | **保留**现有 BetterGI，不执行 taskkill（避免打断进行中的任务）                                          |
| `Yuanshen.exe` 未运行，`BetterGI.exe` **正在运行**  | **先 `taskkill /F /IM BetterGI.exe`**，等待 `wait_after_kill_seconds` 秒确认退出后，再执行原有启动流程 |

检测通过 `tasklist /FI "IMAGENAME eq xxx.exe" /FO CSV /NH` 实现，只解析以引号开头的数据行，因此不受系统语言影响（不会把“信息: 没有运行的任务匹配指定标准”误判为存在进程）。

不需要时设置：

```json
"pre_launch_check": { "enabled": false }
```

---

## 运行日志监听与合并

*（v0.1.1 新增）*

启动 BetterGI 之后，启动器**不会立即退出**，而是持续运行：

1. **采集终端输出（主来源）**

   通过 `BetterGI.exe startOneDragon <配置名>` 启动的 BetterGI 会把运行日志直接打印到终端。启动器用管道接管子进程的 `stdout/stderr`，后台线程逐行读取，写入合并日志并回显终端。
   > 同时修掉了一个隐患：原实现设置了 `stdout=PIPE` 却从不读取，管道缓冲区写满后子进程会被阻塞。

2. **跟随日志文件（兜底来源）**

   若终端一直没有输出（例如 BetterGI 把任务交接给了已运行的实例），启动器会在 `stdout_grace_seconds` 秒后自动启用日志文件跟随：

   `BetterGI.exe` 同目录下的 `log/better-genshin-impactYYYYMMDD.log`。

   跟随策略为**增量读取**：启动前记录该文件的字节基线，只搬运本次启动之后新增的内容；文件被截断时自动回到开头，跨零点出现新日志文件时自动切换。

3. **结束条件**
   - BetterGI 进程被关闭（正常收尾）；
   - 或更新日特殊规则到期并执行了 taskkill；
   - 或超过 `max_duration_hours` 的保护时长。

结束后会在合并日志写入收尾标记与子进程退出码，然后自身退出。

> 只想“启动完就退出”，设置 `"monitor": { "enabled": false }`。

---

## 日期与版本规则

### 版本周期计算

- 原神每个版本持续 **42 天**，版本更新固定在周三 **06:00** 开始停服维护，官方公告预计 5 小时，**约 11:00 开服**。
- 基准版本：**7.0**，开始日期 **2026-08-12**。
- 版本号递增：次版本号 +1；达到 10 时主版本号 +1、次版本号归零（如 7.9 → 8.0）。
- 程序以日期差除以 42 得到版本偏移，取余得到版本内天数（0 表示版本更新当天）。

### 紊乱爆发期判定（v0.1.3 起按实际启动时刻）

「幽境危战」是常驻战斗活动，**挑战开启后 10 天内**为紊乱爆发期（地脉紊乱点处于爆发状态，可消耗树脂换取自选祝圣秘境奖励）。挑战开启时间固定在版本更新后第 8 天 **10:00**。

因此程序使用的时间窗口是：

- **开始**：版本更新日 + 7 天，**10:00**
- **结束**：版本更新日 + 17 天 **03:59**（每日 04:00 重置，即 +18 天 04:00 之前）
- 覆盖 10 次 04:00 每日重置，与官方“持续 10 天”一致

对照官方公告数据：

| 版本    | 版本更新                | 预计开服    | 紊乱爆发期                             |
| ----- | ------------------- | ------- | --------------------------------- |
| 6.7   | 2026-07-01          | 约 11:00 | 07-08 10:00 ~ 07-18 03:59         |
| 7.0   | 2026-08-12          | 约 11:00 | 08-19 10:00 ~ 08-29 03:59         |
| 7.1   | 2026-09-23          | 约 11:00 | 09-30 10:00 ~ 10-10 03:59         |
| 7.2   | 2026-11-04          | 约 11:00 | 11-11 10:00 ~ 11-21 03:59         |
| 7.3   | 2026-12-16          | 约 11:00 | 12-23 10:00 ~ 2027-01-02 03:59    |

判定逻辑（全部基于 `datetime.now()`，精确到分钟）：

1. `now < 爆发期开始` → 常规配置 `dm`。所以爆发期首日 **10:00 之前**（包括每天 7:20 的定时运行）天然走 `dm`，无需再靠“首日视为非爆发期”的经验规则。
2. `爆发期开始 ≤ now < 爆发期结束` → 爆发期配置 `wz`。
3. `now ≥ 爆发期结束` → 常规配置 `dm`。

> **修复说明**：v0.1.2 及更早版本把结束日算成了“第 8 天 + 9 天”，导致爆发期最后一天（例如 7.0 的 08-29 00:00 ~ 03:59）被误判为常规期。v0.1.3 已按官方口径修正为第 18 天 03:59 结束。
>
> 另外，旧版固定“第 8 天全天视为非爆发期”，若当天 10:00 之后才启动，就会错误地使用 `dm`；现在改为按实际时刻判断，10:00 之后启动会正确使用 `wz`。

### 版本更新日特殊处理

- 版本更新当天（版本内第 1 天），游戏停服维护至约 **11:00**。
- 程序在更新日启动 `dm` 配置后，等待 `kill_delay_seconds` 秒（默认 60 秒），然后依次终止 `kill_processes` 列表中的进程。
- 该延迟在监听循环中到期触发（非阻塞 `sleep`），终止后监听会检测到 BetterGI 已退出并收尾。
- 由 `update_day_kill_after_dm` 控制，默认开启。

---

## 命令行与测试模式

| 参数         | 说明                                           |
| ---------- | -------------------------------------------- |
| （无）        | 正常启动流程：按当前时间选择配置并启动 BetterGI，随后持续监听直至其退出。    |
| `testbgi`  | 验证是否能够唤起带有 UAC 权限的 BetterGI。                  |
| `testtk`   | 验证 taskkill 功能是否正常。                          |
| `testproc` | 输出进程状态、原神主窗口句柄、BetterGI 日志目录、日志基线、终端回显状态。    |
| `testtime` | **（v0.1.3）** 输出当前版本、爆发期窗口、判定结果，以及后续 4 个版本的时间表。 |

### 测试时间判定（推荐先跑）

```bash
BetterGI_Launcher.exe testtime
```

输出示例：

```
[INFO] 当前系统时间: 2026-10-28 21:39:51
[INFO] 当前版本: 7.1（版本内第 36 天 / 共 42 天）
[INFO] 版本更新: 2026-09-23 06:00 停服维护，预计 11:00 开服
[INFO] 紊乱爆发期: 2026-09-30 10:00 ~ 2026-10-10 03:59
[INFO] 判定结果: 非爆发期（版本内第 36 天），紊乱爆发期已于 10-10 03:59 结束，使用常规配置 -> 一条龙配置 dm
[INFO] 后续版本时间表（供核对）:
[INFO]   7.1: 更新 2026-09-23 06:00 / 开服约 11:00，爆发期 09-30 10:00 ~ 10-10 03:59
[INFO]   7.2: 更新 2026-11-04 06:00 / 开服约 11:00，爆发期 11-11 10:00 ~ 11-21 03:59
[INFO]   7.3: 更新 2026-12-16 06:00 / 开服约 11:00，爆发期 12-23 10:00 ~ 01-02 03:59
[INFO]   7.4: 更新 2027-01-27 06:00 / 开服约 11:00，爆发期 02-03 10:00 ~ 02-13 03:59
```

### 其他测试

```bash
BetterGI_Launcher.exe testbgi     # BetterGI 唤起
BetterGI_Launcher.exe testtk      # taskkill（会临时启动 notepad.exe）
BetterGI_Launcher.exe testproc    # 进程 / 窗口 / 日志路径
```

`testproc` 输出示例：

```
[INFO] BetterGI.exe: 未运行
[INFO] Yuanshen.exe: 运行中 PID=12345
[INFO] 原神主窗口: HWND=0x1A2B3C
[INFO] BetterGI 路径: D:\Tools\Mhy tools\BetterGI\BetterGI.exe
[INFO] 日志目录: D:\Tools\Mhy tools\BetterGI\log（存在: True）
[INFO] 当前日志基线: ...\better-genshin-impact20261028.log（19354 字节）
[INFO] 终端回显: 已启用
```

---

## 日志系统

- 日志根目录：程序所在目录下的 `log`，按日期分目录：`log/YYYY-MM-DD/`。
- 每次运行最多生成三个日志文件：

| 文件                            | 内容                       |
| ----------------------------- | ------------------------ |
| `HH-MM-SS.log`                | 启动器常规日志（DEBUG 及以上）      |
| `error-HH-MM-SS.log`          | 启动器错误日志（仅 ERROR 及以上）    |
| `bettergi-merge-HH-MM-SS.log` | BetterGI 运行日志合并文件        |

- 合并日志示例（`####` 开头为启动器添加的标记，其余为 BetterGI 原始输出）：

  ```
  # BetterGI 运行日志合并文件
  # 生成时间: 2026-11-11 07:20:00
  # 启动器版本: v0.1.3
  # BetterGI: D:\Tools\Mhy tools\BetterGI\BetterGI.exe
  # 一条龙配置: wz（紊乱爆发期（版本内第 8 天，至 11-21 03:59 结束），使用爆发期配置）
  # 判定时刻: 2026-11-11 07:20:00（版本 7.2）
  # ==========================================================
  #### [2026-11-11 07:20:03] 检测到 BetterGI.exe 进程，开始采集运行日志
  [20:11:40.756] [INF] [...][...] BetterGenshinImpact.ViewModel.Pages.OneDragonFlowViewModel
  启用一条龙配置：wz
  #### [2026-11-11 07:31:12] BetterGI 报告当前焦点窗口不是原神（日志命中“不是原神 … 暂停”），准备把原神切到前台
  #### [2026-11-11 07:31:15] 已把原神窗口切到前台（HWND=0x1A2B3C）
  #### [2026-11-11 09:41:07] 监听结束：BetterGI.exe 进程已关闭；合并日志行数 1024
  ```

- 日志格式：`时间 [级别] 消息`；控制台同时输出 INFO 及以上级别。

---

## 打包指南

```bash
pip install pyinstaller
pyinstaller BetterGI_Launcher.spec
```

或等价的命令行方式：

```bash
pyinstaller --onefile --windowed --icon="BlackScreen_240x240_32bit.ico" --name "BetterGI_Launcher" BgiLauncher.py
```

| 参数           | 说明                                                          |
| ------------ | ----------------------------------------------------------- |
| `--onefile`  | 打包为单个 exe。                                                  |
| `--windowed` | 不显示控制台窗口（GUI 模式）。v0.1.3 起窗口模式也能通过 `AttachConsole` 把日志回显到启动它的终端。 |
| `--icon`     | 指定 `.ico` 图标。                                               |
| `--name`     | 输出 exe 名称。                                                  |

打包产物位于 `dist/BetterGI_Launcher.exe`。首次运行时会在同目录生成 `config.json` 与 `log/`。

---

## 常见问题 FAQ

### Q1：程序启动后弹窗提示“权限不足”并退出？

未以管理员身份运行。请右键 exe →“以管理员身份运行”；若通过任务计划程序，请勾选“使用最高权限运行”。切换原神窗口到前台同样依赖管理员权限。

### Q2：首次运行没有弹出文件选择对话框？

可能已存在 `config.json`，或 `tkinter` 不可用。删除 `config.json` 后重试，或手动填写 `bettergi_path`。

### Q3：BetterGI 启动失败，日志显示“路径无效”？

`bettergi_path` 配置错误或文件不存在。JSON 中反斜杠需写成 `\\`，建议使用绝对路径。

### Q4：配置名称 `wz` / `dm` 不存在怎么办？

在 BetterGI 中创建同名一条龙配置，或修改 `config_name_mapping` 为实际配置名。

### Q5：终端里看不到 BetterGI 的日志？

- 确认是从命令行（cmd / PowerShell / Windows Terminal）启动的程序，而不是双击；
- 确认 `monitor.capture_stdout = true`；
- 若 BetterGI 把任务交接给了已运行实例，它可能本身不往终端输出，此时由日志文件兜底采集（默认 20 秒后启用），但兜底内容只在终端确实为空时才回显；
- 打包时若使用了 `--noconsole`，程序仍会尝试附着父控制台；某些第三方终端（如部分 IDE 内置终端）不支持 `AttachConsole`，改用系统终端即可。

### Q6：按 F12 没有反应？

- 确认 `focus_game.enabled = true`；
- F12 是全局轮询的，不要求窗口焦点，但若被其他软件（Steam / GeForce Experience 截图）占用，请把 `focus_game.cancel_key` 改成 `F11` 等其他键；
- 取消后日志会打印“已取消自动切前台”，再按一次恢复。

### Q7：日志提示“未找到原神窗口”？

游戏还没启动完，或进程名不是 `Yuanshen.exe`。程序已同时尝试 `YuanShen.exe` 与 `GenshinImpact.exe`；若仍失败，用 `testproc` 确认游戏进程与窗口是否正常。可适当增大 `focus_game.retry_times`。

### Q8：合并日志是空的，或只有启动器标记？

BetterGI 的终端输出未被采集到，且文件兜底尚未触发。先跑 `testproc` 确认进程名与日志目录；必要时把 `monitor.follow_log_file` 设为 `true`，或调小 `stdout_grace_seconds`。

### Q9：日志里出现重复的 BetterGI 内容？

同时开启了终端输出采集与日志文件跟随（`capture_stdout` 与 `follow_log_file` 均为 `true`）。保持 `follow_log_file = false` 即可。

### Q10：为什么程序启动后一直不退出？

启动器会常驻，持续监听 BetterGI 日志并处理失焦，直到 BetterGI 进程关闭才退出，这是刻意设计。想要“启动完就退出”，设置 `"monitor": { "enabled": false }`。

### Q11：爆发期判断和我记的不一样？

以官方公告为准：爆发期 = 版本更新后第 8 天 10:00 起、持续 10 天，至第 18 天 03:59。可运行 `testtime` 查看当前窗口与后续版本时间表。若某天官方调整了活动开启时间，修改代码顶部的 `BURST_START_DAY` / `BURST_START_HOUR` / `BURST_DURATION_DAYS` / `BURST_END_HOUR` 即可。

### Q12：`burst_first_day_as_normal` 还要设置吗？

不需要。v0.1.3 起按真实时间判断，爆发期首日 10:00 之前一定使用 `dm`，10:00 之后一定使用 `wz`，该配置项已失去作用，仅为兼容旧配置保留。

### Q13：更新日终止进程没有生效？

检查 `update_day_kill_after_dm` 是否为 `true`，以及当天是否为版本更新日（基准 2026-08-12，周期 42 天）。

---

## 更新日志

### v0.1.3

- **新增：终端日志回显**。命令行启动本程序时，BetterGI 的运行日志同步输出到当前终端；窗口模式通过 `AttachConsole` 附着父控制台，无控制台时静默跳过。
  - 输出走 `WriteConsoleW`（Unicode），不受控制台代码页影响；stdout 为管道 / 重定向时统一按 UTF-8 写出，避免中文乱码。
- **新增：焦点守护**。BetterGI 日志出现“不是原神 …… 暂停”时，自动枚举原神窗口并切到前台（多重重试 + 前台锁绕过）；运行期按 **F12** 可取消 / 恢复，状态不写入配置文件。
- **改造：爆发期按实际启动时刻判定**。改为读取系统时间、精确到分钟，按官方窗口（第 8 天 10:00 ~ 第 18 天 03:59）判断 `wz` / `dm`。
  - 修复：旧版爆发期结束日提前一天（如 7.0 的 08-29 00:00 ~ 03:59 被误判为常规期）。
  - 修复：旧版“首日全天非爆发期”会把当天 10:00 之后的启动误判为 `dm`。
- **调整**：版本更新日按官方口径提示维护窗口（06:00 停服、约 11:00 开服）。
- **新增**：`testtime` 测试模式，输出当前判定与后续版本时间表；`testproc` 增加原神主窗口与终端回显检测。
- **配置**：新增 `focus_game` 段（默认启用），`burst_first_day_as_normal` 转为兼容保留项。
- **文档**：重写 `readme.md`，补充真实爆发期数据与判定口径。
- **工程**：`.gitignore` 增加 `.workbuddy/`。

### v0.1.2

- 以 v0.1.1 代码为基础重新整理并正式发布，功能与 v0.1.1 一致。
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
- 文档：重写 `readme.md`，修正 Markdown 转义符损坏（`\#`、`\*\*`、`&nbsp;`）的问题，并补充 v0.1.1 新特性说明。

### v0.1.0

- 首个版本：日期驱动的配置自动匹配（`wz` / `dm`）、紊乱爆发期判定、版本更新日延迟终止进程、UAC 权限校验、按日期分目录的日志系统、`testbgi` / `testtk` 测试模式、PyInstaller 单文件打包。

---

## 开发说明

### 代码结构

`BgiLauncher.py` 为单文件程序，主要模块：

- **终端输出**：`setup_console_stream()`、`console_write()`。
- **日志系统**：`setup_logger()`。
- **UAC 检测**：`is_admin()`、`request_admin()`。
- **配置管理**：`load_config()`、`save_config()`、`select_bgi_path_interactive()`。
- **日期计算**：`get_version_info()`、`get_version_start_date()`、`get_burst_window()`、`is_burst_period()`、`is_update_day()`、`is_maintenance_time()`、`log_version_context()`。
- **进程管理**：`get_process_pids()`、`is_process_running()`、`kill_processes()`、`pre_launch_process_check()`。
- **窗口处理**：`find_game_window()`、`bring_window_to_foreground()`。
- **焦点守护**：`FocusGuard`（热键轮询、触发匹配、切前台）。
- **启动**：`launch_bettergi()`。
- **日志采集**：`decode_output()`、`capture_bgi_log_baseline()`、`MergedLogWriter`、`BgiStdoutReader`、`BgiLogFollower`、`monitor_bettergi()`。
- **测试模式**：`test_bgi()`、`test_taskkill()`、`test_process()`、`test_time()`。
- **主流程**：`main()`。

### 扩展建议

- 若官方调整活动开启时间，只需修改常量区的 `BURST_START_DAY`、`BURST_START_HOUR`、`BURST_DURATION_DAYS`、`BURST_END_HOUR`。
- 若需发送通知（邮件、钉钉、企业微信），可在 `MergedLogWriter.write()` 的回调机制上再加一个监听器，匹配关键字后推送。
- 若需多语言，可将日志与提示文本提取为常量。

### 贡献

欢迎提交 Issue 和 Pull Request。请确保代码风格一致，并附上测试日志。

---

## 附录：需求提示词

### v0.1.0 最初需求

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

---

## 免责声明

1. 本工具仅用于辅助启动 BetterGI，不修改游戏文件，不提供任何游戏内作弊功能。
2. 使用本工具产生的一切后果由使用者自行承担。
3. 请遵守 BetterGI 的许可协议以及原神官方的用户协议。
4. 本项目由 DeepSeek v4.1f 编写，作者不对其稳定性、安全性作任何明示或暗示的担保。

---

**Enjoy your automated journey with BetterGI!** 🎮✨
