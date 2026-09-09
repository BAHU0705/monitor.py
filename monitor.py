import os
import json
import re
import sys
from datetime import datetime

import requests

VIDEOS = {
    "获奖结果视频": "https://b23.tv/vfrg9Zx",
    "找灵感": "https://b23.tv/OENRgha",
    "做产品-单人": "https://b23.tv/efd59kQ",
    "做产品-圆桌": "https://b23.tv/7IATNwJ",
    "精彩集锦": "https://b23.tv/QhS6Fzh",
}

ALERT_MIN_DROP = 0
SERVERCHAN_SENDKEY = os.environ.get("SERVERCHAN_SENDKEY", "")
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "")
DATA_FILE = "last_views.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com/",
    "Origin": "https://www.bilibili.com",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
}

def resolve_bvid(short_url: str) -> str:
    resp = requests.get(short_url, headers=HEADERS, allow_redirects=True, timeout=15)
    all_urls = [resp.url] + [h.url for h in resp.history]
    for url in all_urls:
        m = re.search(r"(BV[0-9A-Za-z]+)", url)
        if m:
            return m.group(1)
    raise ValueError(f"未能从短链接解析出BV号: {short_url} -> {resp.url}")

def get_view_count(bvid: str) -> int:
    api = "https://api.bilibili.com/x/web-interface/view"
    resp = requests.get(api, params={"bvid": bvid}, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"B站API错误 {data.get('code')}: {data.get('message')}")
    return int(data["data"]["stat"]["view"])

def send_wechat(title: str, content: str):
    if SERVERCHAN_SENDKEY:
        try:
            url = f"https://sctapi.ftqq.com/{SERVERCHAN_SENDKEY}.send"
            requests.post(url, data={"title": title, "desp": content}, timeout=15)
            print("微信推送成功（Server酱）")
        except Exception as e:
            print(f"微信推送失败（Server酱）: {e}")
    if PUSHPLUS_TOKEN:
        try:
            url = "http://www.pushplus.plus/send"
            requests.post(
                url,
                json={"token": PUSHPLUS_TOKEN, "title": title, "content": content},
                timeout=15,
            )
            print("微信推送成功（PushPlus）")
        except Exception as e:
            print(f"微信推送失败（PushPlus）: {e}")

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def main():
    print("解析短链接...")
    bvids = {}
    for name, short_url in VIDEOS.items():
        try:
            bvids[name] = resolve_bvid(short_url)
            print(f"  {name} -> {bvids[name]}")
        except Exception as e:
            print(f"解析失败 {name}: {e}")
            sys.exit(1)

    print("获取播放量...")
    current_views = {}
    for name, bvid in bvids.items():
        try:
            current_views[name] = get_view_count(bvid)
            print(f"  {name}: {current_views[name]:,}")
        except Exception as e:
            print(f"获取失败 {name}: {e}")
            sys.exit(1)

    old_data = load_data()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = []
    alerts = []
    new_data = {}

    for name, curr in current_views.items():
        old_entry = old_data.get(name)
        if old_entry is None:
            status = "首次统计，无法比较"
            inc = None
            new_entry = {"views": curr, "increment": None}
        else:
            old_views = old_entry.get("views")
            old_inc = old_entry.get("increment")
            if old_views is None:
                status = "历史数据异常"
                inc = None
            else:
                inc = curr - old_views
                if old_inc is None:
                    status = f"本次增量 +{inc:,}（首次有增量）"
                else:
                    drop = old_inc - inc
                    if inc < old_inc and drop >= ALERT_MIN_DROP:
                        status = f"变慢 ↓ 前半小时+{old_inc:,}，本次+{inc:,}，下降{drop:,}"
                        alerts.append(f"{name}: {status}")
                    elif inc > old_inc:
                        status = f"加速 ↑ 前半小时+{old_inc:,}，本次+{inc:,}"
                    else:
                        status = f"持平 → 本次+{inc:,}"
            new_entry = {"views": curr, "increment": inc}

        new_data[name] = new_entry
        if inc is not None:
            lines.append(f"  {name}: {curr:,}（本次+{inc:,}；{status}）")
        else:
            lines.append(f"  {name}: {curr:,}（{status}）")

    full_msg = f"[{now_str}] B站播放量播报\n" + "\n".join(lines)
    print(full_msg)

    if SERVERCHAN_SENDKEY or PUSHPLUS_TOKEN:
        if alerts:
            alert_msg = "\n".join(alerts)
            send_wechat("B站播放量增速下降提醒", alert_msg)
        send_wechat("B站播放量播报", full_msg)

    save_data(new_data)

if __name__ == "__main__":
    main()
