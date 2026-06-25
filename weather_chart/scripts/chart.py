"""Weather chart skill - plot hourly temperature with weather icons."""
import json, urllib.request, gzip, io, os, argparse, sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timezone, timedelta
import cairosvg
from PIL import Image
import numpy as np
from scipy.interpolate import PchipInterpolator

CST = timezone(timedelta(hours=8))

# ── API endpoint mapping ──
API_ENDPOINTS = [24, 72, 168]

def resolve_hours(user_hours: int) -> tuple[int, str]:
    """Map user hours to nearest API endpoint. Returns (sliced_hours, api_str)."""
    if user_hours < 1:
        raise ValueError(f"Hours must be >= 1, got {user_hours}")
    if user_hours % 12 != 0:
        raise ValueError(f"Hours must be divisible by 12, got {user_hours}")
    for ep in API_ENDPOINTS:
        if user_hours <= ep:
            return (user_hours, f"{ep}h")
    raise ValueError(f"Max supported hours is 168, got {user_hours}")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_DIR = os.path.join(SCRIPT_DIR, "icons")
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")

# ── Load config ──
with open(CONFIG_PATH) as f:
    cfg = json.load(f)

ICON_BASE = "https://raw.githubusercontent.com/qwd/Icons/main/icons"

COLOR_MAP = {
    '100': '#FFB347', '150': '#FFD700',
    '101': '#87CEEB', '151': '#6A8CBF',
    '102': '#87CEEB', '152': '#6A8CBF',
    '103': '#87CEEB', '153': '#6A8CBF',
    '104': '#B0C4DE',
    '300': '#4682B4', '301': '#4169E1',
    '302': '#4B0082', '303': '#4B0082', '304': '#4B0082',
    '305': '#6495ED', '306': '#4682B4', '307': '#1E90FF',
    '308': '#0000CD', '309': '#6495ED', '310': '#1E90FF',
    '350': '#4682B4', '351': '#4169E1',
    '400': '#E0E8F0', '401': '#C8D8E8', '402': '#B0C8E0',
    '500': '#A9A9A9', '501': '#808080', '502': '#696969',
    '900': '#FF6347', '901': '#4169E1',
}


