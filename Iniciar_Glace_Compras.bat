@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Glace Compras
set "PYC="
where py >nul 2>nul && set "PYC=py -3"
if not defined PYC where python >nul 2>nul && set "PYC=python"
if not defined PYC goto nopy

%PYC% -c "import PyQt6.QtWebEngineWidgets" >nul 2>nul
if errorlevel 1 (
  echo.
  echo  Primera vez: se instalan los componentes del programa.
  echo  Son unos 150 MB y se hace una sola vez. Un momento, por favor...
  echo.
  %PYC% -m pip install --user --upgrade PyQt6 PyQt6-WebEngine
  if errorlevel 1 goto piperr
)

if not exist "%~dp0.acceso_ok" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Glace Compras.lnk'); $s.TargetPath='%~dp0Iniciar_Glace_Compras.bat'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%~dp0Glace_Compras.ico'; $s.WindowStyle=7; $s.Save()" >nul 2>nul
  echo ok> "%~dp0.acceso_ok"
)

where pyw >nul 2>nul && (start "" pyw -3 "%~dp0Glace_Compras_App.pyw" & exit /b 0)
where pythonw >nul 2>nul && (start "" pythonw "%~dp0Glace_Compras_App.pyw" & exit /b 0)
%PYC% "%~dp0Glace_Compras_App.pyw"
exit /b 0

:nopy
echo.
echo  No encontre Python en esta computadora.
echo  Se abre la pagina de descarga. Instalalo (marca "Add python.exe to PATH")
echo  y despues volve a abrir este archivo.
echo.
start "" https://www.python.org/downloads/
pause
exit /b 1

:piperr
echo.
echo  No se pudieron instalar los componentes. Revisa la conexion a internet
echo  y volve a abrir este archivo. Si sigue igual, saca una foto de este mensaje.
echo.
pause
exit /b 1
