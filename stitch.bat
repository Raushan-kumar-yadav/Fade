@echo off
echo Stitching Echo parts together...
echo.
if not exist "Echo-win-x64.zip.001" (
    echo Error: Missing Echo-win-x64.zip.001
    pause
    exit /b
)
copy /b Echo-win-x64.zip.001 + Echo-win-x64.zip.002 + Echo-win-x64.zip.003 Echo-win-x64.zip
echo.
echo Success! You can now extract the large Echo-win-x64.zip file.
pause