def get_icon(code: str) -> Image.Image | None:
    os.makedirs(ICON_DIR, exist_ok=True)
    cache_path = os.path.join(ICON_DIR, f"{code}.png")
    if not os.path.exists(cache_path):
        svg_url = f"{ICON_BASE}/{code}.svg"
        req = urllib.request.Request(svg_url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            svg = urllib.request.urlopen(req, timeout=5).read().decode()
        except Exception:
            return None
        color = COLOR_MAP.get(code, '#CCCCCC')
        svg = svg.replace('fill="currentColor"', f'fill="{color}"')
        png = cairosvg.svg2png(bytestring=svg.encode(), output_width=64, output_height=64)
        with open(cache_path, 'wb') as f:
            f.write(png)
    return Image.open(cache_path)


def fetch_data(hours: str) -> dict:
    url = f"https://{cfg['api_host']}/v7/weather/{hours}?location={cfg['location']}&key={cfg['api_key']}"
    req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        raw = resp.read()
        if raw[0] == 0x1f and raw[1] == 0x8b:
            raw = gzip.decompress(raw)
    return json.loads(raw)


def plot(user_hours: int = None, out_path: str = None, location_name: str = None) -> str:
    from matplotlib.offsetbox import OffsetImage, AnnotationBbox

    if user_hours is None:
        user_hours = int(cfg['default_hours'].rstrip('h'))
    if location_name is not None:
        # GeoAPI v2 动态查城市 → JWT 签名
        import urllib.parse, time as _time, base64 as _b64
        from cryptography.hazmat.primitives import serialization as _ser
        from cryptography.hazmat.primitives.asymmetric import ed25519 as _ed

        priv_path = os.path.join(SCRIPT_DIR, "private.pem")
        if os.path.exists(priv_path):
            with open(priv_path, 'rb') as _f:
                _pk = _ser.load_pem_private_key(_f.read(), password=None)
            _now = int(_time.time())
            _h = _b64.urlsafe_b64encode(json.dumps({"alg":"EdDSA","typ":"JWT","kid":"CD5BE2HF5F"}).encode()).rstrip(b'=').decode()
            _p = _b64.urlsafe_b64encode(json.dumps({"sub":"4AKUXDBGTH","iat":_now-30,"exp":_now+300}).encode()).rstrip(b'=').decode()
            _sig = _b64.urlsafe_b64encode(_pk.sign(f"{_h}.{_p}".encode())).rstrip(b'=').decode()
            _jwt = f"{_h}.{_p}.{_sig}"
        else:
            _jwt = None

        encoded = urllib.parse.quote(location_name)
        geo_url = f"https://{cfg['api_host']}/geo/v2/city/lookup?location={encoded}"
        headers = {"Accept-Encoding": "gzip"}
        if _jwt:
            headers["Authorization"] = f"Bearer {_jwt}"
        geo_req = urllib.request.Request(geo_url, headers=headers)
        try:
            with urllib.request.urlopen(geo_req, timeout=5) as resp:
                geo_raw = resp.read()
                if geo_raw and geo_raw[0] == 0x1f and geo_raw[1] == 0x8b:
                    geo_raw = gzip.decompress(geo_raw)
            geo_data = json.loads(geo_raw)
            if geo_data.get('code') == '200' and geo_data.get('location'):
                loc = geo_data['location'][0]
                cfg['location'] = loc['id']
                cfg['location_name'] = loc['name']
            else:
                print(f"GeoAPI for '{location_name}': code={geo_data.get('code')}", file=sys.stderr)
        except Exception as e:
            print(f"GeoAPI for '{location_name}': {e}", file=sys.stderr)

    data_hours, api_endpoint = resolve_hours(user_hours)
    if out_path is None:
        out_path = os.path.join(cfg['output_dir'], cfg['output_filename'])

    data = fetch_data(api_endpoint)
    if data.get('code') != '200':
        raise RuntimeError(f"API error: {data}")

    hourly = data['hourly'][:data_hours]
    times = [datetime.fromisoformat(h['fxTime']) for h in hourly]
    temps = [float(h['temp']) for h in hourly]
    humids = [int(h['humidity']) for h in hourly]
    precips = [float(h.get('precip', 0)) for h in hourly]
    icons_data = [h['icon'] for h in hourly]

    fig, ax = plt.subplots(figsize=(14, 7))

    x_epoch = np.array([t.timestamp() for t in times])
    y = np.array(temps)
    pch = PchipInterpolator(x_epoch, y)
    x_extra = np.linspace(x_epoch.min(), x_epoch.max(), len(times) * 4)
    x_smooth = np.sort(np.unique(np.concatenate([x_epoch, x_extra])))
    y_smooth = pch(x_smooth)
    times_smooth = [datetime.fromtimestamp(v, tz=CST) for v in x_smooth]

    ax.plot(times_smooth, y_smooth, color='#7EC8E3', linewidth=2.5, alpha=0.95, zorder=3)
    ax.fill_between(times_smooth, y_smooth, min(y)-2, alpha=0.10, color='#7EC8E3', zorder=1)

    # ── Humidity (right Y-axis) ──
    y_h = np.array(humids)
    pch_h = PchipInterpolator(x_epoch, y_h)
    y_h_smooth = pch_h(x_smooth)

    ax2 = ax.twinx()
    ax2.plot(times_smooth, y_h_smooth, color='#4ADE80', linewidth=1.6, linestyle='--', alpha=0.85, zorder=3)
    ax2.set_ylim(-5, 105)
    ax2.set_ylabel('Humidity (%)', fontsize=13, color='#4ADE80')
    ax2.tick_params(colors='#4ADE80', labelsize=10)
    ax2.spines['right'].set_color('#1A3A1A')

    # ── Precipitation fill (third Y-axis) ──
    p_arr = np.array(precips)
    pch_p = PchipInterpolator(x_epoch, p_arr)
    p_smooth = pch_p(x_smooth)

    ax3 = ax.twinx()
    ax3.spines['right'].set_position(('outward', 55))
    ax3.spines['right'].set_color('#3A5A6A')
    ax3.fill_between(times_smooth, p_smooth, 0, color='#87CEEB', alpha=0.15, zorder=0)
    ax3.set_ylim(0, max(max(precips) * 3, 5))
    ax3.set_ylabel('Precip (mm)', fontsize=11, color='#87CEEB')
    ax3.tick_params(colors='#87CEEB', labelsize=9)

    # ── 午夜分隔线 + 日期标签 ──
    midnights = [t for t in times if t.hour == 0 and t.minute == 0]
    weekday_abbr = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    for m in midnights:
        ax.axvline(m, color='#7EC8E3', linestyle='--', linewidth=0.8, alpha=0.4, zorder=2)
        ax.text(m, max(y)+4, f'{m.strftime("%m/%d")} {weekday_abbr[m.weekday()]}',
                ha='center', va='bottom', fontsize=13, color='#7EC8E3', alpha=0.8)

    # ── icons density by hour bracket (divisor of 24, x-axis aligned) ──
    if data_hours <= 24:
        icons_per_day = 12     # 2h
    elif data_hours <= 48:
        icons_per_day = 6      # 4h
    elif data_hours <= 72:
        icons_per_day = 4      # 6h
    elif data_hours <= 120:
        icons_per_day = 3      # 8h
    else:
        icons_per_day = 2      # 12h
    icon_interval = 24 // icons_per_day
    x_data_min = mdates.date2num(times[0])
    x_data_max = mdates.date2num(times[-1])
    ax.set_xlim(x_data_min, x_data_max)
    icon_indices = [i for i, t in enumerate(times) if t.hour % icon_interval == 0]
    for idx in icon_indices:
        img = get_icon(icons_data[idx])
        if img is not None:
            x_frac = (mdates.date2num(times[idx]) - x_data_min) / (x_data_max - x_data_min)
            oi = OffsetImage(np.array(img), zoom=0.45)
            ab = AnnotationBbox(oi, (x_frac, 1.02),
                                xycoords=ax.transAxes,
                                frameon=False, box_alignment=(0.5, 0),
                                zorder=6)
            ax.add_artist(ab)


    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M', tz=CST))
    byhour = list(range(0, 24, icon_interval))
    ax.xaxis.set_major_locator(mdates.HourLocator(byhour=byhour, tz=CST))
    ax.set_ylabel('Temperature (C)', fontsize=15, color='#B0D4E8')
    name = cfg.get('location_name', 'City')
    ax.set_title('')
    ax.grid(True, alpha=0.30, color='#7EC8E3', linewidth=0.6)
    ax.set_ylim(min(y)-2, max(y)+5)
    ax.tick_params(colors='#7EC8E3', labelsize=11)
    ax.set_facecolor('#0D1117')
    fig.patch.set_facecolor('#0D1117')
    for spine in ax.spines.values():
        spine.set_color('#2A3A4A')
    fig.autofmt_xdate()

    # 背景水印 — 地区名
    from matplotlib.font_manager import FontProperties
    cn_font = FontProperties(fname="/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", size=160)
    ax.text(0.5, 0.5, cfg.get('location_name', ''), transform=ax.transAxes,
            fontproperties=cn_font, color='#7EC8E3', alpha=0.10, ha='center', va='center', zorder=0)

    fig.subplots_adjust(top=0.88, left=0.08, right=0.90, bottom=0.12)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    icon_artists = [c for c in ax.get_children() if isinstance(c, AnnotationBbox)]
    plt.savefig(out_path, dpi=140, bbox_inches='tight', facecolor='#0D1117',
                bbox_extra_artists=icon_artists)
    plt.close(fig)
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-o', '--out', default=None)
    parser.add_argument('-H', '--hours', type=int, default=None,
                        help='Forecast hours (max 168), e.g. 48')
    parser.add_argument('-L', '--location', type=str, default=None,
                        help='District name, e.g. 番禺')
    args = parser.parse_args()
    path = plot(user_hours=args.hours, out_path=args.out, location_name=args.location)
    print(path)
