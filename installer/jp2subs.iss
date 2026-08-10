; Inno Setup script for Nishizumi Translations.
;
; Build the app first, then compile this script:
;   python build_executable.py --mode onedir --clean
;   iscc /DMyAppVersion=2.1.0 installer\jp2subs.iss
;
; Installs per-user by default so updating never needs an admin prompt, which
; is what lets the in-app updater run the installer unattended.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

; VersionInfoVersion only accepts a numeric version, so strip any pre-release
; suffix: "2.1.0-rc1" becomes "2.1.0".
#if Pos("-", MyAppVersion) > 0
  #define MyNumericVersion Copy(MyAppVersion, 1, Pos("-", MyAppVersion) - 1)
#else
  #define MyNumericVersion MyAppVersion
#endif

#define MyAppName "Nishizumi Translations"
#define MyAppShortName "jp2subs"
#define MyAppPublisher "nishizumi-maho"
#define MyAppURL "https://github.com/nishizumi-maho/Nishizumi-Translations"
#define MyAppExeName "NishizumiTranslations.exe"
#define MyBuildDir "..\dist\NishizumiTranslations"

[Setup]
AppId={{8F3C2A64-6D51-4E7B-9C0A-2E1B4D7F5A93}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
VersionInfoVersion={#MyNumericVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir=..\dist\installer
OutputBaseFilename=Nishizumi-Translations-Setup-{#MyAppVersion}
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
; Shut the app down cleanly when updating over a running copy.
CloseApplications=yes
RestartApplications=no
AppMutex=NishizumiTranslationsSingleInstance

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "{#MyBuildDir}\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#MyBuildDir}\*"; DestDir: "{app}"; Excludes: "{#MyAppExeName}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; PyInstaller leaves __pycache__ folders behind on first run.
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
// Downloaded models and ffmpeg live outside {app}; offer to remove them too,
// since they can be several gigabytes.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\jp2subs');
    if DirExists(DataDir) then
    begin
      if MsgBox('Also delete the downloaded Whisper models and FFmpeg?' + #13#10 + #13#10 +
                DataDir + #13#10 + #13#10 +
                'Choose No to keep them for a future install.',
                mbConfirmation, MB_YESNO) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
