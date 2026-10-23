Section "un.$(remove_files)" ;"un.Remove files"
  SectionIn RO

; Remove files and uninstaller
  Delete "$INSTDIR\gtkbittorrent.exe"
  Delete "$INSTDIR\gtkbittorrent.pdb"
  Delete "$INSTDIR\gtkbittorrent-import.exe"
  Delete "$INSTDIR\qt.conf"
  Delete "$INSTDIR\uninst.exe"

  ; Remove directories used
  RMDir /r "$INSTDIR\translations"
  RMDir "$INSTDIR"
SectionEnd

Section "un.$(remove_shortcuts)" ;"un.Remove shortcuts"
  SectionIn RO
; Remove shortcuts, if any
  RMDir /r "$SMPROGRAMS\gtkBittorrent"
  Delete "$DESKTOP\gtkBittorrent.lnk"
SectionEnd

Section "un.$(remove_registry)" ;"un.Remove registry keys"
  SectionIn RO
  ; Remove registry keys
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\gtkBittorrent"
  DeleteRegKey HKLM "Software\gtkBittorrent"
  ; Remove ProgIDs
  DeleteRegKey HKLM "Software\Classes\gtkBittorrent.File.Torrent"
  DeleteRegKey HKLM "Software\Classes\gtkBittorrent.Url.Magnet"
  System::Call 'shell32::SHChangeNotify(i ${SHCNE_ASSOCCHANGED}, i ${SHCNF_IDLIST}, p 0, p 0)'
SectionEnd

Section "un.$(remove_firewall)" ;

  DetailPrint $(remove_firewallinfo)
  nsisFirewallW::RemoveAuthorizedApplication "$INSTDIR\gtkbittorrent.exe"

SectionEnd

Section /o "un.$(remove_conf)" ;"un.Remove configuration files"

  !insertmacro UAC_AsUser_Call Function un.remove_conf_user ${UAC_SYNCREGISTERS}|${UAC_SYNCOUTDIR}|${UAC_SYNCINSTDIR}

SectionEnd

Function un.remove_conf_user

  System::Call 'shell32::SHGetKnownFolderPath(g "${FOLDERID_RoamingAppData}", i 0, p 0, *w . r1) i . r0'
  RMDir /r "$1\gtkBittorrent"
  System::Call 'ole32::CoTaskMemFree(p r1)'

FunctionEnd

Section /o "un.$(remove_cache)"

  !insertmacro UAC_AsUser_Call Function un.remove_cache_user ${UAC_SYNCREGISTERS}|${UAC_SYNCOUTDIR}|${UAC_SYNCINSTDIR}

SectionEnd

Function un.remove_cache_user

  System::Call 'shell32::SHGetKnownFolderPath(g "${FOLDERID_LocalAppData}", i 0, p 0, *w . r1) i . r0'
  RMDir /r "$1\gtkBittorrent"
  System::Call 'ole32::CoTaskMemFree(p r1)'

FunctionEnd

;--------------------------------
;Uninstaller Functions

Function un.onInit

  !insertmacro Init "uninstaller"
  !insertmacro MUI_UNGETLANGUAGE

FunctionEnd

Function un.check_instance

  check:
  FindProcDLL::FindProc "gtkbittorrent.exe"
  StrCmp $R0 "1" 0 notfound
  MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION $(uninst_warning) /SD IDCANCEL IDRETRY check IDCANCEL canceled

  canceled:
  SetErrorLevel 15618 # WinError.h: `ERROR_PACKAGES_IN_USE`
  Abort

  notfound:

FunctionEnd

Function un.onUninstSuccess
  SetErrorLevel 0
FunctionEnd
