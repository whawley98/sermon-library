@echo off
set S=C:\Users\WilliamHawley\Documents\Personal\sermon-library\sermon-library\scripts\staging
set R=C:\Users\WilliamHawley\Documents\Personal\sermon-library\sermon-library

echo Deploying files...

if exist "%S%\firebase.js"         copy /Y "%S%\firebase.js"         "%R%\src\lib\firebase.js"         && echo [OK] firebase.js
if exist "%S%\ai.js"               copy /Y "%S%\ai.js"               "%R%\src\lib\ai.js"               && echo [OK] ai.js
if exist "%S%\App.js"              copy /Y "%S%\App.js"              "%R%\src\App.js"                  && echo [OK] App.js
if exist "%S%\App.css"             copy /Y "%S%\App.css"             "%R%\src\App.css"                 && echo [OK] App.css
if exist "%S%\globals.css"         copy /Y "%S%\globals.css"         "%R%\src\styles\globals.css"      && echo [OK] globals.css
if exist "%S%\useTheme.js"         copy /Y "%S%\useTheme.js"         "%R%\src\hooks\useTheme.js"       && echo [OK] useTheme.js
if exist "%S%\Header.js"           copy /Y "%S%\Header.js"           "%R%\src\components\Header.js"    && echo [OK] Header.js
if exist "%S%\Header.css"          copy /Y "%S%\Header.css"          "%R%\src\components\Header.css"   && echo [OK] Header.css
if exist "%S%\Sidebar.js"          copy /Y "%S%\Sidebar.js"          "%R%\src\components\Sidebar.js"   && echo [OK] Sidebar.js
if exist "%S%\Sidebar.css"         copy /Y "%S%\Sidebar.css"         "%R%\src\components\Sidebar.css"  && echo [OK] Sidebar.css
if exist "%S%\SermonCard.js"       copy /Y "%S%\SermonCard.js"       "%R%\src\components\SermonCard.js" && echo [OK] SermonCard.js
if exist "%S%\SermonCard.css"      copy /Y "%S%\SermonCard.css"      "%R%\src\components\SermonCard.css" && echo [OK] SermonCard.css
if exist "%S%\LibraryPage.js"      copy /Y "%S%\LibraryPage.js"      "%R%\src\pages\LibraryPage.js"    && echo [OK] LibraryPage.js
if exist "%S%\LibraryPage.css"     copy /Y "%S%\LibraryPage.css"     "%R%\src\pages\LibraryPage.css"   && echo [OK] LibraryPage.css
if exist "%S%\SermonPage.js"       copy /Y "%S%\SermonPage.js"       "%R%\src\pages\SermonPage.js"     && echo [OK] SermonPage.js
if exist "%S%\SermonPage.css"      copy /Y "%S%\SermonPage.css"      "%R%\src\pages\SermonPage.css"    && echo [OK] SermonPage.css
if exist "%S%\AskPage.js"          copy /Y "%S%\AskPage.js"          "%R%\src\pages\AskPage.js"        && echo [OK] AskPage.js
if exist "%S%\AskPage.css"         copy /Y "%S%\AskPage.css"         "%R%\src\pages\AskPage.css"       && echo [OK] AskPage.css
if exist "%S%\StatsPage.js"        copy /Y "%S%\StatsPage.js"        "%R%\src\pages\StatsPage.js"      && echo [OK] StatsPage.js
if exist "%S%\StatsPage.css"       copy /Y "%S%\StatsPage.css"       "%R%\src\pages\StatsPage.css"     && echo [OK] StatsPage.css
if exist "%S%\deploy.yml"          copy /Y "%S%\deploy.yml"          "%R%\.github\workflows\deploy.yml" && echo [OK] deploy.yml
if exist "%S%\ingest.py"           copy /Y "%S%\ingest.py"           "%R%\scripts\ingest.py"           && echo [OK] ingest.py
if exist "%S%\cleanup.py"          copy /Y "%S%\cleanup.py"          "%R%\scripts\cleanup.py"          && echo [OK] cleanup.py
if exist "%S%\fix_data.py"         copy /Y "%S%\fix_data.py"         "%R%\scripts\fix_data.py"         && echo [OK] fix_data.py
if exist "%S%\diagnose.py"         copy /Y "%S%\diagnose.py"         "%R%\scripts\diagnose.py"         && echo [OK] diagnose.py
if exist "%S%\reprocess_failed.py" copy /Y "%S%\reprocess_failed.py" "%R%\scripts\reprocess_failed.py" && echo [OK] reprocess_failed.py
if exist "%S%\update_web_urls.py"  copy /Y "%S%\update_web_urls.py"  "%R%\scripts\update_web_urls.py"  && echo [OK] update_web_urls.py
if exist "%S%\package.json"        copy /Y "%S%\package.json"        "%R%\package.json"                && echo [OK] package.json
if exist "%S%\README.md"           copy /Y "%S%\README.md"           "%R%\README.md"                   && echo [OK] README.md

echo.
echo Done. Now run:
echo   git add .
echo   git commit -m "Update files"
echo   git push
echo.
pause
