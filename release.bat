@echo off
rem Sobiraet installer: installer\Output\TF2ModStudio-Setup.exe
rem Argumenty peredayutsya v skript: release.bat -Version 1.0.4 -SkipDeps
powershell.exe -ExecutionPolicy Bypass -File "%~dp0build-release.ps1" %*
if errorlevel 1 pause
