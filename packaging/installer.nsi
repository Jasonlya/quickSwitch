; QuickSwitch Windows 安装包（NSIS 3.x）
; 构建：makensis -INPUTCHARSET UTF8 -DVERSION=2.3.0 packaging\installer.nsi
; 产物：dist\QuickSwitch-Setup-<VERSION>.exe
; 说明：需要先由 packaging\quickswitch.spec 产出 dist\QuickSwitch.exe

!include "MUI2.nsh"
!include "FileFunc.nsh"

!ifndef VERSION
  !define VERSION "2.3.0"
!endif

!define APPNAME   "QuickSwitch"
!define PUBLISHER "Jasonlya"
!define APPEXE    "QuickSwitch.exe"
!define PROJECTDIR ".."

; Windows 版 NSIS 的 File 命令只按反斜杠拆分路径；Unix 版 makensis 使用正斜杠。
!ifdef NSIS_WIN32_MAKENSIS
  !define DISTDIR "${PROJECTDIR}\dist"
  !define DESKFLOWDIR "${PROJECTDIR}\packaging\vendor\deskflow\windows-x64"
  !define DISTSEP "\"
!else
  !define DISTDIR "${PROJECTDIR}/dist"
  !define DESKFLOWDIR "${PROJECTDIR}/packaging/vendor/deskflow/windows-x64"
  !define DISTSEP "/"
!endif

Name "${APPNAME} ${VERSION}"
OutFile "${DISTDIR}${DISTSEP}QuickSwitch-Setup-${VERSION}.exe"
InstallDir "$PROGRAMFILES64\${APPNAME}"
InstallDirRegKey HKLM "Software\${APPNAME}" "InstallDir"
RequestExecutionLevel admin
Unicode true
SetCompressor /SOLID lzma

VIProductVersion "${VERSION}.0"
VIAddVersionKey /LANG=2052 "ProductName"     "${APPNAME}"
VIAddVersionKey /LANG=2052 "FileDescription" "QuickSwitch 安装程序"
VIAddVersionKey /LANG=2052 "FileVersion"     "${VERSION}.0"
VIAddVersionKey /LANG=2052 "ProductVersion"  "${VERSION}.0"
VIAddVersionKey /LANG=2052 "CompanyName"     "${PUBLISHER}"
VIAddVersionKey /LANG=2052 "LegalCopyright"  "MIT License"

!define MUI_ICON   "icon.ico"
!define MUI_UNICON "icon.ico"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN      "$INSTDIR\${APPEXE}"
!define MUI_FINISHPAGE_RUN_TEXT "立即启动 QuickSwitch"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"

