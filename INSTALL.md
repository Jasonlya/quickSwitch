# QuickSwitch 安装与使用指南

> 面向使用者。下载与首次使用速览见根目录 [README.md](README.md)；完整配置、通信协议、验收与打包发布见 [docs/TECHNICAL.md](docs/TECHNICAL.md)。

一台 Windows（键鼠接在它上面）＋ 一台 Mac，共用一个显示器。按一次快捷键，显示器输入源和键鼠控制权一起切过去；
即使对端没响应，本机这一半也照样生效。

---

## 0. 三十秒速览

| 步骤 | Windows（server） | macOS（client） |
| --- | --- | --- |
| 1 | 键鼠共享核心自动按服务端启动，无需打开 Deskflow | 键鼠共享核心自动按客户端启动，无需打开 Deskflow |
| 2 | 无需额外 DDC 工具（内置 DXVA2） | 装 m1ddc（Apple Silicon） |
| 3 | 运行 QuickSwitch | 运行 QuickSwitch |
| 4 | 填对方 IP、同一端口、同一个 `auth.secret` | 同左 |
| 5 | `--status` 看到「已连接」＋「密钥校验：已通过」 | 同左 |

---

## 1. 先决条件

| 项目 | 要求 | 说明 |
| --- | --- | --- |
| 网络 | 两台机器在同一局域网 | 有线/无线都行，但要能互 ping 通；跨网段需先在路由器放行 |
| 显示器 | 支持 DDC/CI（VCP 0x60 输入源） | 多数显示器默认开启；个别型号要在 OSD 菜单里打开 DDC/CI |
| 连线 | 建议视频线直连两台机器 | 中间经过扩展坞 / KVM 可能读不到输入源 |
| 键鼠 | 物理接在 Windows 上 | macOS 端通过内置键鼠共享借用 |
| 权限 | Windows 侧注册全局热键需管理员 | 托盘图标与网页控制不需要 |

软件清单：

| 软件 | 作用 | 是否必须 |
| --- | --- | --- |
| QuickSwitch | 切显示器输入源 + 通知对端 | **必须**，本文档安装的就是它 |
| Deskflow 无界面核心 | 一套键鼠控制两台机器、剪贴板文本共享 | 已内置并由 QuickSwitch 自动管理，无需单独下载或打开客户端；GPL-2.0，见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) |
| ControlMyMonitor | Windows 侧可选的外部 DDC 回退 | 可选；Windows 端默认使用系统内置 DXVA2 |
| m1ddc | macOS 侧 DDC/CI 工具 | 必须（macOS 端） |
| LocalSend / Tailscale | 传文件 / 固定虚拟 IP | 可选 |

### 1.1 开启显示器 DDC/CI

DDC/CI 是显示器自己的功能，开关在**显示器 OSD 菜单**里，不在 Windows「显示设置」里。
不同品牌的菜单名称和位置不同，按下面顺序找：

1. 按显示器底部、侧面或背面的实体按键/摇杆，呼出 OSD 菜单。
2. 进入「系统 / System」「设置 / Settings」「其他设置 / Other Settings」「OSD 设置 / OSD Setup」或「管理 / Management」。
3. 找到「DDC/CI」并设为「开 / On」。有些显示器会写成 **DDC/CI Support**、**Monitor Control**、**MCCS** 或 **Display Data Channel**。
4. 保存并退出菜单，等 5 秒后再回到 QuickSwitch 读取/切换。

常见品牌的大致位置（仅作参考，实际以显示器菜单为准）：

| 品牌 | 常见路径 |
| --- | --- |
| Dell | Menu → Others → DDC/CI |
| LG | Settings → General → DDC/CI |
| BenQ | Menu → System → Other Settings → DDC/CI |
| ASUS | Menu → System Setup → DDC/CI |
| HP | Menu → Management → DDC/CI |
| AOC / Philips | Menu → OSD Setup / Settings → DDC/CI |

如果菜单里完全没有 DDC/CI 选项，先把视频线直连显示器，绕开 KVM、扩展坞和切换器再试；仍找不到时，说明该显示器可能不支持 DDC/CI，无法用 QuickSwitch 切换输入源。

