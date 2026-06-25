#!/bin/bash
# 定时降水推送 — 7:45 / 17:45
set -e

SCRIPT_DIR="/AstrBot/data/skills/weather_chart"
CONFIG="${SCRIPT_DIR}/scripts/config.json"

API_BASE="http://localhost:6185/api/v1"
API_KEY=$(python3 -c "import json; print(json.load(open('${CONFIG}'))['astr_api_key'])")
LOCATION=$(python3 -c "import json; print(json.load(open('${CONFIG}'))['location_name'])")
UMO="napcat:FriendMessage:2854964693"
TMP_IMG="/tmp/cron_rain_${LOCATION}.png"

echo "[$(date '+%H:%M:%S')] ${LOCATION} 降水预报..."

python3 "${SCRIPT_DIR}/scripts/minutely_chart.py" -L "${LOCATION}" -o "${TMP_IMG}"

UPLOAD=$(curl -s -X POST "${API_BASE}/file" \
    -H "Authorization: Bearer ${API_KEY}" \
    -F "file=@${TMP_IMG}")
ATTACH=$(echo "${UPLOAD}" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['attachment_id'])")
echo "  uploaded: ${ATTACH}"

curl -s -X POST "${API_BASE}/im/message" \
    -H "Authorization: Bearer ${API_KEY}" \
    -H "Content-Type: application/json" \
    -d "{\"umo\":\"${UMO}\",\"message\":[{\"type\":\"plain\",\"text\":\"${LOCATION} 未来2小时分钟级降水预报：\"},{\"type\":\"image\",\"attachment_id\":\"${ATTACH}\"}]}"

rm -f "${TMP_IMG}"
echo "[$(date '+%H:%M:%S')] done"
