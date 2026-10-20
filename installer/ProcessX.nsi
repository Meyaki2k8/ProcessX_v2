; ProcessX v2.0 installer (NSIS 3.x, Unicode)
Unicode true
SetCompressor /SOLID lzma

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"
!insertmacro GetSize
!insertmacro GetFileName

!define APP_NAME   "ProcessX v2.0"
!define APP_EXE    "ProcessX v2.0.exe"
!define APP_VER    "2.0.0.0"
!define PUBLISHER  "ProcessX"
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"
!define MUTEX_NAME "Local\ProcessX_SingleInstance_v2"
!define SRC_DIR    "..\dist\${APP_NAME}"

Name "${APP_NAME}"
OutFile "..\dist\ProcessX_v2.0_Setup.exe"
InstallDir "$PROGRAMFILES64\${APP_NAME}"
RequestExecutionLevel admin
BrandingText "${APP_NAME} - Built on ${__DATE__} ${__TIME__}"

VIProductVersion "${APP_VER}"
VIAddVersionKey "ProductName" "${APP_NAME}"
VIAddVersionKey "FileDescription" "${APP_NAME} Setup"
VIAddVersionKey "FileVersion" "${APP_VER}"
VIAddVersionKey "ProductVersion" "${APP_VER}"
VIAddVersionKey "LegalCopyright" "ProcessX"

!define MUI_ICON "..\assets\Meyaki.ico"
!define MUI_UNICON "..\assets\Meyaki.ico"
!define MUI_ABORTWARNING
!define MUI_LANGDLL_REGISTRY_ROOT "HKLM"
!define MUI_LANGDLL_REGISTRY_KEY "${UNINST_KEY}"
!define MUI_LANGDLL_REGISTRY_VALUENAME "InstallerLanguage"

!insertmacro MUI_PAGE_COMPONENTS
!define MUI_PAGE_CUSTOMFUNCTION_LEAVE DirLeave
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "Vietnamese"

LangString SEC_START   ${LANG_ENGLISH}    "Start menu shortcuts"
LangString SEC_START   ${LANG_VIETNAMESE} "Lối tắt Start menu"
LangString SEC_DESKTOP ${LANG_ENGLISH}    "Create Desktop Shortcut"
LangString SEC_DESKTOP ${LANG_VIETNAMESE} "Tạo lối tắt ngoài Desktop"
LangString SEC_LAUNCH  ${LANG_ENGLISH}    "Launch ${APP_NAME}"
LangString SEC_LAUNCH  ${LANG_VIETNAMESE} "Chạy ${APP_NAME} sau khi cài"
LangString DESC_MAIN   ${LANG_ENGLISH}    "Installs ${APP_NAME} program files."
LangString DESC_MAIN   ${LANG_VIETNAMESE} "Cài đặt các tệp chương trình của ${APP_NAME}."
LangString DESC_START  ${LANG_ENGLISH}    "Adds ${APP_NAME} to the Start menu."
LangString DESC_START  ${LANG_VIETNAMESE} "Thêm ${APP_NAME} vào Start menu."
LangString DESC_DESKTOP ${LANG_ENGLISH}    "Adds a ${APP_NAME} shortcut to the Desktop."
LangString DESC_DESKTOP ${LANG_VIETNAMESE} "Thêm lối tắt ${APP_NAME} ra Desktop."
LangString DESC_LAUNCH ${LANG_ENGLISH}    "Starts ${APP_NAME} when setup finishes."
LangString DESC_LAUNCH ${LANG_VIETNAMESE} "Mở ${APP_NAME} ngay khi cài xong."
LangString MSG_RUNNING ${LANG_ENGLISH}    "${APP_NAME} is running.$\r$\nExit it completely (tray icon > Quit), then click Retry."
LangString MSG_RUNNING ${LANG_VIETNAMESE} "${APP_NAME} đang chạy.$\r$\nHãy thoát hẳn (biểu tượng khay hệ thống > Thoát), rồi bấm Retry."

