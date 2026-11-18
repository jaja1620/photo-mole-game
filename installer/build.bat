@echo off
rem build.bat —— 双击或命令行运行，等价于 build.ps1
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1" %*
if errorlevel 1 (
  echo.
  echo [FAILED] 构建失败，请查看上方日志。
  pause
  exit /b 1
)
echo.
echo [OK] 构建完成，产物在 dist\photo-mole-game-installer.exe
pause
