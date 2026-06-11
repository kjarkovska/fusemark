; setup.iss — Inno Setup script for ObsiNote (Phase P11 packaging).
; Build: open in Inno Setup Compiler (6.3+) and Build, or: iscc installer\setup.iss
; Output: installer\Output\ObsiNoteSetup.exe
;
; Prerequisites: run `pyinstaller installer/build.spec` first (produces dist\ObsiNote\),
; and place ffmpeg.exe + ffprobe.exe in installer\ffmpeg\ (see ffmpeg\README.md).
;
; MyAppVersion must match app/version.py at release time (see installer/README.md).

#define MyAppName "ObsiNote"
#define MyAppVersion "0.9.3"
#define MyAppExeName "ObsiNote.exe"

[Setup]
; Keep this GUID stable across releases so upgrades replace the prior install.
AppId={{B1E7B0A2-9C3D-4F8E-A6D2-7E5F1C2A3B4D}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={commonpf64}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
LicenseFile=..\LICENSE
OutputDir=Output
OutputBaseFilename=ObsiNoteSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; 64-bit install into Program Files (not %APPDATA% — that is user data only).
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Writing to Program Files needs elevation; the HKCU autostart key is written by
; the app itself at runtime, so it needs no installer privileges.
PrivilegesRequired=admin

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; PyInstaller onedir output.
Source: "..\dist\{#MyAppName}\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
; ffmpeg next to the exe — ffmpeg_exe() (sys.frozen branch) looks for it here.
Source: "ffmpeg\ffmpeg.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "ffmpeg\ffprobe.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; The app writes its own HKCU\...\Run\ObsiNote autostart value at runtime.
; dontcreatekey: do not write it during install; uninsdeletevalue: remove it on
; uninstall so Windows does not try to launch a deleted exe at next login.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "ObsiNote"; Flags: dontcreatekey uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[Code]
function WebView2Installed: Boolean;
var
  Version: String;
begin
  Result :=
    RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) or
    RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) or
    RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version);
  if Result and (Version = '0.0.0.0') then
    Result := False;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ErrorCode: Integer;
begin
  // WebView2 Runtime ships with Windows 11 but may be absent on Windows 10.
  // Warn and offer the download — never hard-fail the install.
  if (CurStep = ssPostInstall) and (not WebView2Installed) then
  begin
    if MsgBox('Microsoft Edge WebView2 Runtime was not found. ObsiNote needs it to '
      + 'display its window. Open the free download page now?',
      mbConfirmation, MB_YESNO) = IDYES then
      ShellExec('open', 'https://developer.microsoft.com/microsoft-edge/webview2/',
        '', '', SW_SHOW, ewNoWait, ErrorCode);
  end;
end;
