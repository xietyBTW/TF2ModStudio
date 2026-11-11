; Установщик Tf2SkinGenerator: ОДИН файл, приложение внутри.
;
; Чем отличается от прежнего Tf2SkinGenerator.iss: тот был загрузчиком —
; сам весил 2 МБ, а во время установки качал zip с GitHub. Значит:
;   * в релизе приходилось держать два файла и не путать их местами;
;   * установка требовала сети и умела сорваться на середине;
;   * контрольная сумма проверяла загрузчик, а не то, что реально ставится.
; Здесь приложение лежит ВНУТРИ установщика: один файл в релизе, установка
; без сети, а SHA-256 накрывает всё содержимое разом.
;
; Собирается не руками, а через build-release.ps1 — он передаёт сюда версию и
; папку с готовой сборкой:
;   ISCC.exe /DAppVersion=1.0.4 /DPayloadDir=<...\dist\Tf2SkinGenerator> ...

; AppName - внутреннее имя: мьютекс, папка установки и папка данных
; (src/shared/paths.py). Смена отрезала бы установленные копии от их данных.
; Человек видит AppDisplayName: ярлыки, мастер, «Программы и компоненты»
#define AppName "Tf2SkinGenerator"
#define AppDisplayName "TF2 Mod Studio"
#define AppPublisher "xietyBTW"
#define AppURL "https://github.com/xietyBTW/TF2ModStudio"
#define AppExe "Tf2SkinGenerator.exe"
; Имя файла установщика в релизе. По нему его находит обновление из
; приложения (ASSET_NAME в src/services/update_checker.py)
#ifndef ReleaseName
  #define ReleaseName "TF2ModStudio"
#endif
; Загрузчик WebView2 от Microsoft (около 2 МБ): скачивается во время установки
; и только если человек оставил галку, сам в установщике не лежит
#define WebView2Url "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
#define WebView2Setup "MicrosoftEdgeWebview2Setup.exe"

; Версию и папку со сборкой задаёт build-release.ps1. Значения ниже —
; только чтобы файл открывался в редакторе Inno сам по себе.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef PayloadDir
  #define PayloadDir "..\dist\Tf2SkinGenerator"
#endif

