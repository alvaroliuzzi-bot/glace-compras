@echo off
cd /d "%~dp0"
where pyw >nul 2>nul && (start "" pyw -3 "%~dp0selftest.pyw" & exit /b 0)
where pythonw >nul 2>nul && (start "" pythonw "%~dp0selftest.pyw" & exit /b 0)
python "%~dp0selftest.pyw"
