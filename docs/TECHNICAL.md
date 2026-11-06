# QuickSwitch 技术文档

按一个快捷键，同时切换**显示器输入源**和**键鼠控制权**。

适用场景（与方案一致）：Windows 主机通过网线接入局域网、键鼠物理连接在 Windows 上；
macOS 主机通过 WiFi 接入同一局域网；两台主机共用一台显示器。

本目录是方案 v1.0 中「QuickSwitch（自研 Python 客户端）」的完整实现，
另外附带了方案里留给「未来扩展」的局域网自动发现。

> **第一次安装？** 先看根目录的 [README.md](../README.md) 与 [INSTALL.md](../INSTALL.md) —— 下载安装包、首次配置与常见问题。
> 成品包怎么装、首次配置改哪几项、权限怎么给、日常怎么切、开机自启、升级卸载、常见问题。
> 本文件是完整技术参考（配置、协议、验收、打包与发布）。

## 1. 组成与数据流

| 组件 | 作用 | 运行位置 | 是否包含本仓库 |
| --- | --- | --- | --- |
| Deskflow 无界面核心 | 一套键鼠控制两台电脑（软件 KVM、剪贴板文本共享） | 两端 | 是：随安装包内置官方 GPL-2.0 版本，由 QuickSwitch 管理，不启动 GUI |
| Windows DXVA2 / m1ddc / ddcutil | DDC/CI 切换显示器输入源 | Windows 使用系统内置；macOS 需 m1ddc；Linux 可选 ddcutil | Windows 无需安装；macOS 需自行安装 |
| **QuickSwitch** | 热键/托盘触发，切本地 DDC 并经 TCP 通知对端冗余切换 | 两端 | **是（本目录）** |
| LocalSend | 局域网文件互传 | 两端 | 否 |
| Tailscale（可选） | 固定虚拟 IP，抵御 IP 变化 | 两端 | 否 |

```
物理键盘（插在 Windows）
  |-- 内置核心捕获        --> 切换键鼠控制权（deskflow-core，无窗口）
  |-- QuickSwitch 捕获   --> 切换显示器信号源（Windows 用内置 DXVA2 / VCP 0x60）
          |-- TCP 通知 Mac --> Mac 端 m1ddc 再切一次（方案 10.1 的冗余保险）
```

Windows 端是 `server`（注册热键），macOS 端是 `client`（只接收 TCP 指令并调用 DDC，不注册热键）。

## 2. 相对方案文档的实现说明

方案里的示例代码能表达意图，但有几处直接照抄会跑不通或不够可靠，实现时做了如下处理：

| # | 方案原文 | 本实现 | 原因 |
| --- | --- | --- | --- |
| 1 | `ControlMyMonitor.exe <monitor> 96 <value>` | Windows 默认直接调用系统 `dxva2.dll` 读写 VCP 0x60；ControlMyMonitor 仅作为可选回退 | 目标机不再需要额外下载 DDC 工具。原生后端失败时才尝试用户配置的外部工具 |
| 2 | 连接循环只发心跳、不读数据、无断线检测 | 独立读循环 + 心跳 + 3 个周期无任何消息即判定半开并重连，指数退避到 30s | 方案原版对端进程被杀后 writer 仍非空，通知会静默丢失 |
| 3 | 通知对端后不校验结果 | 增加 `switch_ack` 确认（默认 4s 超时）并写日志 | 「冗余保险」是否真的生效可被验证，而不是只能靠猜 |
| 4 | 收到对端请求后再通知对端 | 对端发起的切换不再回传（`notify=False`） | 避免两端互相转发形成回环 |
| 5 | 无重复触发保护 | 同一目标 0.6s 内只执行一次（`debounce` 可配） | 热键连发会触发两次切换与两次 DDC |
| 6 | — | 端口被占用时启动即报错退出（退出码 3） | 顺带作为单实例检测，避免两个进程抢键盘热键 |
| 7 | — | `--status` / `--once` / `--dry-run` / `--print-config` / `--init-config` / `--no-tray` | 方案的 §9 验收清单需要可执行的验证手段 |
| 8 | 「未来扩展：mDNS 自动发现」 | 已实现可选的 UDP 广播发现（`peer_host: "auto"`），零第三方依赖 | 直接解决方案 1.2 的「IP 可能变化」痛点，不必强制上 Tailscale |
| 9 | — | 能读出当前输入源（Windows 原生 DXVA2、macOS `m1ddc get input`、Linux `getvcp 60`），`--status` 直接显示 | 便于确认切换是否真的生效。注意：`m1ddc` 官方 README 的 get 列表没写 input，但源码 `attrCodeFromCommand` 支持，非 set 指令都会先读当前值，因此可用 |
| 9b | — | `--detect-inputs` 输入源识别向导：探测候选取值 → 交互标注哪台机器 → 回读校验 → 写回配置 | 方案要求「不同品牌取值不同，需用工具读取」，向导把这一步自动化，不必手工搬数字 |
| 9c | — | `ddc.read_template` / `ddc.read_regex` | 读取能力交给任意工具（如 BetterDisplay CLI）；显示器不支持读 VCP 0x60 时也能自行指定 |
| 9d | — | Windows 原生 DDC 后端（`windows_ddc.py`，DXVA2） | 安装包不再依赖 `ControlMyMonitor.exe`；只要显示器支持并开启 DDC/CI 即可读写 VCP 0x60 |
| 10 | Linux 只在选型表里提到 ddcutil | 已内置 ddcutil 模板 | 顺手支持，成本一次模板 |
| 11 | 日志只写文件 | 轮转日志（1MB × 3）+ 控制台 | 长期常驻不会把日志写爆 |
| 12 | — | 本地 Web 控制台（`webui.py` + `ui/`，默认 http://127.0.0.1:8767/）+ 原生 WebView 设置窗口（`settings_window.py`） | 托盘菜单只能切两下；配置、当前输入源、DDC 命令与事件日志需要一个能一眼看全、能改配置的界面，同时避免每次设置都打开浏览器标签页，也不引入 Electron 之类的重依赖 |
| 13 | — | 启动时后台回读一次输入源，切换/读取后自动回读 | 界面首屏就能显示「显示器现在归谁」，不必先点一次按钮 |
| 14 | — | Web 控制台只允许改白名单字段，且只监听回环地址 + 随机令牌 + Host/Origin 校验 | 一个能切换显示器、能写配置的本地端口，等价于本机代码执行入口，不能裸奔 |
| 15 | 网络只靠 TCP 通知，没有鉴权 | 可选预共享密钥 + 每连接随机 nonce 的 HMAC 质询-响应；未通过校验前丢弃 `switch` / `switch_ack` | 方案默认「同网段即可信」：局域网里任何机器只要往 8765 发一行 JSON 就能切走显示器。密钥不上网、旧连接的校验码不能重放 |
| 16 | — | `packaging/`：PyInstaller 打包 + Windows Authenticode 签名 / macOS 签名 + 公证 + 装订 | 方案把它当「Python 客户端」部署，但目标机装 Python、装依赖、配权限对普通用户太贵。详见 §7 |

## 3. 目录结构

