@echo off
echo ============================================
echo  Fabric MCP Server - Instalacion
echo ============================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python no esta instalado o no esta en el PATH.
    echo Descargalo de https://www.python.org/downloads/
    pause
    exit /b 1
)

echo Instalando dependencias...
pip install mcp[cli] msal requests
if errorlevel 1 (
    echo ERROR: Fallo la instalacion de dependencias.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Dependencias instaladas correctamente!
echo ============================================
echo.
echo Ahora configura Claude Desktop:
echo.
echo 1. Abre Claude Desktop
echo 2. Ve a Settings (icono de engranaje)
echo 3. Click en "Developer" y luego "Edit Config"
echo 4. Reemplaza el contenido con el archivo claude_desktop_config.json
echo    que esta en esta carpeta (edita las rutas primero)
echo 5. Reinicia Claude Desktop
echo.
pause
