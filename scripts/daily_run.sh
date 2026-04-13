#!/bin/bash
# AI Daily Briefing — Cron Jobs
# Daily at 5 AM UTC — lightweight ingest only (no LLM)
# Weekly on Monday at 6 AM UTC — full pipeline with LLM
#
# Crontab entries:
#   0 5 * * * /home/ubuntu/projects/ai-daily-briefing/scripts/daily_run.sh ingest
#   0 6 * * 1 /home/ubuntu/projects/ai-daily-briefing/scripts/daily_run.sh weekly

cd /home/ubuntu/projects/ai-daily-briefing

MODE="${1:-ingest}"

mkdir -p logs

if [ "$MODE" = "weekly" ]; then
    echo "=== Weekly pipeline started at $(date -u) ===" >> logs/weekly_pipeline.log
    /usr/bin/python3 scripts/weekly_pipeline.py >> logs/weekly_pipeline.log 2>&1
    echo "=== Weekly pipeline completed at $(date -u) ===" >> logs/weekly_pipeline.log
else
    echo "=== Daily ingest started at $(date -u) ===" >> logs/daily_ingest.log
    /usr/bin/python3 scripts/daily_ingest.py >> logs/daily_ingest.log 2>&1
    echo "=== Daily ingest completed at $(date -u) ===" >> logs/daily_ingest.log
fi
