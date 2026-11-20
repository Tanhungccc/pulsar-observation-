@echo off
REM ============================================================
REM  build_exe.bat — Dong goi PulsarObs.exe (mot click de mo)
REM  Chay lai sau khi sua code:  build_exe.bat
REM  San pham: PulsarObs.exe  (~100 MB, tu chua Python + numpy +
REM            matplotlib + tkinter + astropy, may dich khong can cai gi)
REM ============================================================
cd /d "%~dp0"

echo [1/4] Kiem tra PyInstaller...
python -m pip install --quiet pyinstaller
if errorlevel 1 ( echo FAIL: khong cai duoc pyinstaller & exit /b 1 )

echo [2/4] Dong goi (mat ~2-3 phut)...
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name PulsarObs ^
    --icon assets\icon.ico ^
    --add-data "assets\icon.ico;assets" ^
    --add-data "assets\icon.png;assets" ^
    --paths code ^
    --hidden-import=rtlsdr ^
    --hidden-import=psr_iq ^
    --hidden-import=psr_fits ^
    --hidden-import=psr_swcomp ^
    --hidden-import=astropy.io.fits ^
    --hidden-import=astropy.io.fits.hdu.image ^
    --hidden-import=astropy.time ^
    --hidden-import=astropy.coordinates ^
    --hidden-import=matplotlib.image ^
    --hidden-import=matplotlib.backends.backend_tkagg ^
    --hidden-import=wave ^
    --exclude-module=scipy ^
    --exclude-module=pandas ^
    --exclude-module=PyQt5 ^
    --exclude-module=PySide2 ^
    code\gui_app.py
if errorlevel 1 ( echo FAIL: build loi & exit /b 1 )

echo [3/4] Copy san pham ra thu muc goc...
copy /Y dist\PulsarObs.exe PulsarObs.exe >nul
if errorlevel 1 ( echo FAIL: khong copy duoc exe & exit /b 1 )

echo [4/4] Kiem chung ban dong goi...
PulsarObs.exe --selfcheck
if errorlevel 1 ( echo FAIL: selfcheck & exit /b 1 )

echo.
echo ================= DONE =================
echo   PulsarObs.exe                double-click de mo (co icon rieng)
echo   PulsarObs.exe --selfcheck    kiem tra ban dong goi
echo   (ket qua: selfcheck_report.txt)
echo =========================================
