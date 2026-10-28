@echo off
cd /d "%~dp0"
docker info >nul 2>&1
if errorlevel 1 (
  echo Docker Desktop no esta abierto. Abrelo y vuelve a intentar.
  pause
  exit /b 1
)
if not exist .env echo Aviso: no existe .env; los videos se guardaran en la carpeta "projects" de este programa.
docker compose build || (pause & exit /b 1)
echo.
echo Listo. Comandos: evergreen new "Titulo" --format rhyme ^| evergreen run ID ^| evergreen status ID ^| evergreen list
echo Para salir escribe: exit
echo.
docker compose run --rm app bash