```
quickswitch/
  main.py            入口：切换逻辑 + 托盘 + 热键 + 命令行
  config.py          配置加载、深度合并、校验、默认值生成
  ddc.py             DDC/CI 封装（Windows 原生 DXVA2 + macOS/Linux 命令模板 + 重试 + 读取）
  windows_ddc.py     Windows 原生 DDC 后端（user32/dxva2，枚举物理显示器并读写 VCP 0x60）
  deskflow_bridge.py 内置 deskflow-core 检测、配置生成、进程启停与权限提示
  network.py         asyncio JSON Lines 通信（心跳、重连、双向互连、ACK、预共享密钥校验）
  discovery.py       可选：局域网 UDP 设备发现（peer_host = "auto"）
  webui.py           本地 Web 控制台：回环 HTTP 服务 + 令牌鉴权 + JSON API + 事件缓冲
  ui/                控制台前端（原生 HTML/CSS/JS，无构建步骤、无 CDN）
  settings_window.py 用系统 WebView 打开设置页；窗口进程与托盘主进程分离
  requirements.txt   运行时依赖
  requirements-build.txt  打包期依赖（PyInstaller / Pillow，只在构建机安装）
  packaging/
    quickswitch.spec        PyInstaller 配置（Windows 单文件 exe / macOS .app）
    fetch-deskflow.py      下载/校验官方 Deskflow，并准备到 packaging/vendor
    bundle-deskflow.py     把官方 Deskflow.app 原样嵌入打包后的 QuickSwitch.app
    build-macos.sh          macOS：打包 → 签名 → 公证 → 装订 → Gatekeeper 校验
    build-windows.ps1       Windows：打包 → Authenticode 签名 → 签名校验
    build-dmg.sh            macOS：把 .app 打成可拖拽安装的 DMG
    installer.nsi           Windows：NSIS 安装包（快捷方式、防火墙规则、卸载项）
    print-version.py        从 main.py 读取版本号，供 DMG/CI 共用
    entitlements.plist      hardened runtime 权限（最小集）
    version_info.txt        Windows exe 的版本资源（2.0.4.0）
    make-icons.py           用 Pillow 生成 icon.png / icon.ico / icon.icns
    icon.png / icon.ico / icon.icns   已生成好的图标
  THIRD_PARTY_NOTICES.md Deskflow 版本、GPL-2.0、源码与校验信息
  scripts/
    quickstart-windows.bat         Windows 端启动（保留控制台日志，便于排错）
    install-task.ps1               注册 Windows 任务计划（登录自启 + 最高权限）
    com.quickswitch.agent.plist    macOS launchd 自启模板
    selftest.py                    本机链路自检（无需第二台机器/显示器）
  tests/              170 个单元/集成测试（unittest，无第三方依赖）
```

## 4. 快速开始

> Python 3.9+（方案写 3.10+，但本实现未使用 3.10 专属语法，已在 3.9.6 上跑通全部测试）。

### 4.1 Windows（server，物理键鼠所在机）

```bat
:: 1) 依赖
pip install -r requirements.txt

:: 2) 首次运行，生成默认配置 %USERPROFILE%\.quickswitch\config.json
python main.py --init-config

:: 3) 按 §8.1 确认 DDC 能切显示器，然后填入 mac_input / win_input
:: 4) 以管理员身份运行（keyboard 注册全局热键需要管理员权限）
python main.py
```

Deskflow 已随安装包内置（选 Server）；按需安装 LocalSend / Tailscale，见 §4.3 / §4.4。
Windows 端不需要安装 ControlMyMonitor，程序默认使用系统内置 DXVA2。

若 Windows 防火墙挡住了 `listen_port`（默认 8765）或自动发现端口（UDP 8766），用管理员 PowerShell 放行一次即可：

```powershell
netsh advfirewall firewall add rule name="QuickSwitch" dir=in action=allow protocol=TCP localport=8765
netsh advfirewall firewall add rule name="QuickSwitch Discovery" dir=in action=allow protocol=UDP localport=8766
netsh advfirewall firewall add rule name="QuickSwitch Deskflow" dir=in action=allow protocol=TCP localport=24800
```

### 4.2 macOS（client）

```bash
brew install m1ddc                               # DDC/CI 切换（仅 Apple Silicon）

cd quickswitch
python3 -m pip install pystray Pillow pywebview
python3 main.py --init-config                    # 生成配置；macOS 会自动写入 role=client
python3 main.py --status                         # 自检：工具 + 对端连通性
python3 main.py
```

键鼠共享核心无需通过 Homebrew 安装：DMG 内置官方 `Deskflow.app`，QuickSwitch 只执行其中的 `deskflow-core`。从源码运行时先执行
`python3 packaging/fetch-deskflow.py --target macos-arm64`，桥接模块会使用 `packaging/vendor`。

授权：系统设置 → 隐私与安全性 → **辅助功能**、**输入监控**、**本地网络**勾选 QuickSwitch；若列表里出现 `Deskflow` 或 `deskflow-core`，也一并勾选。

### 4.3 内置键鼠共享（Deskflow 核心 + 剪贴板）

QuickSwitch 直接调用官方 `deskflow-core`，不启动 Deskflow GUI。`deskflow_bridge.py` 负责：

1. 按角色自动生成配置：Windows `server`，macOS `client`。
2. 写入 QuickSwitch 对端地址、TCP 端口、屏幕左右关系、剪贴板开关和两个切换热键。
3. 用 `deskflow-core <server|client> --settings <Deskflow.conf> --new-instance` 后台启动。
4. 记录 `deskflow.pid`，退出 QuickSwitch 时停止该进程；设置页可手动重启。

默认把 TLS 关闭，避免首次连接还要在两端确认证书指纹，保证完全无界面。连接只应在可信局域网内使用；QuickSwitch 自己的 TCP 通知仍由 `auth.secret` 校验。

默认状态目录：`~/.quickswitch/deskflow`。

- `Deskflow.conf`：QuickSwitch 每次启动生成的主配置。
- `Deskflow-server.conf`：仅 Windows 服务端使用的屏幕布局和热键。
- `deskflow.log`：无界面核心日志。
- `deskflow.pid`：QuickSwitch 管理进程的 PID。

`deskflow.auto_start=true`（默认）时随 QuickSwitch 启动；`peer_host` 为 `auto` 的 macOS 客户端会等待 UDP 发现 Windows 后再启动或重启核心。退出 QuickSwitch 会同步停止核心。

状态页不再只检查进程是否存活。`deskflow_bridge.snapshot()` 会结合 Deskflow 本次启动后的日志和真实 TCP 连接，返回 `connected`、`connection_state`、`active_connections`、`summary` 和 `last_error`：Windows 服务端通过隐藏执行的 `netstat` 检查 `24800` 的 `ESTABLISHED` 连接，macOS 客户端通过 `lsof` 检查核心进程与对端的连接；同时解析 `connected to server`、`client "... " has connected`、超时、拒绝连接和 macOS 权限错误。主界面只显示可读结论，点击「键鼠共享」状态可展开技术细节。

Windows 上所有状态轮询和 DDC 外部命令都通过 `process_utils.silent_subprocess_kwargs()` 加上 `CREATE_NO_WINDOW`，系统托盘程序不会再为 `tasklist`、`taskkill`、`netstat` 或 DDC 回退工具闪出终端窗口；已经由当前进程管理的核心直接使用缓存的 `Popen` 判断，进一步减少子进程调用。

内置位置：

- macOS：`QuickSwitch.app/Contents/Resources/deskflow/Deskflow.app`
- Windows：`%ProgramFiles%\QuickSwitch\deskflow\deskflow-core.exe`

构建机由 `packaging/fetch-deskflow.py` 下载并校验官方 Deskflow `1.27.0`，macOS 由 `bundle-deskflow.py` 在 PyInstaller 完成后原样嵌入，Windows 由 NSIS 安装到 QuickSwitch 目录。用户不需要安装或打开 Deskflow 客户端，也不需要手工填写 Server/Client、屏幕布局或热键。

Windows 安装包会自动放行 TCP `24800`。macOS 首次仍需在「隐私与安全性」中授予辅助功能、输入监控和本地网络权限；修改后点设置页「重启键鼠共享」。若日志出现 `assistive devices does not trust this process`、`process is not trusted anymore` 或 `failed to create quartz event tap`，设置页会标记需要权限，并在本次运行首次发现时自动打开一次辅助功能设置，同时提供「打开辅助功能设置」「打开输入监控设置」两个入口。两端内置版本统一为 `1.27.0`。

