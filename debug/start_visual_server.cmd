@echo off
cd /d C:\Users\32434\Desktop\SiameseBH
C:\Users\32434\anaconda3\python.exe -m abm.visual_server --host 127.0.0.1 --port 8789 --students 100 --male-count 80 --start-time 07:00:00 --seconds-per-step 1 --resume
