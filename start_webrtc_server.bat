@echo off
echo Starting WebRTC Server...
cd /d D:\Projetopresence\presence
call C:\Users\Danilo\miniconda3\Scripts\activate.bat presence
set PYTHONPATH=D:\Projetopresence\presence
set VMS_WEBRTC_PORT=17236
set API_URL=http://127.0.0.1:17234
set RECOGNITION_WORKER_URL=http://127.0.0.1:17235
python app\webrtc_worker\vms_webrtc_server_native.py
pause