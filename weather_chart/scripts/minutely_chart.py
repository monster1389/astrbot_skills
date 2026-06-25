"""Minute precipitation chart — minutely/5m bar chart with dark theme.
Usage: python3 minutely_chart.py [-L 番禺] [-o /tmp/minutely.png]
"""
import json, urllib.request, urllib.parse, gzip, os, sys, argparse, time, base64
from datetime import datetime, timezone, timedelta

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

CST = timezone(timedelta(hours=8))
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Load config ──
with open(os.path.join(SCRIPT_DIR, "config.json")) as f:
    cfg = json.load(f)

# ── JWT ──
priv_path = os.path.join(SCRIPT_DIR, "private.pem")
_jwt = None
if os.path.exists(priv_path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519

    with open(priv_path, 'rb') as f:
        pk = serialization.load_pem_private_key(f.read(), password=None)
    now = int(time.time())
    h = base64.urlsafe_b64encode(json.dumps({"alg":"EdDSA","typ":"JWT","kid":"CD5BE2HF5F"}).encode()).rstrip(b'=').decode()
    p = base64.urlsafe_b64encode(json.dumps({"sub":"4AKUXDBGTH","iat":now-30,"exp":now+300}).encode()).rstrip(b'=').decode()
    sig = base64.urlsafe_b64encode(pk.sign(f"{h}.{p}".encode())).rstrip(b'=').decode()
    _jwt = f"{h}.{p}.{sig}"


def geo_lookup(name: str) -> dict | None:
    """Look up city/district via GeoAPI v2, return {id, name, lon, lat}."""
    url = f"https://{cfg['api_host']}/geo/v2/city/lookup?location={urllib.parse.quote(name)}"
    headers = {"Accept-Encoding": "gzip"}
    if _jwt:
        headers["Authorization"] = f"Bearer {_jwt}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=5) as resp:
        raw = resp.read()
        if raw and raw[0] == 0x1f and raw[1] == 0x8b:
            raw = gzip.decompress(raw)
    data = json.loads(raw)
    if data.get('code') == '200' and data.get('location'):
        return data['location'][0]
    return None


def fetch_minutely(lon: str, lat: str) -> dict:
    """Fetch minutely/5m data, return {summary, items}."""
    url = f"https://{cfg['api_host']}/v7/minutely/5m?location={lon},{lat}"
    headers = {"Accept-Encoding": "gzip"}
    if _jwt:
        headers["Authorization"] = f"Bearer {_jwt}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=5) as resp:
        raw = resp.read()
        if raw and raw[0] == 0x1f and raw[1] == 0x8b:
            raw = gzip.decompress(raw)
    return json.loads(raw)


def plot(location_name: str = None, out_path: str = None) -> str:
    """Generate minute precipitation chart.

    Args:
        location_name: District/city name. Defaults to config location_name.
        out_path: Output PNG path. Defaults to /tmp/minutely.png.

    Returns:
        Output file path.
    """
    if location_name is None:
        location_name = cfg['location_name']
    if out_path is None:
        out_path = os.path.join(cfg['output_dir'], 'minutely.png')

    loc = geo_lookup(location_name)
    if loc is None:
        raise RuntimeError(f"GeoAPI lookup failed for '{location_name}'")

    data = fetch_minutely(loc['lon'], loc['lat'])
    if data.get('code') != '200':
        raise RuntimeError(f"Minutely API error: {data}")

    items = data['minutely']
    times = [datetime.fromisoformat(it['fxTime']).astimezone(CST) for it in items]
    precips = [float(it['precip']) for it in items]

    # ── Chart ──
    wm_font = FontProperties(fname="/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", size=160)

    fig, ax = plt.subplots(figsize=(12, 5))
    fig.patch.set_facecolor('#0D1117')
    ax.set_facecolor('#0D1117')

    ax.bar(times, precips, width=0.003, color='#6BB5FF', alpha=0.7, zorder=3)
    ax.set_ylabel('mm / 5min', fontsize=11, color='#B0D4E8')
    ax.grid(True, alpha=0.20, color='#7EC8E3', linewidth=0.5)
    ax.tick_params(colors='#7EC8E3', labelsize=10)
    for spine in ax.spines.values():
        spine.set_color('#2A3A4A')

    # Watermark
    ax.text(0.5, 0.5, loc['name'], transform=ax.transAxes,
            fontproperties=wm_font, color='#7EC8E3', alpha=0.10, ha='center', va='center', zorder=0)

    fig.autofmt_xdate()
    plt.tight_layout(pad=2)

    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    plt.savefig(out_path, dpi=150, facecolor='#0D1117', bbox_inches='tight')
    plt.close(fig)
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-o', '--out', default=None)
    parser.add_argument('-L', '--location', type=str, default=None,
                        help='District/city name, e.g. 番禺')
    args = parser.parse_args()
    path = plot(location_name=args.location, out_path=args.out)
    print(path)