!macro DEFINE_CHECK_RUNNING un
Function ${un}CheckRunning
  ${Do}
    System::Call 'kernel32::CreateMutexW(p 0, i 0, w "${MUTEX_NAME}") p .r1 ?e'
    Pop $2
    System::Call 'kernel32::CloseHandle(p r1)'
    ${If} $2 <> 183 ; ERROR_ALREADY_EXISTS = app is running
      ${ExitDo}
    ${EndIf}
    MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION "$(MSG_RUNNING)" IDRETRY +2
    Quit
  ${Loop}
FunctionEnd
!macroend
!insertmacro DEFINE_CHECK_RUNNING ""
!insertmacro DEFINE_CHECK_RUNNING "un."

Function .onInit
  SetRegView 64
  !insertmacro MUI_LANGDLL_DISPLAY
  ReadRegStr $0 HKLM "Software\${APP_NAME}" "InstallDir"
  ${If} $0 != ""
    StrCpy $INSTDIR $0
  ${EndIf}
  Call CheckRunning
FunctionEnd

; Always install into a folder named "ProcessX v2.0" (also when the user picks another drive or folder)
Function DirLeave
  StrCpy $0 $INSTDIR 1 -1
  ${If} $0 == "\"
    StrCpy $INSTDIR $INSTDIR -1
  ${EndIf}
  ${GetFileName} "$INSTDIR" $0
  ${If} $0 != "${APP_NAME}"
    StrCpy $INSTDIR "$INSTDIR\${APP_NAME}"
  ${EndIf}
FunctionEnd

Section "${APP_NAME}" SecMain
  SectionIn RO
  SetRegView 64
  SetShellVarContext all
  SetOutPath "$INSTDIR"
  File /r "${SRC_DIR}\*.*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  WriteRegStr HKLM "Software\${APP_NAME}" "InstallDir" "$INSTDIR"
  ${If} $LANGUAGE == ${LANG_VIETNAMESE}
    WriteRegStr HKLM "Software\${APP_NAME}" "LanguagePending" "vi"
  ${Else}
    WriteRegStr HKLM "Software\${APP_NAME}" "LanguagePending" "en"
  ${EndIf}
  WriteRegStr HKLM "${UNINST_KEY}" "DisplayName" "${APP_NAME}"
  WriteRegStr HKLM "${UNINST_KEY}" "DisplayVersion" "${APP_VER}"
  WriteRegStr HKLM "${UNINST_KEY}" "Publisher" "${PUBLISHER}"
  WriteRegStr HKLM "${UNINST_KEY}" "DisplayIcon" "$INSTDIR\${APP_EXE}"
  WriteRegStr HKLM "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "${UNINST_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegDWORD HKLM "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKLM "${UNINST_KEY}" "NoRepair" 1
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKLM "${UNINST_KEY}" "EstimatedSize" "$0"
SectionEnd

Section "$(SEC_START)" SecStart
  SetShellVarContext all
  SetOutPath "$INSTDIR"
  CreateShortcut "$SMPROGRAMS\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
SectionEnd

Section "$(SEC_DESKTOP)" SecDesktop
  SetShellVarContext all
  SetOutPath "$INSTDIR"
  CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
SectionEnd

Section "$(SEC_LAUNCH)" SecLaunch
  SetOutPath "$INSTDIR"
  Exec '"$INSTDIR\${APP_EXE}"'
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecMain}    "$(DESC_MAIN)"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecStart}   "$(DESC_START)"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} "$(DESC_DESKTOP)"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecLaunch}  "$(DESC_LAUNCH)"
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Function un.onInit
  SetRegView 64
  !insertmacro MUI_UNGETLANGUAGE
  Call un.CheckRunning
FunctionEnd

; Only removes files this installer created, never RMDir /r on $INSTDIR itself
; User data in %APPDATA%\ProcessX (settings.json, rules.json) is kept on purpose
Section "Uninstall"
  SetRegView 64
  SetShellVarContext all
  Delete "$DESKTOP\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}.lnk"
  nsExec::Exec 'schtasks /Delete /TN "${APP_NAME}" /F'
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "ProcessX"
  Delete "$INSTDIR\${APP_EXE}"
  RMDir /r "$INSTDIR\_internal"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKLM "${UNINST_KEY}"
  DeleteRegKey HKLM "Software\${APP_NAME}"
SectionEnd
