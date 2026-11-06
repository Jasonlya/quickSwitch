# QuickSwitch 安装与使用指南

> 面向使用者。下载与首次使用速览见根目录 [README.md](README.md)；完整配置、通信协议、验收与打包发布见 [docs/TECHNICAL.md](docs/TECHNICAL.md)。

一台 Windows（键鼠接在它上面）＋ 一台 Mac，共用一个显示器。按一次快捷键，显示器输入源和键鼠控制权一起切过去；
即使对端没响应，本机这一半也照样生效。

---

## 0. 三十秒速览

| 步骤 | Windows（server） | macOS（client） |
| --- | --- | --- |
| 1 | 装 Deskflow，设成 **Server** | 装 Deskflow，设成 **Client** |
| 2 | 装 ControlMyMonitor | 装 m1ddc（Apple Silicon）或 ddcutil |
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
| 键鼠 | 物理接在 Windows 上 | macOS 端通过 Deskflow 借用 |
| 权限 | Windows 侧注册全局热键需管理员 | 托盘图标与网页控制不需要 |

软件清单：

| 软件 | 作用 | 是否必须 |
| --- | --- | --- |
| QuickSwitch | 切显示器输入源 + 通知对端 | **必须**，本文档安装的就是它 |
| Deskflow | 一套键鼠控制两台机器、剪贴板文本共享 | 必须（除非你只想切显示器） |
| ControlMyMonitor | Windows 侧 DDC/CI 工具 | 必须（Windows 端） |
| m1ddc / ddcutil | macOS 侧 DDC/CI 工具 | 必须（macOS 端二选一） |
| LocalSend / Tailscale | 传文件 / 固定虚拟 IP | 可选 |

---

## 2. 安装

