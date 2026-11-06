; QuickSwitch Windows 安装包（NSIS 3.x）
; 构建：makensis /DVERSION=1.0.0 packaging\installer.nsi
; 产物：dist\QuickSwitch-Setup-<VERSION>.exe
; 说明：需要先由 packaging\quickswitch.spec 产出 dist\QuickSwitch.exe

!include "MUI2.nsh"
!include "FileFunc.nsh"

!ifndef VERSION
  !define VERSION "1.0.0"
!endif

!define APPNAME   "QuickSwitch"
!define PUBLISHER "Jasonlya"
!define APPEXE    "QuickSwitch.exe"
!define PROJECTDIR ".."

; Windows 版 NSIS 的 File 命令只按反斜杠拆分路径；Unix 版 makensis 使用正斜杠。
!ifdef NSIS_WIN32_MAKENSIS
  !define DISTDIR "${PROJECTDIR}\dist"
  !define DISTSEP "\"
!else
  !define DISTDIR "${PROJECTDIR}/dist"
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
    File "${DISTDIR}${DISTSEP}${APPEXE}"
    File "icon.ico"

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

    ; 快捷方式以管理员身份运行：Windows 端注册全局热键需要
    WriteRegStr HKLM "Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers" \
        "$INSTDIR\${APPEXE}" "RUNASADMIN"
SectionEnd

Section "Uninstall"
    SetRegView 64
    SetShellVarContext all
    Delete "$INSTDIR\${APPEXE}"
    Delete "$INSTDIR\icon.ico"
    Delete "$INSTDIR\Uninstall.exe"
    RMDir  "$INSTDIR"

    Delete "$SMPROGRAMS\QuickSwitch\QuickSwitch.lnk"
    Delete "$SMPROGRAMS\QuickSwitch\卸载 QuickSwitch.lnk"
    RMDir  "$SMPROGRAMS\QuickSwitch"
    Delete "$DESKTOP\QuickSwitch.lnk"

    nsExec::ExecToLog 'netsh advfirewall firewall delete rule name="QuickSwitch"'

    DeleteRegValue HKLM "Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers" "$INSTDIR\${APPEXE}"
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\QuickSwitch"
    DeleteRegKey HKLM "Software\${APPNAME}"

    ; 用户配置（%USERPROFILE%\.quickswitch）保留，方便重装后继续用
SectionEnd
