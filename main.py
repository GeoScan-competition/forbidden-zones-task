"""
Шаблон для задания «Полёт через запретные зоны».

Пример запуска:
    python main.py 127.0.0.1 8000 "C:/Users/Student/AppData/Local/GeoscanSimulator/zones.txt"
"""

from pioneer_sdk import Pioneer
import sys

if __name__ == "__main__":
    ip = sys.argv[1]
    port = int(sys.argv[2])
    zones_file = sys.argv[3]

    with open(zones_file, "r", encoding="utf-8") as f:
        f.read()
      
    drone = Pioneer(ip=ip, mavlink_port=port, simulator=True)
