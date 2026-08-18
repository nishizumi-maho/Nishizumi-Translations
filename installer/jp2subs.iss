; Inno Setup script for Nishizumi Translations.
;
; Build the app first, then compile this script:
;   python build_executable.py --mode onedir --clean
;   iscc /DMyAppVersion=2.1.0 installer\jp2subs.iss
;
; Installs per-user by default so updating never needs an admin prompt, which
; is what lets the in-app updater run the installer unattended.
;
; Two folders are chosen by the user: the program itself (the standard
; destination page) and the folder the multi-gigabyte Whisper models download
; into. The second one is written to %APPDATA%\jp2subs\data_location.json,
; which is the same pointer file the app writes when the folder is changed from
; the Settings page.

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
// The program folder comes from the standard destination page; this extra page
// picks where the downloaded models, FFmpeg and GPU libraries live, so a small
// system drive never has to hold several gigabytes of speech models.
var
  DataDirPage: TInputDirWizardPage;

function DefaultDataDir(): String;
begin
  Result := ExpandConstant('{localappdata}\jp2subs');
end;

function PointerFile(): String;
begin
  Result := ExpandConstant('{userappdata}\jp2subs\data_location.json');
end;

// Reads the folder the app is using today. The app writes this same file when
// the location is changed from its Settings page, so an unattended update
// carries that choice forward instead of resetting it.
function ConfiguredDataDir(): String;
var
  Lines: TArrayOfString;
  I, Position: Integer;
  Line, Value: String;
begin
  Result := DefaultDataDir();
  if not LoadStringsFromFile(PointerFile(), Lines) then
    Exit;
  for I := 0 to GetArrayLength(Lines) - 1 do
  begin
    Line := Lines[I];
    Position := Pos('"data_dir"', Line);
    if Position = 0 then
      Continue;
    Line := Copy(Line, Position + Length('"data_dir"'), Length(Line));
    Position := Pos('"', Line);
    if Position = 0 then
      Continue;
    Line := Copy(Line, Position + 1, Length(Line));
    Position := Pos('"', Line);
    if Position = 0 then
      Continue;
    Value := Trim(Copy(Line, 1, Position - 1));
    StringChangeEx(Value, '\\', '\', True);
    if Value <> '' then
      Result := Value;
    Exit;
  end;
end;

procedure InitializeWizard;
begin
  DataDirPage := CreateInputDirPage(wpSelectDir,
    'Select Model Folder',
    'Where should the speech models and FFmpeg be stored?',
    'Nishizumi Translations downloads several gigabytes of Whisper models on first run.' + #13#10 +
    'Pick any drive with room to spare - it does not have to be the drive the program is installed on.' + #13#10 + #13#10 +
    'Click Next to continue.',
    False, '');
  DataDirPage.Add('');
  DataDirPage.Values[0] := GetPreviousData('DataDir', ConfiguredDataDir());
end;

procedure RegisterPreviousData(PreviousDataKey: Integer);
begin
  SetPreviousData(PreviousDataKey, 'DataDir', DataDirPage.Values[0]);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Chosen: String;
begin
  Result := True;
  if (DataDirPage <> nil) and (CurPageID = DataDirPage.ID) then
  begin
    Chosen := Trim(DataDirPage.Values[0]);
    if Chosen = '' then
    begin
      MsgBox('Choose a folder for the models and tools.', mbError, MB_OK);
      Result := False;
      Exit;
    end;
    // Creating it now surfaces a wrong drive letter here rather than halfway
    // through a 3 GB download.
    if not ForceDirectories(Chosen) then
    begin
      MsgBox('Setup could not create:' + #13#10 + Chosen + #13#10 + #13#10 +
             'Choose another folder.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

function JsonEscape(const Value: String): String;
begin
  Result := Value;
  StringChangeEx(Result, '\', '\\', True);
  StringChangeEx(Result, '"', '\"', True);
end;

procedure SaveDataLocation();
var
  Chosen: String;
begin
  Chosen := Trim(DataDirPage.Values[0]);
  // No pointer file means "use the standard per-user folder", so choosing the
  // default is recorded by removing any pointer an earlier run left behind.
  if CompareText(RemoveBackslashUnlessRoot(Chosen), RemoveBackslashUnlessRoot(DefaultDataDir())) = 0 then
  begin
    DeleteFile(PointerFile());
    Exit;
  end;
  ForceDirectories(ExpandConstant('{userappdata}\jp2subs'));
  SaveStringToFile(PointerFile(),
    '{' + #13#10 + '  "data_dir": "' + JsonEscape(Chosen) + '"' + #13#10 + '}' + #13#10, False);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    SaveDataLocation();
end;

// Downloaded models and ffmpeg live outside {app} - wherever the user put them
// - so offer to remove them too, since they can be several gigabytes.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ConfiguredDataDir();
    if DirExists(DataDir) then
    begin
      if MsgBox('Also delete the downloaded Whisper models and FFmpeg?' + #13#10 + #13#10 +
                DataDir + #13#10 + #13#10 +
                'Choose No to keep them for a future install.',
                mbConfirmation, MB_YESNO) = IDYES then
      begin
        DelTree(DataDir, True, True, True);
        DeleteFile(PointerFile());
      end;
    end;
  end;
end;
