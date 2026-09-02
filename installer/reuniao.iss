; Inno Setup script for Nishizumi Reuniões (experimental meeting transcriber).
;
; Build the app first, then compile this script:
;   python build_reuniao.py --mode onedir --clean
;   iscc /DMyAppVersion=0.1.0 installer\reuniao.iss
;
; Installs per-user by default so updating never needs an admin prompt.
;
; Two folders are chosen by the user: the program itself (the standard
; destination page) and the folder the multi-gigabyte Whisper models download
; into. The second one is written to %APPDATA%\jp2subs\data_location.json,
; which is the pointer file the shared component store reads — so a model
; downloaded by either Nishizumi app is found by both.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

; VersionInfoVersion only accepts a numeric version, so strip any pre-release
; suffix: "0.1.0-rc1" becomes "0.1.0".
#if Pos("-", MyAppVersion) > 0
  #define MyNumericVersion Copy(MyAppVersion, 1, Pos("-", MyAppVersion) - 1)
#else
  #define MyNumericVersion MyAppVersion
#endif

#define MyAppName "Nishizumi Reunioes"
#define MyAppDisplayName "Nishizumi Reunioes (experimental)"
#define MyAppShortName "reuniao"
#define MyAppPublisher "nishizumi-maho"
#define MyAppURL "https://github.com/nishizumi-maho/Nishizumi-Translations"
#define MyAppExeName "NishizumiReunioes.exe"
#define MyBuildDir "..\dist\NishizumiReunioes"

[Setup]
; A GUID of its own: this app installs and uninstalls independently of the
; subtitle app, and the two can sit side by side.
AppId={{2D5E7B41-9C38-4A6F-B0E2-7F41A9C6D083}
AppName={#MyAppDisplayName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppDisplayName} {#MyAppVersion}
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
OutputBaseFilename=Nishizumi-Reunioes-Setup-{#MyAppVersion}
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppDisplayName}
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
AppMutex=NishizumiReunioesSingleInstance

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar um atalho na &area de trabalho"; GroupDescription: "Atalhos:"; Languages: brazilianportuguese
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Languages: english

[Files]
Source: "{#MyBuildDir}\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#MyBuildDir}\*"; DestDir: "{app}"; Excludes: "{#MyAppExeName}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppDisplayName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppDisplayName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir o {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; PyInstaller leaves __pycache__ folders behind on first run.
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
// The program folder comes from the standard destination page; this extra page
// picks where the downloaded models and FFmpeg live, so a small system drive
// never has to hold several gigabytes of speech models.
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

// Reads the folder the apps are using today. Both Nishizumi apps write this
// same file when the folder is changed from inside them, so an unattended
// update carries that choice forward instead of resetting it.
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
    'Pasta dos modelos',
    'Onde guardar os modelos de voz e o FFmpeg?',
    'O aplicativo baixa alguns gigabytes de modelos na primeira vez.' + #13#10 +
    'Escolha um disco com espaco - nao precisa ser o mesmo do programa.' + #13#10 + #13#10 +
    'Clique em Avancar para continuar.',
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
      MsgBox('Escolha uma pasta para os modelos.', mbError, MB_OK);
      Result := False;
      Exit;
    end;
    // Creating it now surfaces a wrong drive letter here rather than halfway
    // through a 1.5 GB download.
    if not ForceDirectories(Chosen) then
    begin
      MsgBox('Nao foi possivel criar:' + #13#10 + Chosen + #13#10 + #13#10 +
             'Escolha outra pasta.', mbError, MB_OK);
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
    '{' + #13#10 + '  "data_dir": "' + JsonEscape(Chosen) + '"' + #13#10 + '}' + #13#10,
    False);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    SaveDataLocation();
end;