Section "QuickSwitch 主程序" SecMain
    SetRegView 64
    SetShellVarContext all
    SetOutPath "$INSTDIR"

    ; 覆盖安装前先结束旧进程。Windows 不允许覆盖正在运行的 exe；旧实现只让
    ; 用户手动退出，升级后可能仍在运行 v2.0.1，看起来像修复没有生效。
    DetailPrint "正在关闭正在运行的 QuickSwitch..."
    nsExec::ExecToLog 'taskkill /F /IM QuickSwitch.exe /T'
    nsExec::ExecToLog 'taskkill /F /IM deskflow-core.exe /T'
    Sleep 800

    File "${DISTDIR}${DISTSEP}${APPEXE}"
    File "icon.ico"
    File "${PROJECTDIR}${DISTSEP}THIRD_PARTY_NOTICES.md"

    ; Deskflow 随 QuickSwitch 一起安装，用户无需另外下载。
    SetOutPath "$INSTDIR\deskflow"
    File /r "${DESKFLOWDIR}${DISTSEP}*"
    SetOutPath "$INSTDIR"

    CreateDirectory "$SMPROGRAMS\QuickSwitch"
    CreateShortCut "$SMPROGRAMS\QuickSwitch\QuickSwitch.lnk" "$INSTDIR\${APPEXE}"
    CreateShortCut "$SMPROGRAMS\QuickSwitch\卸载 QuickSwitch.lnk" "$INSTDIR\Uninstall.exe"
    CreateShortCut "$DESKTOP\QuickSwitch.lnk" "$INSTDIR\${APPEXE}"

    WriteUninstaller "$INSTDIR\Uninstall.exe"

    WriteRegStr   HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\QuickSwitch" "DisplayName"     "${APPNAME}"
    WriteRegStr   HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\QuickSwitch" "DisplayVersion"  "${VERSION}"
    WriteRegStr   HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\QuickSwitch" "Publisher"       "${PUBLISHER}"
    WriteRegStr   HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\QuickSwitch" "DisplayIcon"     "$INSTDIR\${APPEXE}"
    WriteRegStr   HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\QuickSwitch" "InstallLocation" "$INSTDIR"
    WriteRegStr   HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\QuickSwitch" "UninstallString" '"$INSTDIR\Uninstall.exe"'
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\QuickSwitch" "NoModify" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\QuickSwitch" "NoRepair" 1
    ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
    IntFmt $0 "0x%08X" $0
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\QuickSwitch" "EstimatedSize" "$0"

    WriteRegStr HKLM "Software\${APPNAME}" "InstallDir" "$INSTDIR"

    ; 放行局域网端口（切换通知需要）
    nsExec::ExecToLog 'netsh advfirewall firewall delete rule name="QuickSwitch"'
    nsExec::ExecToLog 'netsh advfirewall firewall add rule name="QuickSwitch" dir=in action=allow protocol=TCP localport=8765'
    nsExec::ExecToLog 'netsh advfirewall firewall delete rule name="QuickSwitch Discovery"'
    nsExec::ExecToLog 'netsh advfirewall firewall add rule name="QuickSwitch Discovery" dir=in action=allow protocol=UDP localport=8766'
    nsExec::ExecToLog 'netsh advfirewall firewall delete rule name="QuickSwitch Deskflow"'
    nsExec::ExecToLog 'netsh advfirewall firewall add rule name="QuickSwitch Deskflow" dir=in action=allow protocol=TCP localport=24800'

    ; 快捷方式以管理员身份运行：Windows 端注册全局热键需要
    WriteRegStr HKLM "Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers" \
        "$INSTDIR\${APPEXE}" "RUNASADMIN"
SectionEnd

Section "Uninstall"
    SetRegView 64
    SetShellVarContext all
    nsExec::ExecToLog 'taskkill /F /IM QuickSwitch.exe /T'
    nsExec::ExecToLog 'taskkill /F /IM deskflow-core.exe /T'
    Sleep 500
    Delete "$INSTDIR\${APPEXE}"
    Delete "$INSTDIR\icon.ico"
    Delete "$INSTDIR\THIRD_PARTY_NOTICES.md"
    RMDir /r "$INSTDIR\deskflow"
    Delete "$INSTDIR\Uninstall.exe"
    RMDir  "$INSTDIR"

    Delete "$SMPROGRAMS\QuickSwitch\QuickSwitch.lnk"
    Delete "$SMPROGRAMS\QuickSwitch\卸载 QuickSwitch.lnk"
    RMDir  "$SMPROGRAMS\QuickSwitch"
    Delete "$DESKTOP\QuickSwitch.lnk"

    nsExec::ExecToLog 'netsh advfirewall firewall delete rule name="QuickSwitch"'
    nsExec::ExecToLog 'netsh advfirewall firewall delete rule name="QuickSwitch Discovery"'
    nsExec::ExecToLog 'netsh advfirewall firewall delete rule name="QuickSwitch Deskflow"'

    DeleteRegValue HKLM "Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers" "$INSTDIR\${APPEXE}"
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\QuickSwitch"
    DeleteRegKey HKLM "Software\${APPNAME}"

    ; 用户配置（%USERPROFILE%\.quickswitch）保留，方便重装后继续用
SectionEnd
