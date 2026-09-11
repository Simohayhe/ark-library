; ARK ライブラリのインストーラ (Inno Setup 6)
;
; tools/build.py から呼ばれる。直接コンパイルするなら:
;   ISCC.exe /DMyVersion=1.0.0 installer\ArkLibrary.iss
;
; 方針:
;   * ユーザー専用インストール (%LOCALAPPDATA%\Programs) にして UAC を出さない。
;     こうしておくと、アプリ内の「更新を確認」も管理者権限なしで動く。
;   * AppId を固定しているので、入っていれば自動で上書き更新になる。
;   * ライブラリ (個体データ) は %LOCALAPPDATA%\ArkLibrary にあるので、
;     アンインストールしても消さない (消したい人向けの選択肢だけ出す)。

#ifndef MyVersion
  #define MyVersion "0.0.0"
#endif

#define MyName "ARK ライブラリ"
#define MyNameEn "ArkLibrary"
#define MyPublisher "Simohaya"
#define MyUrl "https://github.com/Simohayhe/ark-library"
#define MyExe "ArkLibrary.exe"

[Setup]
; この GUID は変えないこと。変えると別のソフト扱いになって上書きされなくなる。
AppId={{BE063DB4-B88D-492A-B865-DDD4CB01B206}
AppName={#MyName}
AppVersion={#MyVersion}
AppVerName={#MyName} {#MyVersion}
VersionInfoVersion={#MyVersion}
AppPublisher={#MyPublisher}
AppPublisherURL={#MyUrl}
AppSupportURL={#MyUrl}/issues
AppUpdatesURL={#MyUrl}/releases

; ユーザー専用インストール (管理者権限を要求しない)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={localappdata}\Programs\{#MyNameEn}
DefaultGroupName={#MyName}
DisableProgramGroupPage=yes
DisableDirPage=no
AllowNoIcons=yes

OutputDir=..\dist
OutputBaseFilename={#MyNameEn}-{#MyVersion}-setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyExe}
UninstallDisplayName={#MyName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; 動いていたら閉じてもらう (更新インストールで失敗しないように)
CloseApplications=yes
RestartApplications=no
CloseApplicationsFilter=*.exe

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "desktopicon"; Description: "デスクトップにショートカットを作る"; GroupDescription: "そのほか:"
Name: "startup"; Description: "Windows起動時に自動で開く (エクスポートを見張るので、入れておくと取りこぼさない)"; GroupDescription: "そのほか:"; Flags: unchecked

[Files]
; onedir 版の中身をまるごと入れる
Source: "..\dist\{#MyNameEn}-dir\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyName}"; Filename: "{app}\{#MyExe}"
Name: "{group}\{#MyName} をアンインストール"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyName}"; Filename: "{app}\{#MyExe}"; Tasks: desktopicon
Name: "{userstartup}\{#MyName}"; Filename: "{app}\{#MyExe}"; Tasks: startup

[Run]
Filename: "{app}\{#MyExe}"; Description: "{#MyName} を開く"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; PyInstaller の展開先など、インストール後に増えたものも片づける
Type: filesandordirs; Name: "{app}\_internal"

[Code]
// ライブラリ (個体データ・サーバー設定・音) は %LOCALAPPDATA%\ArkLibrary にある。
// アンインストール時に消すか聞く。
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\ArkLibrary');
    // 黙って消すのは怖いので、静かなアンインストールのときは必ず残す。
    // (/SUPPRESSMSGBOXES は [Code] の MsgBox を抑えてくれないので自分で見る)
    if DirExists(DataDir) and (not UninstallSilent) then
    begin
      if MsgBox('取り込んだ生物のライブラリも消しますか？' + #13#10 +
                '「いいえ」を選ぶと、入れ直したときにそのまま続きから使えます。',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
