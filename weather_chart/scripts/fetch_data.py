"""Fetch Guangzhou weather data (now + 7d forecast + indices) for agent consumption."""
import json, os, gzip, urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(SCRIPT_DIR, "config.json")) as f:
    cfg = json.load(f)

host = cfg["api_host"]
key = cfg["api_key"]
loc = cfg["location"]

results = {}

# --- now ---
url = f"https://{host}/v7/weather/now?location={loc}&key={key}"
req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"})
with urllib.request.urlopen(req, timeout=8) as resp:
    raw = resp.read()
    if raw[0] == 0x1f and raw[1] == 0x8b:
        raw = gzip.decompress(raw)
results["now"] = json.loads(raw)["now"]

# --- 7d forecast ---
url = f"https://{host}/v7/weather/7d?location={loc}&key={key}"
req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"})
with urllib.request.urlopen(req, timeout=8) as resp:
    raw = resp.read()
    if raw[0] == 0x1f and raw[1] == 0x8b:
        raw = gzip.decompress(raw)
results["forecast"] = json.loads(raw)["daily"][:3]

# --- indices (运动 + 洗车) ---
url = f"https://{host}/v7/indices/1d?location={loc}&key={key}&type=1,2"
req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"})
with urllib.request.urlopen(req, timeout=8) as resp:
    raw = resp.read()
    if raw[0] == 0x1f and raw[1] == 0x8b:
        raw = gzip.decompress(raw)
results["indices"] = json.loads(raw)["daily"]

print(json.dumps(results, ensure_ascii=False))
