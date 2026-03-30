"""
매일 오전 9시 자동 실행 스케줄러
python scheduler.py 로 백그라운드 실행
"""

import schedule
import time
from agent import run

# 매일 오전 9시 실행
schedule.every().day.at("09:00").do(run)

# 테스트용: 바로 한번 실행하고 싶으면 아래 주석 해제
# run()

print("⏰ 스케줄러 시작 (매일 09:00 실행)")
print("Ctrl+C로 종료\n")

while True:
    schedule.run_pending()
    time.sleep(60)