QuickSwitch 注册热键时使用 `suppress=False`，所以内置核心能收到同一个热键；`deskflow_bridge.py` 会把 `config.json` 的热键转换成 Deskflow 的 `keystroke(...) = switchToScreen(...)` 配置，无需在客户端里重复设置。

### 4.4 网络（三选一）

| 方案 | 配置 | 说明 |
| --- | --- | --- |
| 静态 IP / 路由器 DHCP 绑定 | `"peer_host": "192.168.1.10"` | 最简单，IP 变了要改配置 |
| Tailscale（推荐） | `"peer_host": "100.x.x.x"` 或 MagicDNS 名 | IP 变化无感 |
| 局域网自动发现 | `"peer_host": "auto"` | 两端在同一网段即可；见 §5 的 `discovery.*` |

## 5. 配置说明

配置文件：`~/.quickswitch/config.json`（可用 `QUICKSWITCH_CONFIG` 环境变量或 `--config` 覆盖）。
文件里只写要改的字段即可，其余自动用默认值补齐。

```json
{
  "role": "server",
  "peer_host": "100.101.102.103",
  "peer_port": 8765,
  "listen_port": 8765,
  "tray": true,
  "log_level": "INFO",
  "setup": { "completed": false },
  "debounce": 0.6,
  "ddc": {
    "controlmyMonitor_path": "C:\\Tools\\ControlMyMonitor.exe",
    "monitor_id": "\\\\.\\DISPLAY1\\Monitor0",
    "m1ddc_path": "/opt/homebrew/bin/m1ddc",
    "display_index": 1,
    "vcp_code": "0x60",
    "mac_input": 15,
    "win_input": 17,
    "command_template": null,
    "read_template": null,
    "read_regex": null,
    "settle": 1.2,
    "timeout": 10.0,
    "retries": 2,
    "retry_delay": 0.4
  },
  "hotkeys": { "switch_to_mac": "ctrl+alt+1", "switch_to_win": "ctrl+alt+2" },
  "deskflow": {
    "auto_start": true,
    "path": "",
    "port": 24800,
    "mac_side": "left"
  },
  "network": {
    "ping_interval": 10.0,
    "ack_timeout": 4.0,
    "reconnect_interval": 3.0,
    "reconnect_max_interval": 30.0,
    "connect_wait": 4.0
  },
  "discovery": {
    "enabled": false,
    "port": 8766,
    "interval": 5.0,
    "ttl": 15.0,
    "broadcast": "255.255.255.255"
  },
  "web": {
    "enabled": true,
    "host": "127.0.0.1",
    "port": 8767
  },
  "auth": {
    "secret": "用 python main.py --gen-secret 生成，两端填同一个值"
  }
}
```

| 字段 | 说明 |
| --- | --- |
| `role` | `server`（Windows，注册热键）或 `client`（macOS，只响应 TCP） |
| `peer_host` | 对端地址；`"auto"` = 启用局域网自动发现 |
| `peer_port` / `listen_port` | 对端端口 / 本机监听端口（两端都用 8765 即可） |
| `tray` | 是否显示托盘图标（也可用 `--no-tray` 临时关闭） |
| `setup.completed` | 首次配置向导是否完成；旧配置没有该字段时自动视为已完成，避免升级后重复弹向导 |
| `debounce` | 同一目标的重复触发间隔（秒） |
| `ddc.display_index` | 物理显示器序号（从 1 开始）；Windows 原生 DXVA2 与 macOS m1ddc 共用该字段 |
| `ddc.vcp_code` | 输入源 VCP 代码，默认 `0x60`（十进制 96） |
| `ddc.mac_input` / `ddc.win_input` | 显示器接 Mac / Windows 的输入源值，**必须以实际读取为准** |
| `ddc.command_template` | 自定义命令模板，字符串或数组；占位符 `{tool}` `{monitor}` `{vcp}` `{display_index}` `{value}`。设置后 Windows 不再使用原生 DXVA2 |
| `ddc.read_template` | 自定义「读取当前输入源」命令模板（同一套占位符）；用于 BetterDisplay CLI 等其它工具，设置后 Windows 不再使用原生 DXVA2 |
| `ddc.read_regex` | 从读取命令输出里抓数值的正则（含捕获组取第 1 组）；不填则按平台约定解析 |
| `ddc.settle` | 切换后等待显示器稳定的秒数（默认 1.2），`--detect-inputs` 探测与校验时使用 |
| `ddc.retries` | DDC 失败重试次数（显示器偶发无响应很常见，默认重试 2 次） |
| `hotkeys.*` | 切换热键；会自动同步到内置键鼠共享配置 |
| `deskflow.auto_start` | QuickSwitch 启动时是否自动拉起无界面核心，默认 `true`；退出 QuickSwitch 会同步停止它 |
| `deskflow.port` | 键鼠共享 TCP 端口，默认 `24800`；两端必须一致 |
| `deskflow.mac_side` | Mac 相对 Windows 的屏幕方向：`left` 或 `right`，默认 `left` |
| `deskflow.path` | 高级选项：强制指定 Deskflow.app / deskflow-core 路径；留空自动使用安装包内置核心 |
| `network.ack_timeout` | 等待对端切换确认的超时 |
| `discovery.broadcast` | 广播地址，可写数组；留空则只用「按本机网段推导的 x.y.z.255」 |
| `web.enabled` | 是否启动本地 Web 控制台（默认开；也可用 `--no-web` 临时关闭） |
| `web.host` / `web.port` | 控制台监听地址与端口，默认 `127.0.0.1:8767`；改成非回环地址会有告警 |
| `auth.secret` | 预共享配对码（两端一致，默认生成 6 位）；留空 = 不校验，旧长密钥仍兼容，见 §6.3 |

输入源常见值：DP1=15、DP2=16、HDMI1=17、HDMI2=18、USB-C=27（VCP 0x60）。

## 6. 运行方式

```bash
python main.py                 # 常驻运行：托盘 + 全局热键
python main.py --status        # 自检：配置 / DDC 后端 / 当前输入源 / 对端连通性
python main.py --once mac      # 执行一次完整切换后退出（验证 DDC + 通知链路）
python main.py --detect-inputs # 识别显示器输入源取值并写回配置（交互式向导）
python main.py --dry-run       # 只打印将执行的 DDC 操作，不动硬件
python main.py --print-config  # 打印合并默认值后的生效配置
python main.py --deskflow-status  # 打印内置核心路径、配置与运行状态（JSON）
python main.py --start-deskflow   # 后台启动内置核心后退出（不打开窗口）
python main.py --restart-deskflow # 按当前配置重启内置核心后退出
python main.py --stop-deskflow    # 停止由 QuickSwitch 启动的核心
python main.py --no-tray       # 无托盘后台运行
python main.py --web-port 9000 # Web 控制台换端口（默认 8767）
python main.py --no-web        # 关闭 Web 控制台，只留托盘/热键
python main.py --log-level DEBUG
```

| 退出码 | 含义 |
| --- | --- |
| 0 | 正常 |
| 1 | `--once` 切换失败；或 `--detect-inputs` 取值缺失/回读不一致 |
| 2 | 配置错误 |
| 3 | 监听端口被占用（通常已有实例在运行） |
| 4 | 其他启动失败 |

### 6.1 设置窗口与 Web 控制台（默认开启）

常驻运行时会额外起一个**只监听 `127.0.0.1`** 的本地网页，启动日志里会打印带令牌的地址：

