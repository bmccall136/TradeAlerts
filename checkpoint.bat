@echo off
REM Set the timestamp
set dt=%date:~10,4%-%date:~4,2%-%date:~7,2%_%time:~0,2%-%time:~3,2%-%time:~6,2%
set dt=%dt: =0%

REM Make sure checkpoints folder exists
if not exist checkpoints mkdir checkpoints

REM Optional: Create a zip archive of your project as a checkpoint
powershell Compress-Archive -Path * -DestinationPath "checkpoints\checkpoint_%dt%.zip"

REM Stage all changes
git add .

REM Commit with timestamp message
git commit -m "Checkpoint %dt%"

REM Push to origin (change branch if needed)
git push origin HEAD

echo Backup and sync to remote completed!
pause
