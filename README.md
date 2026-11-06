# QuickSwitch

[![Release: latest](docs/images/badge-release.svg)](https://github.com/Jasonlya/quickswitch/releases/latest)
[![License: MIT](docs/images/badge-license.svg)](LICENSE)

一键切换**显示器输入源**和**键鼠控制权**。Windows 与 Mac 共用一台显示器，按 `Ctrl+Alt+1` 切到 Mac，按 `Ctrl+Alt+2` 切回 Windows。

![QuickSwitch 主界面：两个切换按钮、按钮内的热键标记和折叠的信息入口](docs/images/quickstart.png)

## 下载安装

**不需要 Python、pip，也不需要手动安装运行库。** 到 [Releases](https://github.com/Jasonlya/quickswitch/releases/latest) 下载对应安装包：

| 你的电脑 | 下载文件 | 安装方法 |
| --- | --- | --- |
| Mac（Apple 芯片 M1/M2/M3/M4） | `QuickSwitch-*-macOS-arm64.dmg` | 打开 DMG，把 QuickSwitch 拖进「应用程序」 |
| Windows 10/11 64 位 | `QuickSwitch-Setup-*.exe` | 双击安装，按提示下一步即可 |

macOS 版只支持 Apple Silicon，不提供 Intel Mac 安装包。安装包已经自带 Python 运行时、托盘依赖和原生设置窗口，目标电脑不需要开发环境。

> **当前安装包未签名。** macOS 首次打开若提示「无法验证开发者」，请右键 QuickSwitch →「打开」→ 再点「打开」；Windows 首次运行若出现 SmartScreen，请点「更多信息」→「仍要运行」。

## 使用前准备

QuickSwitch 负责切换显示器输入源，不会替代下面两项：

| 需要准备 | 作用 | 在哪里获取 |
| --- | --- | --- |
| Deskflow | 让一套键鼠控制两台电脑 | [deskflow.org](https://deskflow.org/) |
| 显示器 DDC/CI | 允许电脑切换显示器的输入源 | 按显示器机身按钮打开 OSD 菜单，在「系统 / 设置 / 其他设置」里找 DDC/CI；多数型号默认开启，详细路径见 [INSTALL.md](INSTALL.md#11-开启显示器-ddcci) |

键鼠接在 Windows 上时：Windows 的 Deskflow 选 **Server**，Mac 的 Deskflow 选 **Client**。

Windows 端已内置原生 DDC（DXVA2），**不需要安装 ControlMyMonitor**。macOS 端需要 Apple Silicon，并安装 [m1ddc](https://github.com/waydabber/m1ddc)；如果 Mac 端提示找不到 DDC 工具，按安装文档确认 `ddc.m1ddc_path`。

## 首次配置

1. 两台电脑都安装并启动 QuickSwitch。首次启动会自动弹出**配置向导**。
2. **连接**：推荐选「自动发现」；需要手动填 IP 时，把另一台电脑向导左侧显示的「本机 IP」填进来。
3. **安全**：点「生成」得到 6 位配对码，复制或手动输入到另一台电脑。两端配对码必须完全一致。
4. **显示器**：点「读取」确认当前输入源，再标记为 Mac 或 Windows；也可以直接填写已知数值，或点「探测」让程序试探。
5. **完成**：检查摘要后点「完成配置」。关闭设置窗口，从菜单栏/托盘菜单退出 QuickSwitch，再重新打开，让连接配置生效。

向导只在首次配置时自动出现。以后要修改，展开「更多信息与设置」→「配置」，点「重新运行配置向导」。

## 日常使用

- 按 `Ctrl+Alt+1`：切到 Mac；按 `Ctrl+Alt+2`：切回 Windows。
- 主界面的两个切换按钮右侧会直接显示对应热键，不需要展开「更多信息与设置」。
- Deskflow 里也要把热键配成同一组，这样一次按键会同时切换显示器和键鼠。
- 也可以右键菜单栏/托盘图标，选择「切到 Mac」或「切到 Windows」。
- 设置窗口是应用内原生弹窗，不占用浏览器标签页；主界面只保留两个切换按钮。把鼠标停在按钮上，可查看当前输入源、对端连接、密钥校验、DDC 和快捷键摘要。
- 需要读取/探测输入源、检查连接、修改配置或查看日志时，点「更多信息与设置」展开完整面板。

## 常见问题

| 现象 | 处理 |
| --- | --- |
| macOS 提示「无法验证开发者」 | 右键 App →「打开」→「打开」；或到「系统设置 → 隐私与安全性」点「仍要打开」 |
| Windows 提示 SmartScreen | 点「更多信息」→「仍要运行」 |
| 对端一直显示未连接 | 确认两台电脑在同一局域网；Windows 防火墙已放行 TCP `8765` 和自动发现用的 UDP `8766`；macOS 允许 QuickSwitch 访问本地网络 |
| 点切换没有反应 / 找不到 DDC/CI | 按显示器机身的按钮或摇杆打开 OSD 菜单（不是 Windows 显示设置），在「系统 / 设置 / 其他设置 / OSD 设置 / 管理」里找「DDC/CI」（也可能叫 DDC/CI Support、Monitor Control、MCCS 或 Display Data Channel），设为「开 / On」，保存后等 5 秒再试。仍无效时改用直连视频线，绕开 KVM、扩展坞或切换器 |
| Windows 提示找不到 `ControlMyMonitor.exe` | 旧版安装包的回退路径。最新版使用 Windows 内置 DXVA2，不需要该文件；升级后重试，ControlMyMonitor 仅作为可选回退 |
| Windows 设置窗口字体模糊 | 升级到 `v1.0.2` 或更高版本；该版本启用 Per-Monitor V2 DPI 感知。升级后仍模糊时，检查 Windows 显示缩放并更新 WebView2 Runtime |
| Windows DDC 切换报错 | 错误日志会直接列出 OSD 开启步骤。仍失败时在 cmd 运行 `"C:\Program Files\QuickSwitch\QuickSwitch.exe" --ddc-selftest`，先做不改变画面的写入自检；输出会包含具体 WinError 和处理建议 |
| 显示器切了但键鼠没过去 | 这是 Deskflow 的连接或热键配置问题，不是 QuickSwitch 负责的范围 |
| 想查看日志 | macOS：`~/.quickswitch/quickswitch.log`；Windows：`%USERPROFILE%\.quickswitch\quickswitch.log` |
| 想卸载 | macOS 删除「应用程序」里的 QuickSwitch；Windows 用「设置 → 应用 → QuickSwitch → 卸载」。用户配置默认保留 |

更完整的环境检查、权限、开机自启和排错步骤见 [INSTALL.md](INSTALL.md)。

## 技术文档与开发

- [安装与使用详解](INSTALL.md)
- [完整技术文档](docs/TECHNICAL.md)：配置项、通信协议、接口、验收与打包细节
- [从源码运行](docs/TECHNICAL.md)：需要 Python 3.9+，普通用户不需要这一步

发布新版本时，维护者推送 `v*` 标签即可触发 GitHub Actions，自动构建 macOS DMG 和 Windows 安装包：

```bash
git tag v1.0.3
git push origin v1.0.3
```

构建产物会出现在仓库的 **Releases** 页面。

## License

[MIT](LICENSE) © 2026 Jasonlya
