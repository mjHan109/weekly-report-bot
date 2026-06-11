@echo off
:: 서비스 제거 스크립트 (관리자 권한 필요)
set SERVICE_NAME=WeeklyReportBot

nssm stop %SERVICE_NAME%
nssm remove %SERVICE_NAME% confirm
echo 서비스가 제거되었습니다.
pause