[Setup]
; AppId менять НЕЛЬЗЯ: по нему Windows понимает, что новая версия — это
; обновление уже установленной, а не вторая программа рядом.
AppId={{A1B2C3D4-E5F6-4A5B-8C9D-0E1F2A3B4C5D}
AppName={#AppDisplayName}
AppVersion={#AppVersion}
AppVerName={#AppDisplayName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppDisplayName}
AllowNoIcons=yes
; Без UAC: {autopf} у непривилегированного запуска — это
; %LOCALAPPDATA%\Programs, куда приложение вправе писать. Обновление изнутри
; приложения тоже пройдёт без запроса прав.
PrivilegesRequired=lowest
; Портативный режим: тот же установщик, запущенный приложением из портативной
; копии (zip из релиза) как
;   Setup.exe /PORTABLE=1 /DIR="<её папка>" /SILENT /NOICONS
; подменяет файлы на месте и не оставляет следов — ни деинсталлятора, ни
; записи в «Программах и компонентах». Так портативная версия обновляется
; той же кнопкой, что и установленная (src/services/update_checker.py).
Uninstallable=not IsPortable
CreateUninstallRegKey=not IsPortable
UsePreviousAppDir=yes
UsePreviousGroup=yes
; Приложение создаёт мьютекс с этим именем (src/shared/single_instance.py).
; Без него установка поверх работающей программы била бы в занятые файлы.
AppMutex={#AppName}
; Штатный способ закрыть приложение перед заменой файлов и поднять после.
CloseApplications=yes
RestartApplications=yes
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppDisplayName} {#AppVersion}
OutputDir=Output
OutputBaseFilename={#ReleaseName}-Setup
SetupIconFile=assets\icon.ico
; ultra64 против ultra: словарь больше, распаковка требует больше памяти, но
; питоновские DLL и numpy жмутся заметно лучше. Solid — потому что файл один
; и распаковывается целиком.
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=no
DisableWelcomePage=no
; Сборка 64-битная (PyInstaller берёт разрядность питона).
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

; Свои строки установщика — на обоих языках. Стандартные ({cm:CreateDesktopIcon}
; и прочие) Inno берёт из .isl сам, а всё, что написано здесь руками, иначе
; показывается одним языком при любом выборе.
[CustomMessages]
english.RemoveDataGroup=When uninstalling:
english.RemoveData=Also delete my works, mods and settings
russian.RemoveDataGroup=При удалении программы:
russian.RemoveData=Удалить и мои работы, моды и настройки
english.DirNotWritable=You can't write to this folder without administrator rights:%n%n%1%n%nChoose a folder in your user profile or on another drive, for example D:\Games\Tf2SkinGenerator.
russian.DirNotWritable=В эту папку нельзя записывать без прав администратора:%n%n%1%n%nВыберите папку в своём профиле или на другом диске, например D:\Games\Tf2SkinGenerator.
english.WebView2Group=Missing component:
english.WebView2Task=Download and install Microsoft Edge WebView2 from Microsoft (needed for the app window)
english.WebView2Installing=Installing Microsoft Edge WebView2...
english.WebView2Failed=Couldn't download Microsoft Edge WebView2:%n%n%1%n%nInstallation will continue. Until WebView2 is installed, the app opens in your browser.
russian.WebView2Group=Не хватает компонента:
russian.WebView2Task=Скачать и установить Microsoft Edge WebView2 с сайта Microsoft (нужен для окна приложения)
russian.WebView2Installing=Устанавливается Microsoft Edge WebView2...
russian.WebView2Failed=Не удалось скачать Microsoft Edge WebView2:%n%n%1%n%nУстановка продолжится. Пока WebView2 не установлен, приложение будет открываться в браузере.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
; Работы, моды, настройки и кэш лежат в %LOCALAPPDATA%\Tf2SkinGenerator, а не
; в папке установки (см. src/shared/paths.py). Обычное удаление их не трогает,
; эта галка — способ снести всё вместе с программой.
Name: "removedata"; Description: "{cm:RemoveData}"; GroupDescription: "{cm:RemoveDataGroup}"; Flags: unchecked
; Видна, только если WebView2 нет: тогда окно приложения рисовать нечем.
; Решает человек, тихо ничего не скачиваем
Name: "webview2"; Description: "{cm:WebView2Task}"; GroupDescription: "{cm:WebView2Group}"; Check: OfferWebView2

[InstallDelete]
; ДО распаковки убираем прошлую версию. Inno перезаписывает свои файлы, но не
; удаляет те, которых в новой сборке уже нет: в _internal тогда смешиваются
; .pyd и .dll от двух сборок PyInstaller, и первое же расхождение версий
; питона или пакета даёт ImportError либо падение в нативном коде.
; Данные человека здесь не лежат — они в %LOCALAPPDATA%.
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\tools"
; Ярлыки под прежним названием: новые создаются под AppDisplayName, а
; старые Inno сам не убирает, и значков стало бы два. Портативная копия
; ярлыков не заводит, и чужие (установленной) ей трогать нельзя
Type: files; Name: "{group}\{#AppName}.lnk"; Check: not IsPortable
Type: files; Name: "{autodesktop}\{#AppName}.lnk"; Check: not IsPortable

[Files]
; Вся собранная папка целиком. PayloadDir приходит от build-release.ps1.
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppDisplayName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{cm:UninstallProgram,{#AppDisplayName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppDisplayName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
; Без прав администратора загрузчик Microsoft ставит WebView2 только для
; этого пользователя, ему этого хватает
Filename: "{tmp}\{#WebView2Setup}"; Parameters: "/silent /install"; StatusMsg: "{cm:WebView2Installing}"; Tasks: webview2; Check: WebView2Downloaded; Flags: waituntilterminated
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppDisplayName}}"; Flags: nowait postinstall skipifsilent
; Обновление из приложения идёт тихо, и строка выше его пропускает: программа
; закрывалась, обновлялась и не поднималась. RestartApplications тут не
; помогает — он перезапускает только то, что закрыл сам, а приложение к
; приходу установщика уже вышло. Поэтому поднимаем явно. Решает НОВЫЙ
; установщик, так что это работает и при обновлении с 1.0.5.
Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Flags: nowait skipifnotsilent; Check: StartedByUpdater

[UninstallDelete]
; Файлы из [Files] деинсталлятор снимает сам — здесь только то, чего он не
; знает: что программа создала уже во время работы.
Type: files; Name: "{app}\tf2sg.log"
Type: files; Name: "{app}\tf2sg.log.*"
Type: files; Name: "{app}\tf2sg_crash.log"
; Данные прежних версий, до переезда в %LOCALAPPDATA% (см. migrate_legacy_data).
Type: filesandordirs; Name: "{app}\config"; Tasks: removedata
Type: filesandordirs; Name: "{app}\export"; Tasks: removedata
Type: filesandordirs; Name: "{app}\work"; Tasks: removedata
Type: filesandordirs; Name: "{app}\mods"; Tasks: removedata
Type: filesandordirs; Name: "{app}\cache"; Tasks: removedata
; Работы, моды, настройки и кэш нынешних версий.
Type: filesandordirs; Name: "{localappdata}\{#AppName}"; Tasks: removedata
; Кэш разобранных моделей прежних версий, до переезда в папку данных (см.
; migrate_legacy_data). Это только кэш, убираем всегда
Type: filesandordirs; Name: "{%USERPROFILE}\.tf2skingen_cache"
; Папку убираем, только если она пуста: человек мог поставить программу в уже
; существующую папку, и её содержимое не наше.
Type: dirifempty; Name: "{app}"

[Code]
function IsPortable: Boolean;
begin
  Result := ExpandConstant('{param:PORTABLE|0}') = '1';
end;

// Запуск из приложения по кнопке «Обновить»: оно всегда передаёт
// /RESTARTAPPLICATIONS (src/services/update_checker.py, _SETUP_FLAGS), и
// версия 1.0.5 тоже. Ручной тихий запуск без него программу не поднимет.
function StartedByUpdater: Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), '/RESTARTAPPLICATIONS') = 0 then
      Result := True;
end;

// Можно ли писать в папку. Установщик идёт без прав администратора, и папка
// вроде C:\Program Files падала «Отказано в доступе» уже посреди копирования.
// Проверяем ближайшую существующую папку пробным файлом, ничего не создавая.
function CanWriteTo(Dir: String): Boolean;
var
  Probe: String;
begin
  while (Dir <> '') and not DirExists(Dir) do
    Dir := ExtractFileDir(Dir);
  Probe := AddBackslash(Dir) + 'tf2sg_write_test.tmp';
  Result := SaveStringToFile(Probe, '', False);
  if Result then
    DeleteFile(Probe);
end;

const
  WebView2Key = 'Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

var
  DownloadPage: TDownloadWizardPage;
  WebView2Ready: Boolean;

// Признак WebView2 по Microsoft: значение pv на машину или на пользователя,
// пустое или 0.0.0.0 значит «не установлен»
function HasWebView2Version(Root: Integer; Key: String): Boolean;
var
  Version: String;
begin
  Result := RegQueryStringValue(Root, Key, 'pv', Version)
            and (Version <> '') and (Version <> '0.0.0.0');
end;

function WebView2Installed: Boolean;
begin
  Result := HasWebView2Version(HKLM32, 'SOFTWARE\' + WebView2Key)
            or HasWebView2Version(HKCU, 'Software\' + WebView2Key);
end;

// Тихий запуск (обновление из приложения, портативная копия) ничего не
// скачивает: спросить там некого
function OfferWebView2: Boolean;
begin
  Result := not WizardSilent and not IsPortable and not WebView2Installed;
end;

function WebView2Downloaded: Boolean;
begin
  Result := WebView2Ready;
end;

procedure InitializeWizard;
begin
  DownloadPage := CreateDownloadPage(SetupMessage(msgWizardPreparing),
    SetupMessage(msgPreparingDesc), nil);
end;

// Без сети или при обрыве установка идёт дальше: приложение и так откроется
// в браузере и само подскажет, где взять WebView2
procedure DownloadWebView2;
begin
  DownloadPage.Clear;
  DownloadPage.Add('{#WebView2Url}', '{#WebView2Setup}', '');
  DownloadPage.Show;
  try
    try
      DownloadPage.Download;
      WebView2Ready := True;
    except
      if not DownloadPage.AbortedByUser then
        MsgBox(FmtMessage(CustomMessage('WebView2Failed'), [GetExceptionMessage]),
          mbInformation, MB_OK);
    end;
  finally
    DownloadPage.Hide;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  // Тихое обновление ставит в прежнюю папку, туда писать можно; спрашивать
  // там некого.
  if (CurPageID = wpSelectDir) and not WizardSilent and not CanWriteTo(WizardDirValue) then
  begin
    MsgBox(FmtMessage(CustomMessage('DirNotWritable'), [WizardDirValue]), mbError, MB_OK);
    Result := False;
  end;
  if (CurPageID = wpReady) and WizardIsTaskSelected('webview2') then
    DownloadWebView2;
end;
