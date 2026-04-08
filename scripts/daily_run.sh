#!/bin/bash
# Daily AI Briefing Pipeline
# Runs at 5:00 AM UTC via cron
cd /home/ubuntu/projects/ai-daily-briefing
/usr/bin/python3 main.py >> /home/ubuntu/projects/ai-daily-briefing/logs/pipeline.log 2>&1
echo "--- Run completed at $(date -u) ---" >> /home/ubuntu/projects/ai-daily-briefing/logs/pipeline.log
