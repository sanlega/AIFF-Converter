@echo off
python "%~dp0audio_converter.py"
if errorlevel 1 (
    echo.
    echo Ocurrio un error. Revisa el mensaje de arriba.
    pause
)
