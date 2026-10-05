\# BetterGI 智能启动器



> \*\*本项目由 DeepSeek v4.1f 编写的 Vibe 项目\*\*  

> 一个根据日期自动匹配启动参数、智能切换 BetterGI 一条龙配置的 Windows 自动化工具。



---



\## 📖 目录



\- \[项目简介](#项目简介)

\- \[功能特性](#功能特性)

\- \[系统要求](#系统要求)

\- \[项目结构](#项目结构)

\- \[快速开始](#快速开始)

&nbsp; - \[1. 获取程序](#1-获取程序)

&nbsp; - \[2. 首次运行](#2-首次运行)

&nbsp; - \[3. 配置任务计划](#3-配置任务计划)

\- \[配置文件详解](#配置文件详解)

\- \[日期与版本规则](#日期与版本规则)

&nbsp; - \[版本周期计算](#版本周期计算)

&nbsp; - \[紊乱爆发期判定](#紊乱爆发期判定)

&nbsp; - \[版本更新日特殊处理](#版本更新日特殊处理)

\- \[命令行与测试模式](#命令行与测试模式)

\- \[日志系统](#日志系统)

\- \[打包指南](#打包指南)

\- \[常见问题 FAQ](#常见问题-faq)

\- \[开发说明](#开发说明)

\- \[附录：最初提示词](#附录最初提示词)

\- \[免责声明](#免责声明)



---



\## 项目简介



\*\*BetterGI 智能启动器\*\* 是一个专为 \[BetterGI](https://bettergi.com/)（一款原神自动化工具）设计的辅助启动程序。  

原神的每个版本持续 42 天，其中包含为期 10 天的“紊乱爆发期”。在爆发期与非爆发期，玩家通常需要使用不同的 BetterGI 一条龙配置。此外，版本更新当天存在停服维护，需要特殊处理。



手动切换配置既繁琐又容易遗忘。本项目通过读取系统日期，自动计算当前版本与版本内天数，判断是否处于紊乱爆发期，并据此选择对应的配置名称启动 BetterGI。同时，在版本更新日，程序会在启动 `dm` 配置一分钟之后自动终止 `Yuanshen.exe` 与 `BetterGI.exe`，避免维护期间的无意义运行。



本项目由 \*\*DeepSeek v4.1f\*\* 以 Vibe 编程方式生成，代码简洁、易于维护，适合无人值守的自动化场景。



---



\## 功能特性



\- ✅ \*\*自动版本计算\*\*：基于原神 7.0 版本（2026-08-12）为基准，自动推算任意日期的版本号与版本内天数。

\- ✅ \*\*紊乱爆发期识别\*\*：准确判断爆发期，自动切换 `wz` / `dm` 配置。

\- ✅ \*\*爆发期第一天可配置\*\*：默认将爆发期第一天视为非爆发期，可在配置文件中修改。

\- ✅ \*\*版本更新日特殊处理\*\*：更新当天启动 `dm` 后，延迟指定秒数自动终止游戏与 BetterGI 进程。

\- ✅ \*\*UAC 权限保护\*\*：启动时检测管理员权限，若无权限则弹窗提示并退出，确保任务计划程序以最高权限运行。

\- ✅ \*\*首次运行引导\*\*：自动创建配置文件，并弹出文件选择对话框让用户选择 `BetterGI.exe` 路径。

\- ✅ \*\*完整日志系统\*\*：按日期分目录记录日志，常规日志与错误日志分离，便于排查问题。

\- ✅ \*\*测试模式\*\*：内置 `testbgi` 与 `testtk` 参数，可快速验证 BetterGI 唤起与 taskkill 功能。

\- ✅ \*\*高度可配置\*\*：配置名称、爆发期规则、终止进程列表、延迟时间等均可通过 `config.json` 调整。

\- ✅ \*\*单文件打包\*\*：支持 PyInstaller 打包为独立 exe，附带自定义图标。



---



\## 系统要求



| 项目 | 要求 |

|------|------|

| 操作系统 | Windows 10 / Windows 11 |

| 运行权限 | \*\*管理员权限\*\*（必需） |

| Python 版本（开发） | Python 3.8 或更高 |

| BetterGI 版本 | 0.45.3 及以上（支持 `startOneDragon <配置名称>`） |

| 依赖库 | 标准库（`os`, `sys`, `json`, `time`, `ctypes`, `subprocess`, `logging`, `datetime`, `pathlib`, `tkinter`） |



> \*\*注意\*\*：`tkinter` 用于首次运行时的文件选择对话框，Windows 官方 Python 安装包默认包含。若使用精简版 Python，请确保安装 `tkinter`。



---



\## 项目结构



```

BetterGI\_Launcher/

├── bettergi\_launcher.py          # 主程序源码

├── config.json                   # 配置文件（首次运行自动生成）

├── README.md                     # 本说明文档

├── log/                          # 日志目录（自动创建）

│   └── 2026-10-05/

│       ├── 19-40-00.log          # 常规日志

│       └── error-19-40-00.log    # 错误日志

└── dist/

&nbsp;   └── BetterGI\_Launcher.exe     # 打包后的可执行文件

```



---



\## 快速开始



\### 1. 获取程序



\*\*方式一：直接下载打包好的 exe\*\*  

从发布页面下载 `BetterGI\_Launcher.exe`，放置于任意目录（建议单独建文件夹，例如 `D:\\Tools\\BetterGI\_Launcher\\`）。



\*\*方式二：从源码运行\*\*  

确保已安装 Python 3.8+，然后执行：



```bash

python bettergi\_launcher.py

```



\*\*方式三：自行打包\*\*  

参考 \[打包指南](#打包指南)。



\### 2. 首次运行



1\. \*\*右键点击\*\* `BetterGI\_Launcher.exe`，选择 \*\*“以管理员身份运行”\*\*。

2\. 程序启动后，若未找到 `config.json`，会自动创建默认配置，并弹出文件选择对话框。

3\. 在对话框中定位到你的 `BetterGI.exe`，例如：

&nbsp;  ```

&nbsp;  D:\\Tools\\Mhy tools\\BetterGI\\BetterGI.exe

&nbsp;  ```

4\. 选择完成后，程序保存配置并立即执行一次启动流程。

5\. 程序会在同目录下创建 `log` 文件夹，并写入本次运行日志。



> \*\*提示\*\*：如果未选择文件或路径无效，程序会记录错误日志并退出。你可以手动编辑 `config.json` 修正路径。



\### 3. 配置任务计划



为了实现每日 7:20 自动运行：



1\. 打开 \*\*任务计划程序\*\*（Task Scheduler）。

2\. 点击 \*\*“创建任务”\*\*（不是“创建基本任务”）。

3\. \*\*常规\*\*选项卡：

&nbsp;  - 名称：`BetterGI 智能启动器`

&nbsp;  - 勾选 \*\*“使用最高权限运行”\*\*（至关重要，否则会因缺少 UAC 权限而弹窗退出）。

&nbsp;  - 配置：选择你的 Windows 版本。

4\. \*\*触发器\*\*选项卡：

&nbsp;  - 新建触发器 → 每天 → 开始时间设置为 `07:20:00`。

&nbsp;  - 勾选 \*\*“启用”\*\*。

5\. \*\*操作\*\*选项卡：

&nbsp;  - 新建操作 → 启动程序 → 程序或脚本：选择 `BetterGI\_Launcher.exe` 的完整路径。

&nbsp;  - 起始于（可选）：填写 exe 所在目录，例如 `D:\\Tools\\BetterGI\_Launcher\\`。

6\. \*\*条件\*\*选项卡：

&nbsp;  - 取消勾选 \*\*“只有在计算机使用交流电源时才启动此任务”\*\*（如果是笔记本）。

&nbsp;  - 根据需求勾选 \*\*“如果计算机空闲则启动”\*\* 等。

7\. \*\*设置\*\*选项卡：

&nbsp;  - 勾选 \*\*“如果任务失败，按以下频率重新启动”\*\*，可设置 1 分钟、3 次。

&nbsp;  - 取消勾选 \*\*“如果任务运行时间超过以下时间，停止任务”\*\*（避免长时间运行被终止）。

8\. 保存任务。可右键手动运行一次进行测试。



---



\## 配置文件详解



首次运行自动生成 `config.json`，内容如下：



```json

{

&nbsp; "bettergi\_path": "D:\\\\Tools\\\\Mhy tools\\\\BetterGI\\\\BetterGI.exe",

&nbsp; "config\_name\_mapping": {

&nbsp;   "burst": "wz",

&nbsp;   "normal": "dm"

&nbsp; },

&nbsp; "special\_rules": {

&nbsp;   "burst\_first\_day\_as\_normal": true,

&nbsp;   "update\_day\_kill\_after\_dm": true,

&nbsp;   "kill\_delay\_seconds": 60,

&nbsp;   "kill\_processes": \["Yuanshen.exe", "BetterGI.exe"]

&nbsp; }

}

```



\### 字段说明



| 字段路径 | 类型 | 默认值 | 说明 |

|----------|------|--------|------|

| `bettergi\_path` | string | `""` | `BetterGI.exe` 的完整路径。首次运行时会弹出文件选择对话框，也可手动编辑。 |

| `config\_name\_mapping.burst` | string | `"wz"` | 紊乱爆发期使用的 BetterGI 一条龙配置名称。 |

| `config\_name\_mapping.normal` | string | `"dm"` | 非爆发期使用的配置名称。 |

| `special\_rules.burst\_first\_day\_as\_normal` | bool | `true` | 爆发期第一天是否视为非爆发期。`true` 表示第一天仍用 `dm`。 |

| `special\_rules.update\_day\_kill\_after\_dm` | bool | `true` | 版本更新日是否执行终止进程操作。 |

| `special\_rules.kill\_delay\_seconds` | int | `60` | 启动 `dm` 后等待多少秒再终止进程。 |

| `special\_rules.kill\_processes` | array | `\["Yuanshen.exe", "BetterGI.exe"]` | 需要终止的进程名称列表。 |



\### 适配其他配置名称



如果你的 BetterGI 一条龙配置名称不是 `wz` 和 `dm`，只需修改 `config\_name\_mapping`：



```json

"config\_name\_mapping": {

&nbsp; "burst": "你的爆发期配置名",

&nbsp; "normal": "你的常规配置名"

}

```



例如，若配置名为 `爆发` 和 `日常`：



```json

"config\_name\_mapping": {

&nbsp; "burst": "爆发",

&nbsp; "normal": "日常"

}

```



\### 关闭更新日终止进程



若你不希望更新日自动终止游戏，设置：



```json

"update\_day\_kill\_after\_dm": false

```



\### 调整终止延迟



若希望启动后等待 120 秒再终止：



```json

"kill\_delay\_seconds": 120

```



---



\## 日期与版本规则



\### 版本周期计算



\- 原神每个版本持续 \*\*42 天\*\*。

\- 基准版本：\*\*7.0\*\*，开始日期 \*\*2026-08-12\*\*。

\- 后续版本依次为 7.1（2026-09-23）、7.2（2026-11-04）……  

\- 版本号递增规则：主版本号不变，次版本号 +1；当次版本号达到 10 时，主版本号 +1，次版本号归零（例如 7.9 → 8.0）。

\- 程序通过计算目标日期与基准日期的天数差，除以 42 得到版本偏移量，再取余得到版本内天数（0 表示版本更新当天）。



\### 紊乱爆发期判定



\- 紊乱爆发期：版本更新后 \*\*第 8 天 10:00\*\* 开始，持续 \*\*10 天\*\*，至 \*\*第 17 天 03:59\*\* 结束。

\- 以 7.0 版本为例：

&nbsp; - 版本开始：2026-08-12

&nbsp; - 爆发期开始：2026-08-19 10:00（第 8 天）

&nbsp; - 爆发期结束：2026-08-29 03:59（第 17 天）

\- 程序判定逻辑：

&nbsp; 1. 若 `day\_in == 0`（版本更新当天），强制视为非爆发期。

&nbsp; 2. 若 `day\_in == 7`（爆发期第一天）且 `burst\_first\_day\_as\_normal = true`，视为非爆发期。

&nbsp; 3. 若 `day\_in` 在 `\[7, 16]` 范围内（即第 8 天至第 17 天），且最后一天未超过 03:59，则视为爆发期。

&nbsp; 4. 其他情况均为非爆发期。



> \*\*注意\*\*：程序在每日 7:20 运行，因此爆发期第一天（第 8 天）的 10:00 尚未到达，默认视为非爆发期，符合实际需求。该行为可通过 `burst\_first\_day\_as\_normal` 修改。



\### 版本更新日特殊处理



\- 版本更新当天（`day\_in == 0`），游戏停服维护至 \*\*10:00\*\*。

\- 程序在更新日启动 `dm` 配置后，等待 `kill\_delay\_seconds` 秒（默认 60 秒），然后依次终止 `kill\_processes` 列表中的进程。

\- 该功能由 `update\_day\_kill\_after\_dm` 控制，默认开启。

\- 若不需要，可设为 `false`。



---



\## 命令行与测试模式



程序支持以下命令行参数：



| 参数 | 说明 |

|------|------|

| （无） | 正常启动流程，根据日期自动选择配置并启动 BetterGI。 |

| `testbgi` | 测试模式：验证是否能够唤起带有 UAC 权限的 BetterGI。 |

| `testtk` | 测试模式：验证 taskkill 功能是否正常。 |



\### 测试 BetterGI 唤起



```bash

BetterGI\_Launcher.exe testbgi

```



程序会输出 BetterGI 路径、路径是否存在、当前管理员权限，并尝试执行 `BetterGI.exe --help`。若成功，说明 BetterGI 可正常唤起。



\### 测试 taskkill



```bash

BetterGI\_Launcher.exe testtk

```



程序会启动一个 `notepad.exe`，等待 2 秒后使用 `taskkill /F /IM notepad.exe` 终止它，并输出结果。若成功，说明 taskkill 功能正常。



---



\## 日志系统



\- 日志根目录：程序所在目录下的 `log` 文件夹。

\- 按日期分目录：`log/YYYY-MM-DD/`。

\- 每次运行生成两个日志文件：

&nbsp; - 常规日志：`HH-MM-SS.log`（记录 DEBUG 及以上级别）。

&nbsp; - 错误日志：`error-HH-MM-SS.log`（仅记录 ERROR 及以上级别）。

\- 日志格式：`时间 \[级别] 消息`。

\- 示例结构：



```

log/

└── 2026-10-05/

&nbsp;   ├── 19-40-00.log

&nbsp;   └── error-19-40-00.log

```



\- 控制台同时输出 INFO 及以上级别的日志，方便调试。

\- 所有异常均会记录到错误日志，便于无人值守时事后排查。



---



\## 打包指南



\### 使用 PyInstaller 打包



1\. 安装 PyInstaller：



```bash

pip install pyinstaller

```



2\. 执行打包命令（图标路径按你的实际路径替换）：



```bash

pyinstaller --onefile --windowed --icon="D:\\asus\\Documents\\mic\\BlackScreen\_240x240\_32bit.ico" --name "BetterGI\_Launcher" bettergi\_launcher.py

```



3\. 打包完成后，可执行文件位于 `dist/BetterGI\_Launcher.exe`。



\### 参数说明



| 参数 | 说明 |

|------|------|

| `--onefile` | 打包为单个 exe 文件，便于分发。 |

| `--windowed` | 不显示控制台窗口（GUI 模式）。若需要看控制台输出，可去掉此参数。 |

| `--icon` | 指定图标文件路径，必须为 `.ico` 格式。 |

| `--name` | 指定输出的 exe 名称。 |



\### 图标要求



\- 路径：`D:\\asus\\Documents\\mic\\BlackScreen\_240x240\_32bit.ico`

\- 格式：ICO，尺寸建议包含 256x256、128x128、64x64、48x48、32x32、16x16 等多分辨率。

\- 若图标文件不存在，PyInstaller 会报错，请确保路径正确。



\### 打包后的目录结构



```

dist/

└── BetterGI\_Launcher.exe

```



首次运行时，exe 会在同目录下生成 `config.json` 和 `log` 文件夹。



---



\## 常见问题 FAQ



\### Q1：程序启动后弹窗提示“权限不足”并退出？



\*\*原因\*\*：未以管理员身份运行。  

\*\*解决\*\*：右键 exe → “以管理员身份运行”。若通过任务计划程序，请勾选“使用最高权限运行”。



\### Q2：首次运行没有弹出文件选择对话框？



\*\*原因\*\*：可能已存在 `config.json`，或 `tkinter` 不可用。  

\*\*解决\*\*：删除 `config.json` 后重新运行；确保 Python 安装包含 `tkinter`。也可手动编辑 `config.json` 填写 `bettergi\_path`。



\### Q3：BetterGI 启动失败，日志显示“路径无效”？



\*\*原因\*\*：`bettergi\_path` 配置错误或文件不存在。  

\*\*解决\*\*：检查路径是否正确，注意反斜杠转义（JSON 中需使用 `\\\\`）。建议使用绝对路径。



\### Q4：配置名称 `wz` / `dm` 不存在怎么办？



\*\*原因\*\*：BetterGI 中未创建对应名称的一条龙配置。  

\*\*解决\*\*：在 BetterGI 中创建名为 `wz` 和 `dm` 的配置，或修改 `config.json` 中的 `config\_name\_mapping` 为实际配置名。



\### Q5：更新日终止进程没有生效？



\*\*原因\*\*：`update\_day\_kill\_after\_dm` 为 `false`，或当天不是版本更新日。  

\*\*解决\*\*：检查配置；确认日期计算是否正确（基准日期 2026-08-12，周期 42 天）。



\### Q6：日志文件在哪里？



\*\*位置\*\*：程序同目录下的 `log/YYYY-MM-DD/` 文件夹。  

\*\*排查\*\*：优先查看 `error-\*.log`，其中记录了所有错误信息。



\### Q7：如何修改爆发期第一天视为非爆发期的行为？



\*\*修改\*\*：将 `config.json` 中 `special\_rules.burst\_first\_day\_as\_normal` 设为 `false`。  

\*\*效果\*\*：爆发期第一天（第 8 天）将直接使用 `wz` 配置。



\### Q8：支持其他版本的日期计算吗？



\*\*支持\*\*：基准版本和日期在代码中定义为 `BASE\_VERSION = (7, 0)` 和 `BASE\_DATE = date(2026, 8, 12)`。若未来版本周期变化，可修改这两个常量。



---



\## 开发说明



\### 代码结构



\- `bettergi\_launcher.py` 为单文件程序，主要模块：

&nbsp; - \*\*日志系统\*\*：`setup\_logger()` 创建按日期分目录的日志。

&nbsp; - \*\*UAC 检测\*\*：`is\_admin()`、`request\_admin()`。

&nbsp; - \*\*配置管理\*\*：`load\_config()`、`save\_config()`、`select\_bgi\_path\_interactive()`。

&nbsp; - \*\*日期计算\*\*：`get\_version\_info()`、`is\_burst\_period()`、`is\_update\_day()`、`is\_maintenance\_time()`。

&nbsp; - \*\*启动与进程管理\*\*：`launch\_bettergi()`、`kill\_processes()`。

&nbsp; - \*\*测试模式\*\*：`test\_bgi()`、`test\_taskkill()`。

&nbsp; - \*\*主流程\*\*：`main()`。



\### 扩展建议



\- 若需支持更多特殊日期规则，可在 `special\_rules` 中增加字段，并在 `main()` 中读取。

\- 若需发送通知（如邮件、钉钉），可在关键节点添加钩子。

\- 若需多语言，可将日志和提示文本提取为常量。



\### 贡献



欢迎提交 Issue 和 Pull Request。请确保代码风格一致，并附上测试日志。



---



\## 附录：最初提示词



以下为用户最初给出的完整需求提示词，本项目即根据此需求由 DeepSeek v4.1f 编写。



```text

写一个python，用于在不同的日期，匹配不同的启动参数，启动我的Bettergi



配置文件包括四项，在首次启动时 自动创建 bgi路径允许弹出一个文件资源管理器，然后用户自行选择

1、better文件路径 参考“D:\\Tools\\Mhy tools\\BetterGI\\BetterGI.exe"

2、bgi启动参数的的匹配规则——以兼容其他配置名称或日期要求

3、后面提到的紊乱爆发期与版本更新特殊优化的开启状态



bettergi文档：

\# 执行 BetterGI 一条龙页面上选定的配置

BetterGI.exe startOneDragon

BetterGI.exe --startOneDragon

start bettergi://startOneDragon



\# 执行给定的一条龙配置（如果找不到就用页面上选定的）（需要 0.45.3 及以上版本）

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

然后使用 D:\\asus\\Documents\\mic\\BlackScreen\_240x240\_32bit.ico 作为图标打包该程序

并允许附带启动参数 testbgi 来测试是否能唤起带有uac权限的bgi testtk 来测试是否能够正常执行taskkill

启动时若不带uac 则直接弹窗，并报错退出

由于无人值守，日志文件报错至同目录下log文件夹，参考：

└─log

&nbsp;   └─2026-10-05

&nbsp;           19-40-00.log

&nbsp;           error-19-40-00.log

```



---



\## 免责声明



1\. 本工具仅用于辅助启动 BetterGI，不修改游戏文件，不提供任何游戏内作弊功能。

2\. 使用本工具产生的一切后果由使用者自行承担。

3\. 请遵守 BetterGI 的许可协议以及原神官方的用户协议。

4\. 本项目由 DeepSeek v4.1f 生成，作者不对其稳定性、安全性作任何明示或暗示的担保。



---



\*\*Enjoy your automated journey with BetterGI!\*\* 🎮✨