```
2026-10-16 14:12:37 [webui] INFO: Web 控制台已启动：http://127.0.0.1:8767/?t=OaftWnJt...
```

托盘菜单「打开设置窗口」会优先启动应用内 WebView，不打开浏览器标签页。
macOS 使用系统 WKWebView，Windows 使用 WebView2；窗口由独立子进程承载，
避免和 pystray 争抢 macOS 主线程。WebView 不可用或启动失败时才回退到默认浏览器。
`--no-tray` 时启动地址也会打到 stderr，可直接在浏览器打开。页面上能做的事：

| 区块 | 内容 |
| --- | --- |
| 主界面 | 只显示「切到 Mac」「切到 Windows」两个材质按钮；按钮右侧直接显示键帽式热键标记，悬停可查看注册状态，按钮提示包含当前输入源、对端连接、密钥校验、DDC 与快捷键摘要；当前持有方以蓝色图标、描边和状态点标记 |
| 更多信息与设置 | 默认折叠；展开后包含运行概况、显示器所有权、诊断工具、连接、显示器 DDC、热键、配置与事件日志 |
| 显示器所有权 | 两台机器分列一条发丝栅格的两端，蓝色块停在当前持有方；切换时蓝块沿栅格滑动，两端数字（`ddc.mac_input` / `ddc.win_input`）用等宽字形跟着换色 |
| 诊断工具 | 读取当前输入源 / 探测输入源（可自定义候选值，留空用内置候选集） |
| 连接 | 角色、监听端口、最近切换目标、对端地址与连接状态、对端身份、对端密钥校验结果、自动发现到的设备 |
| 显示器 DDC | 工具路径与可用性、按当前配置拼好的三条命令行（可直接复制到终端核对）、Mac/Windows 取值、当前输入源与上次读取时间 |
| 热键 | 组合键、是否注册成功、失败原因（例如未安装 `keyboard`、缺少管理员权限） |
| 配置 | 白名单字段可视化编辑；保存前用 `config.validate` 校验，校验不过不落盘；标记「需重启」的字段会明确告知要重启才生效 |
| 事件 | 运行中进程的日志尾部（内存环形缓冲，不额外落盘），倒序 |

值一律来自 `/api/status`、`/api/config`、`/api/events` 三个接口的**真实数据**：
读不到就显示「读取不到」，未知就显示「—」，页面不编造任何数值。

安全模型（三层，缺一不可）：

1. 只绑定 `127.0.0.1`，不对外网暴露（改 `web.host` 会有告警，因为那等于把切换能力交给局域网）；
2. 每次启动生成随机令牌，写在地址栏的 `?t=` 里，页面之后用 `X-QuickSwitch-Token` 头调用 API —— 自定义头会触发 CORS 预检，跨站的表单/图片式请求打不进来；
3. 校验 `Host` 与 `Origin` 是否为本机，阻断 DNS rebinding（恶意站点把自己的域名解析到 `127.0.0.1`）。

配置里的 `web.enabled` 可关掉整个控制台；临时关闭用 `--no-web`，改端口用 `--web-port`。
若端口被别的程序占用，只会在日志里报错，切换功能不受影响。

设计方向：以 **Swiss** 锚点为骨架，按 macOS 原生材质语言落地 —— 冷灰白画布、系统字体（SF Pro / system-ui）、单一 Apple 蓝 `#007AFF`、发丝分隔线、左对齐与 tabular 数字；同时使用系统设置式的圆角卡片、半透明窗口材质和轻量阴影。
不同点是桌面端呈现为一个居中的紧凑半透明窗口，主切换区采用「控制中心」式的两组材质按钮；当前持有方用图标底色、描边和状态点共同标记。
支持系统深色模式；没有暖纸底、衬线、颗粒纹理、装饰性图标与 `//` 式伪注释。

### 6.2 开机自启


- Windows：管理员 PowerShell 执行 `powershell -ExecutionPolicy Bypass -File scripts\install-task.ps1 -ProjectDir C:\Tools\quickswitch`
  （注册为「登录时启动 + 最高权限运行」；也可把 `quickstart-windows.bat` 的快捷方式放进 `shell:startup`）
- macOS：`cp scripts/com.quickswitch.agent.plist ~/Library/LaunchAgents/` 后 `launchctl load -w ...`
  （需先把 plist 里的 `/Users/CHANGE_ME/quickswitch` 换成实际路径；用「系统设置 → 通用 → 登录项」更简单）

### 6.3 局域网访问控制（6 位配对码）

**默认不设防**：`auth.secret` 为空时，同一网段里任何机器只要往 `listen_port` 发一行
`{"type":"switch","target":"mac"}`，显示器就会被切走。家用 LAN 通常可以接受，但只要
网络里有访客设备、物联网设备或公共 WiFi，就该打开这一层。

```bash
python3 main.py --gen-secret
# {"auth": {"secret": "K7QM9X"}}
```

把这一行合并进**两端**的 `~/.quickswitch/config.json`（或者控制台页面「配置」区块里改别的字段、
配对码直接改文件），重启两端后确认：

默认配对码是 6 位、去掉 `I/O/0/1` 的 32 符号随机串，约 30 bit 熵。它用于家用局域网便利配对；
在访客网络或公共 WiFi 中建议手动改成更长的随机值。配对码只用于 HMAC 挑战应答，不直接上网。

```
python3 main.py --status
  对端         : 192.168.1.101:8765 已连接（对端 DESKTOP-ABC，role=server，版本=2.0.3）
  密钥校验     : 已通过（hmac-sha256）
```

行为说明：

| 情形 | 结果 |
| --- | --- |
| 两端配对码一致 | 连接建立后自动完成质询-响应，日志出现「对端密钥校验通过」 |
| 两端配对码不一致 | 双方都校验不通过；对端发来的 `switch` / `switch_ack` 被丢弃（日志「丢弃未经校验的报文：校验码不匹配」），本端也不再发送会被丢弃的通知 |
| 一端配置、一端没配 | 没配的那端发出的切换请求会被丢弃；`--status` 会明确提示是哪一边没配 |
| 都没配 | 与旧版本行为一致，直连直切 |

设计取舍：

- 只拦报文、不拦连接：校验失败时连接与心跳照常，便于从日志和 `--status` 看出「两端配置不一致」，
  而不是表现为「连不上」这种更难排查的故障；
- 密钥不上网：网络上只传 HMAC 校验码；每条连接一个随机 nonce，且校验码同时绑定对方的 nonce，
  因此抓包拿到的旧校验码无法重放（换 nonce 就算不出新校验码）；比较用 `hmac.compare_digest` 常量时间；
- 不防「中间人转发」：转发者拿不到密钥，改不了报文、也造不出新报文，只是把两条连接接在一起，
  而在两端本就互相信任的前提下这没有额外收益；
- Web 控制台可以在「安全」区块修改 `auth.secret`，但配对码不会进入 `/api/status`、事件日志或启动日志；读取配置仍需要本机随机令牌。

## 7. 打包与分发（PyInstaller + 签名 / 公证）

内置脚本把「源码 + 依赖 + 前端」打成一个双击即用的成品，再按平台要求签名：

