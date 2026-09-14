@echo off
rem 아우리봇 로컬 서버 ? 탐색기에서 더블클릭하거나 터미널에서 scripts\serve.cmd
rem
rem 실제 동작은 serve.py 가 한다. 그쪽이 서버를 콘솔·프로세스 그룹에서 떼어내
rem 띄우기 때문에, 이 창을 닫아도 서버는 계속 돈다.
rem
rem   scripts\serve.cmd            서버 기동
rem   scripts\serve.cmd --status   상태 확인
rem   scripts\serve.cmd --stop     서버 종료
rem
rem 주의: 이 파일은 CRLF + CP949 로 저장할 것. LF 로 저장하면 cmd 가 파싱에
rem 실패하고, UTF-8 로 저장하면 한글 echo 행을 명령으로 오인한다(둘 다 실측).
cd /d "%~dp0.."
python "%~dp0serve.py" %*
if errorlevel 1 pause