推荐直接从 [GitHub Releases](https://github.com/Jasonlya/quickswitch/releases/latest) 下载安装包。
安装包自带 Python 运行时、托盘依赖和网页设置页，目标机不需要安装 Python 或 pip。

### 2.1 macOS（推荐安装包）

下载时按芯片选择：

- Apple 芯片（M1/M2/M3/M4）：`QuickSwitch-1.2.3-macOS-arm64.dmg`
- Intel 芯片：`QuickSwitch-1.2.3-macOS-x64.dmg`
- 不确定时，在终端运行 `uname -m`：`arm64` 选 arm64，`x86_64` 选 x64。

安装步骤：

1. 打开 DMG，把 `QuickSwitch.app` 拖到 `Applications`（应用程序）文件夹。
2. 首次打开若提示「无法验证开发者」：在 App 上右键 →「打开」→ 再点「打开」。
   当前 Release 未签名 / 未公证；如果系统仍拦截，可到「系统设置 → 隐私与安全性」点「仍要打开」。
3. 首次启动可能弹「允许 QuickSwitch 查找并连接到本地网络上的设备」→ 点**允许**；
   拒绝的话对端通知发不出去（本机切换仍可用）。
4. 菜单栏出现 QuickSwitch 图标 = 启动成功，首次运行会自动打开设置页面。程序不进 Dock，属于正常的菜单栏程序。

命令行自检：

```bash
/Applications/QuickSwitch.app/Contents/MacOS/QuickSwitch --status
```

### 2.2 Windows（推荐安装包）

1. 下载并双击 `QuickSwitch-Setup-1.2.3.exe`，在 UAC 提示中点「是」。
2. 未签名版本首次运行可能弹 SmartScreen：点「更多信息」→「仍要运行」。
3. 安装程序会创建桌面和开始菜单快捷方式，自动放行 TCP 8765，并写入卸载入口。
4. 从桌面或开始菜单启动 QuickSwitch；首次运行会自动打开设置页面。
5. Windows 全局热键需要管理员权限，快捷方式已设置为以管理员身份运行；每次启动出现 UAC 时点「是」即可。

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

安装包首次启动时会自动打开设置页面，并在下面位置生成配置：

- macOS：`~/.quickswitch/config.json`
- Windows：`%USERPROFILE%\.quickswitch\config.json`

如果没有自动打开：右键菜单栏 / 托盘图标 →「打开设置页面」。

也可以手动生成或查看配置文件：

```bash
# macOS（成品包）
/Applications/QuickSwitch.app/Contents/MacOS/QuickSwitch --init-config

# Windows（成品包）
"%ProgramFiles%\QuickSwitch\QuickSwitch.exe" --init-config

# 源码
python main.py --init-config
```

也可以直接在网页控制台点「更多信息与设置」→「配置」区块里改（只允许改白名单字段），省得手动编辑 JSON。

### 3.2 先填这三项

| 字段 | 例子 | 说明 |
| --- | --- | --- |
| `peer_host` | 对端局域网 IP，如 `192.168.1.101` | 也可设 `"auto"` 开局域网自动发现 |
| `role` | Windows 填 `server`，macOS 填 `client` | 首次常驻启动会按系统自动选好；只有 `server` 注册全局热键 |
| `auth.secret` | 两端填同一个 16 位以上的随机字符串 | 在「更多信息与设置 → 配置 → 安全」区块填写；两端必须一致，保存后重启 |
| `listen_port` / `peer_port` | 两端都用 `8765` | 两边必须一致，且防火墙要放行 |

设置页「连接」区块会显示本机局域网 IP；把它填到**另一台电脑**的「对端地址」里。
DDC 路径和输入源取值如果默认值不匹配，再按 3.3 调整。

Windows 端还要确认 DDC 工具路径：

| 字段 | 说明 |
| --- | --- |
| `ddc.controlmyMonitor_path` | 默认 `C:\Tools\ControlMyMonitor.exe`，按实际位置改 |
| `ddc.monitor_id` | 默认 `\\.\DISPLAY1\Monitor0`，多屏时按实际监视器改 |

macOS 端确认 `ddc.m1ddc_path`（默认 `/opt/homebrew/bin/m1ddc`），或改用 `ddcutil`。

### 3.3 识别显示器输入源

不同品牌取值不一样，别猜，让工具测：

```bash
python3 main.py --detect-inputs                                # 交互式：探测候选值 → 标注哪台机器 → 回读校验 → 写回配置
python3 main.py --detect-inputs --mac-input 15 --win-input 17  # 已知取值时直接写
python3 main.py --detect-inputs --no-write                     # 只看结果，不改配置
```

成品包同样可以带参数运行（路径见 3.1）。网页控制台里也有「探测输入源」按钮，效果相同。

### 3.4 配预共享密钥（必须）

`auth.secret` 为空时，同网段任何程序只要往 8765 发一行 JSON 就能切走你的显示器。推荐直接在设置页的「安全」区块填写，也可以生成后复制到两端：

```bash
python3 main.py --gen-secret
# {"auth": {"secret": "ReKQONRgzal_BnZAnRya3bx_FpCbLXQaLe1dDGSB5zk"}}
```

把同一个值填进**两端**的「安全 → auth.secret」，保存后重启两端。

### 3.5 自检：什么才算配好了

两端各跑一次 `--status`，重点是这三行：

```
对端         : 192.168.1.101:8765 已连接（对端 DESKTOP-ABC，role=server，版本=1.2.3）
密钥校验     : 已通过（hmac-sha256）
DDC 工具     : 已找到 /opt/homebrew/bin/m1ddc
```

| 输出 | 含义 |
| --- | --- |
| 对端「连接失败」 | 对端没运行、IP / 端口错、或防火墙挡了 |
| 密钥校验「未配置」 | 本端没填 `auth.secret`，切换请求不会校验 |
| 密钥校验「未通过」 | 两端 `auth.secret` 不一致 |
| DDC「未找到」 | 工具路径不对或没装 |
| 当前输入源「无法读取」 | 显示器不支持读 VCP 0x60，或工具不支持读；不影响切换 |

---

## 4. 日常使用

### 4.1 三种触发方式

| 方式 | 怎么用 | 前提 |
| --- | --- | --- |
| 托盘 / 菜单栏 | 右键图标 →「打开设置页面」/「切到 Mac」/「切到 Windows」/「查看状态（写入日志）」/「退出」 | 无 |
| 全局热键 | `Ctrl+Alt+1` → Mac，`Ctrl+Alt+2` → Windows | 只在 Windows `server` 端注册，需管理员权限 |
| 网页控制台 | 浏览器打开带令牌的地址，点按钮 | 程序正在运行 |

### 4.2 网页控制台

只监听 `127.0.0.1`，每次启动生成新令牌：

- 首次启动会自动在浏览器打开设置页面；
- 启动日志里会打印 `Web 控制台：http://127.0.0.1:8767/?t=...`；
- 成品包没有控制台窗口，去 `~/.quickswitch/quickswitch.log` 里找最后一条
  `Web 控制台已启动：...`，把整条地址粘进浏览器。

主页面只保留「切到 Mac / Windows」两个按钮；鼠标停在按钮上会显示当前输入源、对端连接、
密钥校验、DDC 和快捷键摘要。点「更多信息与设置」后，才能读取/探测输入源、查看连接与
DDC 命令原文、修改白名单配置和查看事件日志。地址里的 `?t=` 不要发给别人。

### 4.3 和 Deskflow 配合

QuickSwitch 只管显示器，键鼠控制权归 Deskflow。两边热键要**配成同一组**，这样一次按键两件事同时发生：

| 目标 | QuickSwitch 热键 | Deskflow 热键 |
| --- | --- | --- |
| 切到 Mac | `ctrl+alt+1` | 「切换到 Mac 屏幕」 |
| 切到 Windows | `ctrl+alt+2` | 「切换到 Windows 屏幕」 |

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
```

---

## 7. 常见问题

| 现象 | 原因 / 处理 |
| --- | --- |
| macOS 双击提示「无法验证开发者」 | 未签名 / 未公证。右键 → 打开；或系统设置 → 隐私与安全性 → 仍要打开 |
| macOS 提示 app「已损坏」 | 隔离属性。本地自测执行 `xattr -dr com.apple.quarantine /Applications/QuickSwitch.app` |
| Windows 首次运行弹 SmartScreen | 未签名。更多信息 → 仍要运行；正式分发需代码签名 |
| 网页打不开 | 端口 8767 被占，或被 `--no-web` 关了；去日志里看实际地址与令牌 |
| 首次启动网页晚出现约 30 秒 | macOS 首次本地网络权限 / 解析，点「允许」后即可；之后启动 1~2 秒就绪 |
| 点切换没反应 | DDC 工具路径错、显示器没开 DDC/CI、取值不对。先跑 `--status` 看 DDC 那一行 |
| 显示器切了但键鼠没过去 | Deskflow 的问题：检查两端 Deskflow 连接与热键 |
| 对端未连接 | IP / 端口、防火墙、对端没运行。`--status` 会写明「连接失败」 |
| 密钥校验未通过 | 两端 `auth.secret` 不一致，改成同一个值后重启 |
| 想停掉程序 | 托盘菜单「退出」。托盘运行时 `SIGTERM` 不生效，脚本里停进程用 `kill -9` |
| 启动退出码 3 | 监听端口被占用，通常已经有实例在跑 |

---

## 8. 一分钟验收

1. 两端 `--status`：对端「已连接」、密钥校验「已通过」、DDC 工具「可用」。
2. 按一次 `Ctrl+Alt+1`：显示器切到 Mac，Mac 上键鼠可用，托盘显示当前为 Mac。
3. 按一次 `Ctrl+Alt+2`：切回 Windows。
4. 关掉 Mac 上的 QuickSwitch，再按 `Ctrl+Alt+1`：Windows 本机仍切换成功，日志提示「对端未确认」——这是预期的冗余设计。