| 平台 | 产物 | 签名方式 | 脚本 |
| --- | --- | --- | --- |
| Windows | `dist/QuickSwitch.exe` + NSIS 安装包（自带 Python 运行时、`ui/` 和 `deskflow\` 便携版） | Authenticode（`signtool`）+ 时间戳 | `packaging/build-windows.ps1` + `installer.nsi` |
| macOS | `dist/QuickSwitch.app`（**onedir 应用包**，自带 `ui/`、WKWebView 桥接依赖和嵌套 `Deskflow.app`） | codesign（Developer ID + hardened runtime）→ 公证 → 装订 | `packaging/build-macos.sh` |

两端的目标机都不需要预装 Python 或依赖。`main.py` 的 `VERSION`（当前 `2.0.4`）用于运行时与 macOS
`CFBundleShortVersionString`；Windows 的 `packaging/version_info.txt` 是静态版本资源，发布时需要同步更新。
图标由 `packaging/make-icons.py` 用 Pillow 现画（Apple 蓝渐变圆角方块 + 两台显示器 + 箭头），
`icon.png` / `icon.ico` / `icon.icns` 已随仓库提供，构建时若缺失会自动重画。

Deskflow 二进制不提交进 Git。构建前由 `packaging/fetch-deskflow.py` 从官方 `v1.27.0` Release
下载并校验 SHA256；脚本只接受固定的 Windows x64 便携包与 macOS arm64 DMG，校验失败会中止构建。
Windows 由 NSIS 复制到安装目录，macOS 在 PyInstaller 完成后由 `bundle-deskflow.py` 用 `ditto`
原样嵌入 `Contents/Resources/deskflow`，避免 PyInstaller 重写嵌套 Qt framework 的软链。GPL-2.0
许可、固定版本与源码地址见 `THIRD_PARTY_NOTICES.md`；Release 同时上传对应 Deskflow 源码包。

### 7.1 macOS：打包 → 签名 → 公证

公证（notarization）是 Apple 的强制要求：**只签名不公证**的 .app 从网上下载后仍会被 Gatekeeper 拦下。
所以脚本默认把「签名 → 公证 → 装订」一次做完。

一次性准备（需要 Apple Developer Program，99 美元/年）：

```bash
# 1) 在 developer.apple.com 签发「Developer ID Application」证书并装进钥匙串
security find-identity -v -p codesigning      # 应能看到该证书

# 2) 生成 App 专用密码（appleid.apple.com → 登录与安全），存进钥匙串（只需一次）
xcrun notarytool store-credentials quickswitch-notary \
  --apple-id "you@example.com" --team-id TEAMID --password "app-specific-password"
```

之后构建：

```bash
packaging/build-macos.sh --check                                   # 只做环境自检（没证书也能跑，会把缺项列出来）
packaging/build-macos.sh --no-sign                                 # 只出未签名 .app，本机自测
packaging/build-macos.sh --keychain-profile quickswitch-notary     # 签名 + 公证（自动挑 Developer ID 身份）
packaging/build-macos.sh --identity "Developer ID Application: X (TEAMID)" \
                         --keychain-profile quickswitch-notary \
                         --zip dist/QuickSwitch-2.0.4.zip          # 顺便导出一份可分发 zip
```

脚本按顺序做：预检（工具链 / 图标 / 签名身份 / 公证凭据）→ 建 `.venv-build` 并装依赖 → PyInstaller →
`codesign --options runtime --timestamp --entitlements` → `codesign --verify --deep --strict` →
`ditto` 打 zip → `notarytool submit --wait` → 未通过时自动打印 `notarytool log` → `stapler staple` + `validate` →
`spctl -a -vvv` 做 Gatekeeper 评估 → 打印 SHA256。

macOS 版刻意选 **onedir + .app** 而不是 onefile：onefile 会在运行时把内容解到临时目录，
公证对「包里再套未签名二进制」很敏感，而且启动更慢。`packaging/entitlements.plist` 是最小 hardened runtime 集合——
只打开网络客户端/服务端，不放开 JIT 与库校验。

### 7.2 Windows：打包 → Authenticode 签名

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build-windows.ps1 -Check
powershell -ExecutionPolicy Bypass -File packaging\build-windows.ps1 -NoSign
powershell -ExecutionPolicy Bypass -File packaging\build-windows.ps1 `
    -PfxPath C:\certs\quickswitch.pfx -PfxPassword $env:QS_PFX_PASSWORD
powershell -ExecutionPolicy Bypass -File packaging\build-windows.ps1 `
    -CertSubject "CN=Your Company, O=Your Company, C=CN"       # 证书已装进证书存储时
```

签名材料三选一：

| 方式 | 参数 | 说明 |
| --- | --- | --- |
| pfx 文件 | `-PfxPath` + `-PfxPassword` | 最常用；脚本调 `signtool /f /p` |
| pfx 的 base64 | 环境变量 `QS_PFX_BASE64` | 给 CI 用（不必把证书文件写进构建目录）；脚本解到临时文件，签完立刻删除 |
| 证书存储 | `-CertSubject` | 证书已装进 `Cert:\CurrentUser\My` / `Cert:\LocalMachine\My` 时，用 `/n` 按主题选 |

脚本按顺序做：预检（Python / signtool / 签名材料，并核对 `main.py` 的 `VERSION` 与 `version_info.txt` 一致）→
建 `.venv-build` 并装依赖 → PyInstaller → `signtool sign /fd sha256 /tr <时间戳> /td sha256` →
`signtool verify /pa` → `Get-AuthenticodeSignature` 复核 → 打印 SHA256 与后续步骤。

`signtool.exe` 会自动定位：PATH → vswhere（Visual Studio）→ `Windows Kits\10\bin`，装了 Windows SDK 就能直接用。

未签名（`-NoSign`）的 exe 首次运行会弹 SmartScreen「Windows 已保护你的电脑」；普通 OV 证书也只是逐步积累信誉，
**要立刻消除警告需要 EV 证书或走 Microsoft Store 分发**。

### 7.3 生成安装包与自动发布

普通用户下载的是安装包，不需要源码和 Python：