---

## 2. 安装

推荐直接从 [GitHub Releases](https://github.com/Jasonlya/quickswitch/releases/latest) 下载安装包。
安装包自带 Python 运行时、托盘依赖和设置窗口，目标机不需要安装 Python 或 pip。

### 2.1 macOS（推荐安装包）

QuickSwitch macOS 版只支持 Apple Silicon（M1/M2/M3/M4），不再提供 Intel Mac 安装包。

在终端运行 `uname -m` 应显示 `arm64`。下载最新 Release 里的 `QuickSwitch-*-macOS-arm64.dmg`。

安装步骤：

1. 打开 DMG，把 `QuickSwitch.app` 拖到 `Applications`（应用程序）文件夹。
2. 首次打开若提示「无法验证开发者」：在 App 上右键 →「打开」→ 再点「打开」。
   当前 Release 未签名 / 未公证；如果系统仍拦截，可到「系统设置 → 隐私与安全性」点「仍要打开」。
3. 首次启动可能弹「允许 QuickSwitch 查找并连接到本地网络上的设备」→ 点**允许**；
   拒绝的话对端通知发不出去（本机切换仍可用）。
4. 菜单栏出现 QuickSwitch 图标 = 启动成功，首次运行会自动弹出配置向导。程序不进 Dock，属于正常的菜单栏程序。

命令行自检：

```bash
/Applications/QuickSwitch.app/Contents/MacOS/QuickSwitch --status
```

如果双击没有反应、终端启动一直卡住，或此前执行 `xattr -rd` 时看到大量
`Operation not permitted`，通常是 macOS 缓存了错误的启动策略记录。先彻底退出 QuickSwitch，
再刷新 LaunchServices：

```bash
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f /Applications/QuickSwitch.app
open -a /Applications/QuickSwitch.app
```

不要再递归执行 `xattr -rd com.apple.quarantine`。较新的 macOS 会保护 App 包内的文件，
递归修改会失败并可能留下异常的启动记录；正常安装只需要上面的「右键 → 打开」。

### 2.2 Windows（推荐安装包）

1. 下载并双击最新 Release 里的 `QuickSwitch-Setup-*.exe`，在 UAC 提示中点「是」。
2. 未签名版本首次运行可能弹 SmartScreen：点「更多信息」→「仍要运行」。
3. 安装程序会创建桌面和开始菜单快捷方式，自动放行 TCP 8765（切换通知）、UDP 8766（自动发现）和键鼠共享 TCP 24800，并写入卸载入口。
4. 从桌面或开始菜单启动 QuickSwitch；首次运行会自动弹出配置向导。
5. Windows 全局热键需要管理员权限，快捷方式已设置为以管理员身份运行；每次启动出现 UAC 时点「是」即可。

安装目录中的 `deskflow\` 是随包内置的官方 Deskflow 无界面核心。它由 QuickSwitch 自动启动，不需要单独打开，也没有客户端快捷方式。

命令行自检：

```bat
"%ProgramFiles%\QuickSwitch\QuickSwitch.exe" --status
```

> 当前 Release 未使用商业代码签名证书。macOS Gatekeeper 与 Windows SmartScreen 会给出一次提示，
> 按上面的「右键打开 / 仍要运行」操作即可。正式对外分发若希望完全无提示，需要 Developer ID 公证与 Windows 代码签名。

### 2.3 从源码运行（开发者）

```bash
cd quickswitch
python3 -m pip install -r requirements.txt
python3 main.py --init-config     # 生成 ~/.quickswitch/config.json
python3 main.py --status          # 自检
python3 main.py                   # 常驻运行
```

Windows 可以直接双击 `scripts\quickstart-windows.bat`（保留控制台日志，便于排错）。

---

## 3. 首次配置（两端各做一次）

### 3.1 第一次启动

安装包首次启动时会自动弹出**配置向导**，并在下面位置生成配置：

- macOS：`~/.quickswitch/config.json`
- Windows：`%USERPROFILE%\.quickswitch\config.json`

如果没有自动打开：右键菜单栏 / 托盘图标 →「打开设置窗口」。向导会停在最后一个完成步骤，或在下次启动时重新打开。

也可以手动生成或查看配置文件：

```bash
# macOS（成品包）
/Applications/QuickSwitch.app/Contents/MacOS/QuickSwitch --init-config

# Windows（成品包）
"%ProgramFiles%\QuickSwitch\QuickSwitch.exe" --init-config

# 源码
python main.py --init-config
```

也可以直接在设置窗口点「更多信息与设置」→「配置」区块里改（只允许改白名单字段），省得手动编辑 JSON。

### 3.2 按向导完成四步

| 步骤 | 要做什么 | 说明 |
| --- | --- | --- |
| 连接 | 选「自动发现」，或填另一台电脑的 IP | 自动发现使用 UDP 8766；手动模式把另一台电脑的「本机 IP」填进来。TCP 监听端口保持 `8765` |
| 安全 | 生成 6 位配对码，并填到另一台电脑 | 两端配对码必须完全相同；点「生成」即可 |
| 显示器 | 读取当前输入源并标记 Mac / Windows | 不同品牌取值可能不同；也可以直接填写或点「探测」 |
| 完成 | 保存后退出并重新打开 QuickSwitch | 角色会按系统自动选择：macOS = `client`，Windows = `server`，只有 Windows 端注册全局热键 |

向导左侧会显示本机局域网 IP；把它填到**另一台电脑**的连接步骤里。
完成后要退出并重新打开 QuickSwitch，连接方式、角色和配对码才会生效。

### 3.3 高级配置与重新运行向导

以后要修改配置：展开「更多信息与设置」→「配置」，点「重新运行配置向导」；或直接编辑白名单字段。

Windows 端默认使用系统内置 DXVA2，不需要配置外部程序。以下字段仅用于诊断或可选回退：

| 字段 | 说明 |
| --- | --- |
| `ddc.display_index` | 选择第几个物理显示器（从 1 开始）；单屏保持 `1` |
| `ddc.controlmyMonitor_path` | 可选回退工具路径；只有原生 DXVA2 失败且你确实安装了 ControlMyMonitor 时才需要填 |
| `ddc.monitor_id` | 仅供外部 ControlMyMonitor 回退使用，原生 DXVA2 不依赖它 |

macOS 端确认 `ddc.m1ddc_path`（默认 `/opt/homebrew/bin/m1ddc`）。如果使用 Homebrew 安装，路径通常是 `/opt/homebrew/bin/m1ddc`。

### 3.4 识别显示器输入源

不同品牌取值不一样，别猜，让工具测：

```bash
python3 main.py --detect-inputs                                # 交互式：探测候选值 → 标注哪台机器 → 回读校验 → 写回配置
python3 main.py --detect-inputs --mac-input 15 --win-input 17  # 已知取值时直接写
python3 main.py --detect-inputs --no-write                     # 只看结果，不改配置
```

成品包同样可以带参数运行（路径见 3.1）。设置窗口里也有「探测输入源」按钮，效果相同。

### 3.5 配 6 位配对码（必须）

`auth.secret` 为空时，同网段任何程序只要往 8765 发一行 JSON 就能切走你的显示器。推荐直接在设置页的「安全」区块点「生成」，得到 6 位无歧义配对码，再填到另一台电脑。也可以命令行生成：

```bash
python3 main.py --gen-secret
# {"auth": {"secret": "K7QM9X"}}
```

把同一个 6 位配对码填进**两端**的「安全」区块（配置文件里对应 `auth.secret`），保存后重启两端。6 位码便于家用局域网配对；如果在访客网络或公共 WiFi 使用，建议手动改成更长的随机值。旧版生成的长密钥仍然兼容，不需要修改。

### 3.6 自检：什么才算配好了

两端各跑一次 `--status`，重点是这三行：

```
对端         : 192.168.1.101:8765 已连接（对端 DESKTOP-ABC，role=server，版本=2.0.3）
密钥校验     : 已通过（hmac-sha256）
DDC 后端     : 已找到 /opt/homebrew/bin/m1ddc
```

Windows 端正常时应显示：

```
DDC 后端     : Windows 原生 DDC（DXVA2）已检测到 1 个显示器：...
读取方式     : Windows 原生 DXVA2（无需外部命令）
```

| 输出 | 含义 |
| --- | --- |
| 对端「连接失败」 | 对端没运行、IP / 端口错、或防火墙挡了 |
| 密钥校验「未配置」 | 本端没填配对码，切换请求不会校验 |
| 密钥校验「未通过」 | 两端配对码不一致 |
| DDC「未找到」 | 仅 macOS 需要 m1ddc；Windows 出现此提示说明当前是旧版安装包，或原生 DXVA2 未检测到显示器 |
| 当前输入源「无法读取」 | 显示器未开启/不支持读 VCP 0x60，或当前 DDC 后端不可用；不影响发送切换 |

---

## 4. 日常使用

### 4.1 三种触发方式

| 方式 | 怎么用 | 前提 |
| --- | --- | --- |
| 托盘 / 菜单栏 | 右键图标 →「打开设置窗口」/「切到 Mac」/「切到 Windows」/「查看状态（写入日志）」/「退出」 | 无 |
| 全局热键 | `Ctrl+Alt+1` → Mac，`Ctrl+Alt+2` → Windows | 只在 Windows `server` 端注册，需管理员权限；macOS 界面会标注「Windows 键盘」 |
| 设置窗口 | 应用内原生 WebView 弹窗，点按钮或展开设置 | 程序正在运行 |

### 4.2 设置窗口与本地控制台

只监听 `127.0.0.1`，每次启动生成新令牌：

- 首次启动会自动弹出应用内配置向导，不打开浏览器标签页；
- 设置窗口由独立的 WebView 子进程承载，托盘和全局热键仍在主进程运行；
- Windows 缺少 WebView2、或系统不支持 WebView 时，会自动回退到默认浏览器；
- 启动日志里会打印 `Web 控制台：http://127.0.0.1:8767/?t=...`；
- 成品包没有控制台窗口，去 `~/.quickswitch/quickswitch.log` 里找最后一条
  `Web 控制台已启动：...`，把整条地址粘进浏览器。

主页面只保留「切到 Mac / Windows」两个按钮；鼠标停在按钮上会显示当前输入源、对端连接、
密钥校验、DDC 和快捷键摘要。点「更多信息与设置」后，才能读取/探测输入源、查看连接与
DDC 命令原文、修改白名单配置和查看事件日志。地址里的 `?t=` 不要发给别人。

### 4.3 键鼠共享（已集成，无需打开 Deskflow）

QuickSwitch 会在后台自动启动随包内置的 `deskflow-core`，并根据 QuickSwitch 配置生成键鼠共享配置。**不需要安装 Deskflow，也不需要打开它的客户端页面。**

- Windows 自动作为服务端，监听 TCP `24800`。
- macOS 自动作为客户端，连接 QuickSwitch 发现或配置的 Windows 地址。
- 两台电脑的屏幕相对位置由 `deskflow.mac_side` 控制：Mac 在左选 `left`，在右选 `right`。
- QuickSwitch 的两个切换热键会自动写入键鼠共享配置，一次按键同时切换显示器和键鼠。
- 键鼠共享连接后，剪贴板默认双向同步文本、HTML 和图片；可在「配置 → 键鼠共享」关闭，或把单次上限从默认 `16 MB` 调到 `1-128 MB`。上限以 Windows 服务端为准。
- 切换热键可在「配置 → 热键」点「录入」直接按键修改；至少需要一个 Ctrl/Alt/Shift/Win 修饰键，F1-F12 可单独使用。保存后旧热键立即注销、新热键立即注册。
- macOS 客户端默认保留自己的当前输入源，不跟随 Windows 的键盘布局；只有两台电脑安装了完全相同的键盘布局时，才在设置页开启「同步键盘语言」。
- 退出 QuickSwitch 时，内置核心会同步停止；需要单独重启时，用设置页的「重启键鼠共享」或托盘菜单。

默认状态目录为 `~/.quickswitch/deskflow`，里面有 `Deskflow.conf`、`Deskflow-server.conf`（仅服务端）、`deskflow.pid` 和 `deskflow.log`。主界面按钮下方会显示「键鼠共享 · 已连接 / 等待连接 / 连接异常」状态；点击后可展开模式、活动 TCP 连接数、最近错误、日志路径和原始日志。只有检测到活动连接或 Deskflow 明确报告连接成功时，才会显示「已连接」。

macOS 首次使用只需授权一次：

1. 打开「系统设置 → 隐私与安全性」。
2. 在**辅助功能**和**输入监控**中允许 QuickSwitch；如果列表里出现 `Deskflow` 或 `deskflow-core`，也一并打开。设置页提供两个独立按钮，可直接打开对应设置页。
3. 在**本地网络**中允许 QuickSwitch 访问局域网。
4. 回到 QuickSwitch 设置页，点「重启键鼠共享」。

如果日志出现 `assistive devices does not trust this process`、`process is not trusted anymore` 或 `failed to create quartz event tap`，说明 macOS 尚未授权键鼠控制；主界面会显示「需要权限」，首次出现时 QuickSwitch 也会自动打开一次辅助功能设置页。

**已授权但仍提示「需要权限」**：这是 `v2.0.4` 及更早版本的已知问题。旧安装包使用 Ad-hoc 签名，macOS 会把授权绑定到当次构建的 cdhash；重新打包或升级后 cdhash 变化，系统设置里开关看起来是打开的，实际已经匹配不到新 App。`v2.0.5` 起改为稳定的 designated requirement，后续升级不会再次失效。升级后按下面步骤修复一次：

1. 展开「更多信息与设置 → 键鼠共享」，点「重建 macOS 授权」；程序会清除旧记录、自动重启并打开系统设置。也可以完全退出 QuickSwitch 后在终端执行：

   ```bash
   /Applications/QuickSwitch.app/Contents/MacOS/QuickSwitch --reset-macos-permissions
   ```

2. 系统设置打开后，在**辅助功能**和**输入监控**中重新打开 QuickSwitch。若列表里还留着同名旧条目，先点 `−` 移除，再点 `＋` 添加 `/Applications/QuickSwitch.app`。
3. 回到设置页点「重启键鼠共享」。状态应变为「已连接」，日志不再出现 `failed to create quartz event tap`。

Windows 安装包会自动放行 TCP `24800`；源码运行或手工安装时需自行在防火墙放行该端口。

验收方法：在 Windows 上按 `Ctrl+Alt+1`，显示器应切到 Mac，同时 Windows 键鼠应能控制 Mac；按 `Ctrl+Alt+2` 应反向切回。若显示器切了但键鼠没过去，先看主界面键鼠共享状态是否为「已连接」；「等待连接」表示共享核心已运行但两端尚未握手，「连接异常」会给出超时、拒绝连接或权限问题，再检查 macOS 权限和 Windows 的 TCP `24800` 防火墙规则。

---

## 5. 开机自启

### 5.1 成品包

**macOS**：系统设置 → 通用 → 登录项与扩展 →「＋」→ 选 `/Applications/QuickSwitch.app`。

**Windows**（管理员 PowerShell，指向安装后的 exe，不需要 Python）：

```powershell
$exe = "$env:ProgramFiles\QuickSwitch\QuickSwitch.exe"
$action = New-ScheduledTaskAction -Execute $exe -WorkingDirectory "$env:ProgramFiles\QuickSwitch"
$trigger = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName QuickSwitch -Action $action -Trigger $trigger -Principal $principal -Force

# 立即启动 / 查看状态 / 卸载
Start-ScheduledTask -TaskName QuickSwitch
Get-ScheduledTask -TaskName QuickSwitch | Get-ScheduledTaskInfo
Unregister-ScheduledTask -TaskName QuickSwitch -Confirm:$false
```

### 5.2 源码运行

| 平台 | 做法 |
| --- | --- |
| Windows | `powershell -ExecutionPolicy Bypass -File scripts\install-task.ps1 -ProjectDir C:\Tools\quickswitch` |
| macOS | 把 `scripts/com.quickswitch.agent.plist` 里的路径改成实际目录，`cp` 到 `~/Library/LaunchAgents/` 后 `launchctl load -w ...`；或把启动脚本加进登录项 |

> 这两个脚本内部执行的是 `python main.py`，所以**不适用于成品包**，成品包请用 5.1。

---

## 6. 升级与卸载

| 操作 | macOS | Windows |
| --- | --- | --- |
| 升级 | 退出程序 → 打开新 DMG → 把新 App 拖进「应用程序」覆盖旧版 | 退出程序 → 运行新版 Setup 安装包覆盖安装 |
| 配置 | 保留在 `~/.quickswitch/config.json`，升级不会覆盖 | 同左 |
| 卸载 | 删 App；要连配置一起清就删 `~/.quickswitch/` | 「设置 → 应用 → QuickSwitch → 卸载」；要连配置一起清再删 `%USERPROFILE%\.quickswitch\` |

清理 Windows 防火墙规则：

```powershell
Remove-NetFirewallRule -DisplayName "QuickSwitch"
Remove-NetFirewallRule -DisplayName "QuickSwitch Discovery"
```

---

## 7. 常见问题

| 现象 | 原因 / 处理 |
| --- | --- |
| macOS 双击提示「无法验证开发者」 | 未签名 / 未公证。右键 → 打开；或系统设置 → 隐私与安全性 → 仍要打开 |
| macOS 双击无反应，或终端启动卡在 `_dyld_start` | 启动策略缓存异常。先退出所有 QuickSwitch 进程，再执行 `/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f /Applications/QuickSwitch.app`，然后重新打开 App |
| macOS 执行 `xattr -rd` 报 `Operation not permitted` | 新版 macOS 会保护 App 包内容，不需要递归清理隔离属性。停止该命令，改用「右键 App → 打开」；若仍无反应，按上一行刷新 LaunchServices |
| macOS 提示 app「已损坏」 | 先重新从 DMG 拖入「应用程序」；仍被拦截时右键 → 打开，或到系统设置 → 隐私与安全性 → 仍要打开。不要递归修改 App 包内的扩展属性 |
| macOS 已授权但仍提示「需要权限」 | `v2.0.4` 及更早版本把 Ad-hoc 授权绑在 cdhash 上，升级后会失效。升级到 `v2.0.5`，点设置页「重建 macOS 授权」，再在「辅助功能」和「输入监控」中重新打开 QuickSwitch；旧同名条目先移除再添加 |
| Windows 首次运行弹 SmartScreen | 未签名。更多信息 → 仍要运行；正式分发需代码签名 |
| Windows 设置窗口字体模糊 | 升级到 `v1.0.2` 或更高；新版已启用 Per-Monitor V2 DPI 感知。必要时更新 Microsoft Edge WebView2 Runtime |
| Windows 启动时有多个终端窗口闪动 | 升级到 `v2.0.1` 或更高。旧版会反复调用 `tasklist`/DDC 工具等控制台程序；新版统一使用 `CREATE_NO_WINDOW` 隐藏子进程窗口 |
| Windows 托盘可以打开，但设置窗口完全不显示 | 升级到 `v2.0.3` 或更高。`v2.0.2` 已移除误继承的 `SW_HIDE`；`v2.0.3` 覆盖安装时会自动结束旧进程，WebView 启动失败时会回退到默认浏览器。安装完仍建议从托盘「退出」后再重新打开一次 |
| Mac 上按界面显示的 `Ctrl+Alt+1/2` 没反应 | 热键只在连接键鼠的 Windows 端注册。请使用 Windows 键盘，或直接点 Mac 菜单栏/设置页的切换按钮；界面上的热键来源会标注为「Windows 键盘」 |
| 剪贴板没有同步 | 确认键鼠共享状态为「已连接」，并在「配置 → 键鼠共享」勾选「共享剪贴板」。检查复制内容是否超过「剪贴板上限」；客户端沿用 Windows 端设置。保存配置会自动重启共享核心 |
| 自定义热键保存失败 | 热键至少包含一个 Ctrl/Alt/Shift/Win 修饰键，单键仅支持 F1-F12；两个方向不能使用同一组合键。可点「默认」恢复 `Ctrl+Alt+1/2` |
| 切回 Windows 后短暂卡顿或热键失效 | 新版本已并行执行本机 DDC 与对端确认，本机成功后立即释放热键；对端较慢时只转后台确认。请确认使用的是包含该修复的版本，并重启 QuickSwitch |
| 切到 Mac 后键位不对或输入法被改 | 升级到 `v2.0.4` 或更高。默认关闭 Deskflow 语言同步，保留 Mac 当前输入源；在设置页点「重启键鼠共享」后生效。只有两端键盘布局完全相同时才开启「同步键盘语言」 |
| Windows 安装过程或完成页中文乱码 | 升级到 `v2.0.4` 或更高。安装器已改为 UTF-8 编译；旧版乱码不影响安装后的功能 |
| Windows DDC 切换报错 | 错误日志会直接列出 OSD 开启步骤。仍失败时在 cmd 里运行 `"C:\Program Files\QuickSwitch\QuickSwitch.exe" --ddc-selftest`；它会读当前输入源并写回同一个值，不改变画面。把输出的「原生错误」、处理建议和日志一起保留 |
| 网页打不开 | 端口 8767 被占，或被 `--no-web` 关了；去日志里看实际地址与令牌 |
| 首次启动设置窗口晚出现约 30 秒 | macOS 首次本地网络权限 / 解析，点「允许」后即可；之后启动 1~2 秒就绪 |
| 点切换没反应 / 找不到 DDC/CI | 按显示器机身按钮或摇杆打开 OSD 菜单，在「系统 / 设置 / 其他设置 / OSD 设置 / 管理」里找「DDC/CI」（也可能叫 DDC/CI Support、Monitor Control、MCCS），设为「开 / On」；保存后等 5 秒。详细路径见 [1.1 开启显示器 DDC/CI](#11-开启显示器-ddcci)。Windows 再看 `--status` 的 DDC 后端是否为 DXVA2，macOS 检查 `ddc.m1ddc_path` |
| Windows 提示找不到 `ControlMyMonitor.exe` | 旧版安装包会尝试该外部回退。最新版 Windows 使用内置 DXVA2，不需要该文件；ControlMyMonitor 仅是可选的补充回退 |
| QuickSwitch 启动后键鼠共享没起来 | 点主界面键鼠共享状态，或运行 `--deskflow-status` 检查 `installed`/`bundled`/`running`/`connected`/`last_error`；确认 `deskflow.auto_start` 开启。Windows 核心位于 `QuickSwitch\deskflow`，macOS 位于 `QuickSwitch.app/Contents/Resources/deskflow`，通常不需要另装 |
| 显示器切了但键鼠没过去 | 在设置页点「重启键鼠共享」；确认两端 QuickSwitch 已连接、Windows 自动为服务端、Mac 自动为客户端、`deskflow.mac_side` 与实际屏幕方向一致。Windows 安装器会自动放行 TCP `24800`；macOS 授予辅助功能、输入监控和本地网络权限后重启核心 |
| 对端未连接 | IP / 端口、防火墙、对端没运行。`--status` 会写明「连接失败」 |
| 密钥校验未通过 | 两端配对码不一致，改成同一个 6 位配对码后重启 |
| 想停掉程序 | 托盘菜单「退出」。托盘运行时 `SIGTERM` 不生效，脚本里停进程用 `kill -9` |
| 启动退出码 3 | 监听端口被占用，通常已经有实例在跑 |

---

## 8. 一分钟验收

1. 两端 `--status`：对端「已连接」、密钥校验「已通过」、DDC 后端「可用」。
2. 按一次 `Ctrl+Alt+1`：显示器切到 Mac，Mac 上键鼠可用，托盘显示当前为 Mac。
3. 按一次 `Ctrl+Alt+2`：切回 Windows。
4. 关掉 Mac 上的 QuickSwitch，再按 `Ctrl+Alt+1`：Windows 本机仍切换成功，日志提示「对端未确认」——这是预期的冗余设计。
