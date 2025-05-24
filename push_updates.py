import os, time

while True:
    os.system("git add gold_gpt_data.txt")
    os.system("git commit -m 'Auto update' || echo no changes")
    os.system("git push origin main")
    time.sleep(1)  # every 60 seconds