- macOS：`build-macos.sh` 产出 `.app`，再由 `build-dmg.sh` 打成 DMG（内含 `Applications` 快捷方式与安装说明）。
- Windows：PyInstaller 产出单文件 `QuickSwitch.exe`，再由 NSIS 的 `installer.nsi` 连同 `deskflow\` 打成 `QuickSwitch-Setup-<版本>.exe`。

本地生成 macOS 安装包：

```bash
python3 packaging/fetch-deskflow.py --target macos-arm64
packaging/build-macos.sh --no-sign
packaging/build-dmg.sh --out dist/QuickSwitch-2.0.4-macOS-arm64.dmg
```

Windows 安装包在 Windows 构建机上生成：

```powershell
python packaging\fetch-deskflow.py --target windows-x64
powershell -ExecutionPolicy Bypass -File packaging\build-windows.ps1 -NoSign
makensis -INPUTCHARSET UTF8 /DVERSION=2.0.4 packaging\installer.nsi
```

GitHub Actions 的发布流程在 `.github/workflows/release.yml`：推送 `v*` 标签后先在 macOS/Windows
跑测试，再自动下载固定版本 Deskflow、构建安装包，并在 Windows Runner 上执行静默安装 → 检查内置核心 →
启动/停止无界面核心 → 静默卸载的验收。Release 会同时上传安装包、`SHA256SUMS.txt`、`INSTALL.md`、
`THIRD_PARTY_NOTICES.md` 与 Deskflow 对应源码包。

macOS 版只支持 Apple Silicon。`build-macos.sh` 与 `build-dmg.sh` 都会在非 arm64 构建机上直接失败，
DMG 脚本还会检查 `.app` 内是否包含 arm64 可执行文件。

```bash
git tag v2.0.4
git push origin v2.0.4
```

CI 默认产出**未签名**安装包。要发布签名/公证版本，需要把 Apple Developer ID 与 Windows 代码签名材料接入仓库 Secrets，
并在 workflow 中调用现有的签名参数；没有证书时，macOS 需右键打开、Windows 需通过 SmartScreen 的「仍要运行」。

### 7.4 打包脚本开关

| 开关 | 平台 | 作用 |
| --- | --- | --- |
| `--check` / `-Check` | 两边 | 只做环境自检（工具链、图标、证书/签名材料、公证凭据），不构建 |
| `--no-sign` / `-NoSign` | 两边 | 只产出未签名产物，本地自测用 |
| `--skip-notarize` | macOS | 签名但不公证（验证 hardened runtime 时可先跑到这一步） |
| `--identity` / `-CertSubject` | 两边 | 指定签名身份；macOS 不指定则自动挑 Developer ID，Windows 必须显式给 pfx 或证书主题 |
| `--keychain-profile` | macOS | notarytool 凭据名（不传就跳过公证） |
| `--dist` / `--work` / `--venv` / `--python` / `-Python` | 两边 | 改产物目录、中间目录、构建虚拟环境与解释器 |
| `--zip` | macOS | 额外导出一份公证后装订过的分发 zip |
| `-SkipInstall` | Windows | 复用已有 `.venv-build`，跳过 pip 安装（CI 缓存用） |

`dist/`、`build/`、`.venv-build/` 都是可丢弃的中间状态，不必提交。

### 7.5 打包后才出现的行为

这几处只在「打包运行」时生效，源码直跑看不到：

| 行为 | 实现 | 说明 |
| --- | --- | --- |
| 前端随包分发 | `webui._ui_dir()` 优先取 `sys._MEIPASS/ui` | 打包后没有源码目录，`ui/` 由 spec 的 `datas=[(…/ui, "ui")]` 装进包里，控制台页面照常 |
| Windows 控制台输出 | `main.attach_parent_console()` | Windows 版是 `console=False`（不弹黑窗），但 `QuickSwitch.exe --status` 在 cmd 里仍看得到输出：启动时 `AttachConsole(-1)` 附着到父控制台 |
| 菜单栏程序 | `LSUIElement = True` | macOS 版不进 Dock、不抢焦点，只在菜单栏出图标 |
| 局域网权限描述 | `NSLocalNetworkUsageDescription` | macOS 15+ 访问局域网会弹权限框，缺这条会被系统静默拒绝 |
| 不压缩 | `upx = False` | UPX 处理过的可执行文件会破坏签名/公证 |
| 退出方式 | 托盘菜单「退出」 | 托盘运行时主线程停在 Cocoa 事件循环，`SIGTERM` 不会被处理（日志里连「收到信号」都不会出现），自动化脚本停进程请用 `kill -9`；`--no-tray` 运行时 SIGTERM 正常退出 |

装到目标机后还需要（与源码部署一致，见 §4）：

- Windows：NSIS 安装包会自动放行 TCP 8765（切换通知）、UDP 8766（自动发现）和键鼠共享 TCP 24800；直接运行单文件 exe 时需手动执行
  `netsh advfirewall firewall add rule name="QuickSwitch" dir=in action=allow protocol=TCP localport=8765`
  、`netsh advfirewall firewall add rule name="QuickSwitch Discovery" dir=in action=allow protocol=UDP localport=8766`
  和 `netsh advfirewall firewall add rule name="QuickSwitch Deskflow" dir=in action=allow protocol=TCP localport=24800`。
  注册全局热键需要管理员权限（托盘图标本身不需要）。
- macOS：内置键鼠共享核心需要「辅助功能」「输入监控」权限；首次被 QuickSwitch 访问局域网时允许弹窗。

### 7.6 本目录的验证状态

> 当前发布策略：`v2.0.4` 继续内置官方 Deskflow 无界面核心，修正 Mac 热键提示与键盘布局同步策略，并修复 Windows 安装器中文乱码；macOS 安装包仅提供 Apple Silicon（arm64）。

- **v2.0.4**：macOS 客户端默认关闭 Deskflow 的 `languageSync`，保留 Mac 自己的当前输入源，避免 Windows 布局在 Mac 上缺失时键位错乱；该选项仍可在设置页手动开启。Mac 主界面不再把未在本机注册的热键误标为可用热键，而是明确标注为「Windows 键盘」。Windows NSIS 安装器改用带 BOM 的 UTF-8 脚本并通过 `-INPUTCHARSET UTF8` 编译，修复安装过程与完成页中文乱码。新增配置校验、Deskflow 配置生成和安装器编码回归测试。
- **v2.0.3**：修复 Windows 覆盖安装时旧 `QuickSwitch.exe` 仍在运行、导致二进制未真正替换的问题；安装器和卸载器会先结束旧的 QuickSwitch 与 `deskflow-core` 进程。设置窗口子进程若在启动阶段退出，父进程现在会识别失败并回退到默认浏览器，不再表现为点击后无响应。新增对应回归测试。
- **v2.0.2**：修复 `v2.0.1` Windows 设置窗口不显示。设置窗口是 GUI 子进程，不能再复用带 `STARTUPINFO.wShowWindow = SW_HIDE` 的控制台静默参数；新版改用仅设置 `CREATE_NO_WINDOW` 的窗口子进程参数，既避免控制台闪动，也不会隐藏 WebView 窗口。新增对应回归测试。
- **v2.0.1**：Windows 运行时所有控制台子进程（`tasklist`、`taskkill`、`netstat`、DDC 回退工具和设置窗口）统一使用 `CREATE_NO_WINDOW`，修复启动后终端窗口反复闪动。新增键鼠共享可读状态：主界面显示「已连接 / 等待连接 / 连接异常 / 未运行」，详情展示活动 TCP 连接数、最近错误；连接成功依据真实 `ESTABLISHED` 连接或 Deskflow 本次日志，而不是只看核心进程是否存活。
- **v2.0.0**：官方 Deskflow 1.27.0 无界面核心随 QuickSwitch 打包，不再要求用户安装或打开 Deskflow 客户端。应用自动按平台选择服务端/客户端、发现 Windows 地址、生成共享配置并管理核心进程；键鼠共享、热键、端口和屏幕方向可在设置页即时调整。Windows 安装包内置核心并放行 TCP 24800，macOS App 内置官方 `Deskflow.app`，退出 QuickSwitch 时同步停止核心。设置页新增键鼠共享状态、日志和 macOS 权限引导；全新大版本保留 DDC、6 位配对码、配置向导与 Windows DPI 修复。
- **v1.0.3**：Windows 原生 DDC 会先按 `display_index` 选择物理显示器，失败后继续尝试其它显示器；读取失败/写入失败会记录具体 WinError。新增 `--ddc-selftest`（读取当前输入源并写回同一个值，不改变画面）；DDC 错误日志、配置向导、`--status` 和安装文档会直接说明如何在 OSD 中开启 DDC/CI。Windows 安装包新增 UDP 8766 自动发现防火墙规则。157 项测试通过。
- **已验证**：首次启动自动打开四步配置向导（连接 / 安全 / 显示器 / 完成）；
  `setup.completed` 支持旧配置迁移，已有配置不会重复弹向导。157 项测试通过，`node --check ui/app.js`
  与 Python 编译检查通过；1120×820、780×700、浅色与深色布局已检查。
- **已验证**：`build-macos.sh --no-sign` 产出 arm64 `.app`，`build-dmg.sh` 产出 DMG 并通过
  `hdiutil verify`；成品 App 会拉起独立的 `--settings-window` 子进程，`/api/status` 返回真实
  `setup.completed`、DDC 后端与输入源状态。
- **已验证（内置 Deskflow）**：官方 macOS arm64 `Deskflow.app` 原样嵌入
  `QuickSwitch.app/Contents/Resources/deskflow`，嵌套 App 签名校验通过；用 `--deskflow-status`
  能识别 `bundled=true`，用 `--start-deskflow` 能从嵌套路径实际启动。DMG 内也已确认包含该 App。
- **已验证（本机 macOS）**：`m1ddc` 读取当前输入源正常；运行中的 App 实际执行
  `Windows → 15`、`Mac → 18` 两次 DDC 切换并回读一致。macOS 自动使用 `client` 角色，
  Windows 自动使用 `server` 角色。
- **已验证（Windows 高 DPI 配置）**：Windows EXE manifest 声明 Per-Monitor V2，
  `settings_window.py` 在 WebView2 创建前提供运行时兜底；manifest 解析和专项测试通过。
- **发布产物**：GitHub Actions 在 `v2.0.4` 标签上构建 macOS arm64 DMG、Windows Setup 与
  `SHA256SUMS.txt`。安装包未签名，首次打开方式见 README。
- **未验证**（本机不具备条件）：真实 `codesign` / `notarytool` / `stapler` 全流程——本机只装了 Command Line Tools，
  钥匙串里没有 Developer ID 证书，`build-macos.sh --check` 会明确报出这两项缺失（预期行为）；
  Windows 安装包的静默安装/启动/卸载验收脚本已加入 release workflow，但尚未在实体 Windows 上通过 CI 跑完。
  首次在真实签名环境运行时建议先跑 `--check` / `-Check` 看缺什么。

## 8. 验收清单（对应方案第 9 节）

### 8.1 DDC 双向控制

Windows 默认走系统内置的 DXVA2 后端，封装在 `windows_ddc.py` 中。程序会枚举物理显示器，
用 `GetVCPFeatureAndVCPFeatureReply` / `SetVCPFeature` 读写 VCP 0x60。先用 QuickSwitch 自检：

```bat
"%ProgramFiles%\QuickSwitch\QuickSwitch.exe" --status
```

正常时 DDC 后端一行应显示 `Windows 原生 DDC（DXVA2）已检测到 ...`，读取方式显示
`Windows 原生 DXVA2（无需外部命令）`。只有原生后端失败、且确实配置了
`ddc.controlmyMonitor_path` 时，才会尝试下面这个可选回退工具：

```bat
C:\Tools\ControlMyMonitor.exe /SetValue "\\.\DISPLAY1\Monitor0" 0x60 15
C:\Tools\ControlMyMonitor.exe /GetValue "\\.\DISPLAY1\Monitor0" 0x60

