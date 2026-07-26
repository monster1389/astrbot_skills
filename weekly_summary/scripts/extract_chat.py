#!/usr/bin/env python3
"""从 astrbot*.log 提取指定用户和日期区间的聊天记录，输出为 Markdown
Usage: python3 extract_chat.py --user tool-nut --start 2026-07-21 --end 2026-07-25
"""

import re
import sys
import glob
import os
import argparse
from datetime import date, timedelta

LOG_DIR = "/AstrBot/data/logs"
OUT_PATH = "/tmp/week_chat.md"

# 用户消息: RawMessage 的 raw_message 字段
RAWMSG_RE_TEMPLATE = (
    r"\[(?P<ts>[\d\- :.]+)\] .*? RawMessage .*?"
    r"'raw_message':\s*'(?P<text>.+?)',\s*(?:'font'|'message')"
)

# Amadeus 回复: completion finish_reason='stop'
COMPLETION_TS_RE = re.compile(r"^\[(?P<ts>[\d\- :.]+)\]")
COMPLETION_STOP_RE = re.compile(r"finish_reason='stop'")
COMPLETION_CONTENT_RE = re.compile(r"content='(.+?)',\s*refusal=")

SKIP_PATTERNS = [
    r'\[Tool\b',
    r'\[result_decorate',
    r'\[pipeline\.',
    r'\[runners\.',
    r'\[agent_sub_stages',
]


def find_log_files(log_dir: str) -> list:
    files = glob.glob(os.path.join(log_dir, "astrbot*.log"))
    files.sort(key=lambda f: os.path.getmtime(f))
    return files


def unescape(text: str) -> str:
    return (
        text.replace("\\n", "\n")
            .replace("\\t", "\t")
            .replace("\\'", "'")
            .replace('\\"', '"')
            .replace("\\\\", "\\")
    )


def should_skip(line: str) -> bool:
    for pat in SKIP_PATTERNS:
        if re.search(pat, line):
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description="Extract chat logs")
    parser.add_argument("--user", default="tool-nut")
    parser.add_argument("--start", help="Start date YYYY-MM-DD (default: 7 days ago)")
    parser.add_argument("--end", help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--out", default=OUT_PATH)
    args = parser.parse_args()

    user = args.user
    end_date = date.fromisoformat(args.end) if args.end else date.today()
    start_date = date.fromisoformat(args.start) if args.start else end_date - timedelta(days=7)

    dates = set()
    d = start_date
    while d <= end_date:
        dates.add(d.isoformat())
        d += timedelta(days=1)

    raw_re = re.compile(RAWMSG_RE_TEMPLATE)

    lines_out = []
    seen_raw = set()
    seen_completions = set()

    log_files = find_log_files(LOG_DIR)

    for log_path in log_files:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                if len(stripped) < 11 or stripped[0] != '[':
                    continue
                line_date = stripped[1:11]
                if line_date not in dates:
                    continue
                if should_skip(stripped):
                    continue

                # --- 用户消息 ---
                rm = raw_re.search(stripped)
                if rm:
                    if user not in stripped and "2854964693" not in stripped:
                        continue
                    ts = rm.group("ts").split(".")[0]
                    text = unescape(rm.group("text")).strip()
                    if not text or text == "Output your last task result below.":
                        continue
                    if text in seen_raw:
                        continue
                    seen_raw.add(text)
                    lines_out.append(f"**🧑 {user}** _{ts}_\n\n{text}\n\n***\n\n")
                    continue

                # --- Amadeus 回复 ---
                if not COMPLETION_STOP_RE.search(stripped):
                    continue
                ts_match = COMPLETION_TS_RE.match(stripped)
                if not ts_match:
                    continue
                ts = ts_match.group("ts").split(".")[0]
                cm = COMPLETION_CONTENT_RE.search(stripped)
                if not cm:
                    continue
                text = unescape(cm.group(1)).strip()
                if not text:
                    continue
                if text.startswith("任务完成"):
                    continue
                key = text[:80]
                if key in seen_completions:
                    continue
                seen_completions.add(key)
                lines_out.append(f"**🤖 Amadeus** _{ts}_\n\n{text}\n\n***\n\n")

    if not lines_out:
        print("ERROR: no messages found", file=sys.stderr)
        sys.exit(1)

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(f"# 聊天记录: {user} ({start_date} → {end_date})\n\n")
        f.write("".join(lines_out))

    print(args.out)


if __name__ == "__main__":
    main()
