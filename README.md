# QuickSwitch

[![Release: latest](docs/images/badge-release.svg)](https://github.com/Jasonlya/quickswitch/releases/latest)
[![License: MIT](docs/images/badge-license.svg)](LICENSE)

一键切换**显示器输入源**和**键鼠控制权**。Windows 与 Mac 共用一台显示器，按 `Ctrl+Alt+1` 切到 Mac，按 `Ctrl+Alt+2` 切回 Windows。

![QuickSwitch 主界面：两个切换按钮、按钮内的热键标记和折叠的信息入口](docs/images/quickstart.png)

## 下载安装

**不需要 Python、pip，也不需要手动安装运行库。** 到 [Releases](https://github.com/Jasonlya/quickswitch/releases/latest) 下载对应安装包：

| 你的电脑 | 下载文件 | 安装方法 |
| --- | --- | --- |
| Mac（Apple 芯片 M1/M2/M3/M4） | `QuickSwitch-1.2.2-macOS-arm64.dmg` | 打开 DMG，把 QuickSwitch 拖进「应用程序」 |
| Mac（Intel 芯片） | `QuickSwitch-1.2.2-macOS-x64.dmg` | 打开 DMG，把 QuickSwitch 拖进「应用程序」 |
| Windows 10/11 64 位 | `QuickSwitch-Setup-1.2.2.exe` | 双击安装，按提示下一步即可 |

安装包已经自带 Python 运行时、托盘依赖和网页设置页，目标电脑不需要开发环境。

> **当前安装包未签名。** macOS 首次打开若提示「无法验证开发者」，请右键 QuickSwitch →「打开」→ 再点「打开」；Windows 首次运行若出现 SmartScreen，请点「更多信息」→「仍要运行」。

## 使用前准备

QuickSwitch 负责切换显示器输入源，不会替代下面两项：

| 需要准备 | 作用 | 在哪里获取 |
| --- | --- | --- |
| Deskflow | 让一套键鼠控制两台电脑 | [deskflow.org](https://deskflow.org/) |
| DDC/CI 工具 | 让程序切换显示器输入源 | Windows：[ControlMyMonitor](https://www.nirsoft.net/utils/control_my_monitor.html)；macOS：[m1ddc](https://github.com/waydabber/m1ddc) |

键鼠接在 Windows 上时：Windows 的 Deskflow 选 **Server**，Mac 的 Deskflow 选 **Client**。

## 首次配置

1. 两台电脑都安装 QuickSwitch，然后启动它。
2. 首次启动会自动在浏览器打开控制台。如果没有自动打开：菜单栏或任务栏托盘右键 QuickSwitch →「打开设置页面」。
3. 主界面只显示切换按钮；点「更多信息与设置」→「配置」，填写下面三项后保存：

   | 设置项 | 怎么填 |
   | --- | --- |
   | 对端地址 | 填**另一台电脑**设置页上显示的「本机 IP」 |
   | 角色 | Windows 选 `server`，Mac 选 `client`（首次启动通常会按系统自动选好） |
   | 预共享密钥 | 两台电脑填**完全相同**的一串字符，建议至少 16 位 |

   监听端口保持默认 `8765`，两端必须一致。

4. 保存后，右键托盘图标 →「退出」，再重新打开 QuickSwitch，让地址、角色和密钥生效。
5. 如果 DDC 工具放在非默认位置，在「更多信息与设置 → 配置」里改成实际路径；路径不确定时，展开后点「探测输入源」，按提示识别 Mac 和 Windows 对应的输入源数值。
6. 展开「更多信息与设置」，在两端「连接」区域看到对端已连接、密钥校验通过，就配置好了。

## 日常使用

- 按 `Ctrl+Alt+1`：切到 Mac；按 `Ctrl+Alt+2`：切回 Windows。
- 主界面的两个切换按钮右侧会直接显示对应热键，不需要展开「更多信息与设置」。
- Deskflow 里也要把热键配成同一组，这样一次按键会同时切换显示器和键鼠。
- 也可以右键菜单栏/托盘图标，选择「切到 Mac」或「切到 Windows」。
- 主界面只保留两个切换按钮。把鼠标停在按钮上，可查看当前输入源、对端连接、密钥校验、DDC 和快捷键摘要。
- 需要读取/探测输入源、检查连接、修改配置或查看日志时，点「更多信息与设置」展开完整面板。

## 常见问题

| 现象 | 处理 |
| --- | --- |
| macOS 提示「无法验证开发者」 | 右键 App →「打开」→「打开」；或到「系统设置 → 隐私与安全性」点「仍要打开」 |
| Windows 提示 SmartScreen | 点「更多信息」→「仍要运行」 |
| 对端一直显示未连接 | 确认两台电脑在同一局域网、端口都是 `8765`、防火墙已放行；macOS 允许 QuickSwitch 访问本地网络 |
| 点切换没有反应 | 检查 DDC 工具路径、显示器是否开启 DDC/CI，再用设置页的「探测输入源」确认取值 |
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
git tag v1.2.2
git push origin v1.2.2
```

构建产物会出现在仓库的 **Releases** 页面。

## License

[MIT](LICENSE) © 2026 Jasonlya