:: 显示器保持显示 Mac，再从 Windows 后台执行，验证能否反向切回（对应方案 10.1）
C:\Tools\ControlMyMonitor.exe /SetValue "\\.\DISPLAY1\Monitor0" 0x60 17
```

macOS：

```bash
m1ddc display list
m1ddc display 1 get input         # 读取当前输入源（源码支持，README 未列出）
m1ddc display 1 set input 15      # 切到 Mac
m1ddc display 1 set input 17      # 切到 Windows（需显示器支持在非激活输入源上执行 DDC）
```

各平台读取当前输入源的能力（`--status` 与 `--detect-inputs` 依赖它）：

| 平台 | 读取命令 | 说明 |
| --- | --- | --- |
| Windows | 系统 `dxva2.dll`（原生 DXVA2） | 按 `ddc.display_index` 选择物理显示器；ControlMyMonitor 仅为可选回退 |
| macOS | `m1ddc display <n> get input` | 只输出一个整数；显示器不支持读 VCP 0x60 时命令失败 → 视为读不到 |
| Linux | `ddcutil --display <n> getvcp 60 --terse` | 输出形如 `VCP 60 SNC 0x000f` |
| 任意 | `ddc.read_template` + `ddc.read_regex` | 用别的工具（如 BetterDisplay CLI）读取时改这两项即可 |

> 若 `display_index` 与实际的物理显示器顺序不同，先修正配置；单屏保持 `1`。
> 只有使用外部回退时才需要 `monitor_id`；ControlMyMonitor 版本命令行不同，可用
> `ddc.command_template` 覆盖，无需改代码。

### 8.2 自动识别输入源取值

不想手工找 `mac_input` / `win_input` 时，直接跑向导（Windows / macOS / Linux 都可用，
前提是「能读当前输入源」，见 §8.1 的能力表）：

```bash
python main.py --detect-inputs
```

它会：

1. 读取当前输入源，并逐一试探候选取值（默认 `1,3,15,16,17,18,27`），每次 `set` 后**回读确认**；
2. 逐值切换并询问「屏幕上是 Windows 桌面 / Mac 桌面 / 黑屏」（探测与询问之间会恢复原输入源，
   所以回答问题的时候屏幕已经切回来了）；
3. 回读校验两个取值，然后写入 `config.json`，并打印一行可直接复制到另一端的 JSON；
4. 结束后恢复原始输入源。

常用变体：

```bash
python main.py --detect-inputs --mac-input 15 --win-input 17   # 已知取值，跳过提问
python main.py --detect-inputs --candidates 15,17,27           # 自定义候选取值
python main.py --detect-inputs --no-probe                      # 不探测，只校验并写配置
python main.py --detect-inputs --no-write                      # 只看结果，不改配置
python main.py --detect-inputs --non-interactive --win-input 17 --mac-input 15  # 脚本/自启用
```

说明与限制：

- 探测期间屏幕会短暂切换/黑屏，属正常现象；结束会切回原来的输入源。
- 取值是**显示器属性**，同一台显示器在两端一致，所以一端识别成功后，把打印出的 JSON 复制到另一端即可。
- 若显示器不接受「在非激活输入源上执行 DDC」，探测可能只看到当前那一个值；此时用 §8.1 的手动方式确认。
- 退出码 `0` = 识别成功且回读一致；`1` = 取值缺失或回读不一致（配置仍会写入，需人工复核）。

### 8.3 QuickSwitch 链路

```bash
# 两端各自自检
python main.py --status

# Windows 端整体验证（本地 DDC + 通知 Mac）
python main.py --once mac --dry-run     # 先看将要执行的命令
python main.py --once mac               # 真实切换
```

期望日志：

- Windows：`本地 DDC → Mac：成功`、`本地 DDC 成功；对端 DDC 成功`；
- macOS：`收到对端切换请求：→ Mac`、`本地 DDC → Mac：成功`、`接受来自 <Windows IP> 的连接`。

### 8.4 快捷键与其余组件

- 按 `Ctrl+Alt+1`：显示器切到 Mac、键鼠控制权交给 Mac，两端日志各出现一条切换记录；
- 按 `Ctrl+Alt+2`：切回 Windows；
- 杀掉一端进程：另一端应打印「对端连接断开（会自动重连）」，重启后自动恢复；
- 修改对端 IP 后（Tailscale 或 `"auto"` 模式）无需改配置；
- 剪贴板：Windows 复制文本 → Mac 粘贴，再反向验证（Deskflow）；
- 文件传输：两端打开 LocalSend 应能互相发现并发送文件。

### 8.5 配对码校验（配了 `auth.secret` 才需要跑）

```bash
# 两端都配同一个 6 位配对码后重启，各跑一次：
python3 main.py --status          # 应显示「密钥校验：已通过（hmac-sha256）」
```

- 两端日志应出现「对端密钥校验通过」，且**没有**「丢弃未经校验的报文」；
- 故意把一端的配对码改错再重启：那端日志出现「丢弃未经校验的报文：校验码不匹配」，
  `--status` 显示「未通过」，此时按热键本机照常切换、但对端不动（符合预期）；
- 不改任何硬件也能验证这条链路：`python3 scripts/selftest.py` 里包含 3 项对应用例
  （正确配对码通过、错误配对码的连接能建立但切换被拒、错误配对码没能触发切换）。

## 9. 故障排查

| 现象 | 处理 |
| --- | --- |
| 启动报「监听端口 8765 不可用」 | 已有一个 QuickSwitch 在跑（退出码 3）；或改 `listen_port` |
| 按热键无反应 | 需管理员权限（用 `install-task.ps1` 或「以管理员身份运行」）；检查是否与其他软件抢占热键；`--log-level DEBUG` 看是否注册成功 |
| QuickSwitch 没拉到键鼠共享核心 | 运行 `--deskflow-status` 看 `installed` / `bundled` / `managed` / `running` / `connected` / `last_error`；安装包内置版应分别位于 `QuickSwitch\deskflow` 或 App 的 `Contents/Resources/deskflow`；也可在设置页点「重启键鼠共享」 |
| 只切了显示器和键鼠之一 | 先看主界面键鼠共享状态；「等待连接」表示核心运行但尚未握手，「连接异常」会显示超时/拒绝/权限原因。再检查 `~/.quickswitch/deskflow/deskflow.log`、两端 `deskflow.port` 是否一致、`deskflow.mac_side` 是否与实际屏幕方向一致；macOS 权限不足时重启核心 |
| 显示器不切换，日志显示 DDC 失败 | 确认 `ddc.display_index`；显示器需支持并开启 DDC/CI（部分型号需在 OSD 菜单打开）；建议视频线直连、避免转接。Windows 原生 DXVA2 失败时，ControlMyMonitor 只是可选回退，不是必需依赖 |
| Windows 提示找不到 `ControlMyMonitor.exe` | 这是旧版安装包的外部回退路径。最新版应使用原生 DXVA2；升级后重跑 `--status`，若仍看不到原生后端，检查显示器 DDC/CI 与连接方式 |
| `--status` 显示「无法读取」 | 显示器不支持/未开启读 VCP 0x60，或当前后端不可用。此时仍可能正常发送切换，只是无法回读校验：可用 §8.1 的方法确认，或配置 `ddc.read_template` 使用支持读取的工具 |
| `--detect-inputs` 探测不到可用值 | 先确认 §8.1 的手动 set/get 是否都能成功；显示器若不允许在非激活输入源上 DDC，就用手动方式确认两个值后 `--detect-inputs --mac-input 15 --win-input 17` |
| 识别出的两个值反了 | 直接 `--detect-inputs --mac-input <值> --win-input <值>` 覆盖，或手动改 `config.json`；两个值的配对不影响底层机制 |
| Windows 能切到 Mac，Mac 侧切不回 Windows | 方案 10.1 描述的现象：非激活输入源不支持 DDC。Mac 端常驻 QuickSwitch 后由 TCP 通知切换即可；仍不行则用显示器自动信号源或按钮兜底 |
| 日志出现「对端未确认」 | 对端程序没在跑、防火墙挡了 8765、或 `peer_host` 指错。用 `python main.py --status` 检查连通性 |
| 日志出现「丢弃未经校验的报文」 | 两端配对码不一致（或对端没配）。用 `--status` 看「密钥校验」一行，两端填同一个 6 位配对码后重启 |
| 设了配对码后完全切不过去 | 确认两端进程都重启过（配对码在启动时读取），且没有多余空格；`--status` 显示「未完成」通常是对端版本过旧（不支持 `auth_challenge`） |
| macOS 提示应用「已损坏」 | `xattr -c /Applications/Deskflow.app`，并重新授予辅助功能权限 |
| 在同一台机器上测试两端 | 用 `--config` 指定两份配置（不同 `listen_port`），或让 `peer_host` 明确指向 127.0.0.1 |
| IP 经常变化 | 用 Tailscale，或 `"peer_host": "auto"`；若广播被阻断，把 `discovery.broadcast` 改成网段广播地址（如 `192.168.1.255`） |

## 10. 通信协议

JSON Lines（一行一条 JSON）走 TCP，默认端口 8765；两端都会主动连接对方并监听本地端口。

| 类型 | 方向 | 字段 | 说明 |
| --- | --- | --- | --- |
| `hello` | 连接建立后（两端都发） | `name` `role` `version` `platform` `listen_port` `auth` | 身份交换，日志中可看到对端是谁；`auth` 声明是否要求密钥校验 |
| `auth_challenge` | 双向 | `nonce` `alg` | 仅配置了 `auth.secret` 时发送；`nonce` 每条连接随机生成 |
| `auth_response` | 双向 | `nonce` `mine` `alg` `mac` | 对质询的回答：`mac = HMAC-SHA256(secret, "quickswitch-auth-1\|<对端 nonce>\|<本端 nonce>")` |
| `ping` / `pong` | 双向 | `ts` | 心跳，默认 10s；3 个周期无任何消息则重连 |
| `switch` | 双向 | `target` `id` `source` | 请求对端切换输入源 |
| `switch_ack` | 双向 | `id` `ok` `detail` | 对端执行结果，超时默认 4s |

校验流程（未配置 `auth.secret` 时整段跳过）：

1. 连接建立后双方各发一个 `hello` 和一个 `auth_challenge`（被连的一方也发，保证单向可达时同样能校验）；
2. 收到对方的质询就用同一个密钥算一个 `auth_response` 回去，**只发校验码，不发密钥**；
3. 校验本连接收到的回复：nonce 必须与本连接一致（挡重放）、校验码必须匹配（挡伪造与密钥不一致）；
4. 通过之前，该连接上的 `switch` / `switch_ack` 一律丢弃并在日志里留下「丢弃未经校验的报文」。

## 11. 测试

```bash
python3 -m unittest discover -s tests -t . -v
```

覆盖：配置合并/校验、Windows-macOS-Linux 命令构建与模板、重试与超时、输入源解析、
TCP 双向收发/心跳/重连/端口占用/单向可达回退、设备发现报文与设备表、
两端完整切换链路（含 ACK 与负向 ACK、去抖、本地失败但对端成功）、Web 控制台
（令牌、Host/Origin 防护、状态结构、切换、配置白名单与「需重启」判定、静态文件与目录穿越防护）、
预共享密钥（校验码绑定两个 nonce、密钥不一致时丢弃 switch 与伪造的 switch_ack、
一端未配置、重放旧校验码被拒、`--gen-secret` 与 `--status` 输出不泄漏密钥）、
Deskflow 安装检测 / 后台启动 / 自动启动开关，命令行子进程冒烟测试。

想在不动硬件的情况下看界面，可以用模拟 DDC 工具起一个实例（真的会执行「DDC」命令，
只是这个命令是个写状态文件的脚本）：

```bash
# 用一个只接受 15/17 的假 m1ddc 代替真工具
cat > /tmp/mock-m1ddc.sh <<'EOF'
#!/bin/bash
[ -f /tmp/qs-state ] || echo 17 > /tmp/qs-state
if [ "$3" = "get" ]; then cat /tmp/qs-state; exit 0; fi
case "$5" in 15|17) echo "$5" > /tmp/qs-state; exit 0 ;; *) exit 1 ;; esac
EOF
chmod +x /tmp/mock-m1ddc.sh
python3 main.py --no-tray --print-config > /tmp/qs.json   # 再把 ddc.m1ddc_path 改成 /tmp/mock-m1ddc.sh
python3 main.py --no-tray --config /tmp/qs.json
```

在真机上不想动硬件时，可先跑本机链路自检：它会在临时配置下启动一个真实的
QuickSwitch 进程（`--no-tray --dry-run`），再作为「对端」完成 hello / 心跳 /
switch / switch_ack 全流程，并检查守护进程日志：

```bash
python3 scripts/selftest.py
```

## 12. 参考

- Deskflow：https://github.com/deskflow/deskflow
- Windows DXVA2 原生 DDC：系统组件，无需额外下载
- ControlMyMonitor（可选回退）：https://www.nirsoft.net/utils/control_my_monitor.html
- m1ddc：https://github.com/waydabber/m1ddc
- ddcutil：https://www.ddcutil.com/
- LocalSend：https://github.com/localsend/localsend
- Tailscale：https://tailscale.com/
