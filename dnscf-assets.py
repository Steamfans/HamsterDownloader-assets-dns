#!/usr/bin/env python3
"""
Update assets.123123999.xyz grey-cloud A records from cf-speed-dns ipTop feed.
Fork of https://github.com/ZhiXuanWang/cf-speed-dns/dnscf.py with:
  - proxied=false (grey cloud, required for preferred IP)
  - create missing A records when fewer exist than returned IPs
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback

import urllib.error
import urllib.request

CF_API_TOKEN = os.environ.get("CF_API_TOKEN") or os.environ.get("CLOUDFLARE_API_TOKEN")
CF_ZONE_ID = os.environ.get("CF_ZONE_ID", "7aa2f0a29ec948d83ef363d0664fd598")
CF_DNS_NAME = os.environ.get("CF_DNS_NAME", "assets.123123999.xyz")
IP_TOP_URL = os.environ.get("CF_SPEED_IP_URL", "https://ip.164746.xyz/ipTop.html")
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "")
TIMEOUT = 30


def http_json(method: str, url: str, data: dict | None = None) -> dict:
    headers = {
        "Authorization": f"Bearer {CF_API_TOKEN}",
        "Content-Type": "application/json",
    }
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            raise RuntimeError(f"HTTP {exc.code}: {raw}") from exc


def fetch_text(url: str, retries: int = 5) -> str | None:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "hamsterdl-assets-cf-speed-dns/1.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    return resp.read().decode("utf-8").strip()
        except Exception as exc:  # noqa: BLE001
            print(f"fetch {url} failed ({attempt + 1}/{retries}): {exc}")
            if attempt == retries - 1:
                traceback.print_exc()
    return None


def list_a_records(name: str) -> list[dict]:
    url = f"https://api.cloudflare.com/client/v4/zones/{CF_ZONE_ID}/dns_records?type=A&name={name}"
    result = http_json("GET", url)
    if not result.get("success"):
        raise RuntimeError(f"list DNS failed: {result}")
    return [
        {"id": r["id"], "content": r.get("content", ""), "proxied": r.get("proxied")}
        for r in result.get("result") or []
    ]


def upsert_a_record(record_id: str | None, name: str, ip: str) -> str:
    payload = {
        "type": "A",
        "name": name,
        "content": ip,
        "proxied": False,
        "ttl": 1,
    }
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    if record_id:
        current = list_a_records(name)
        match = next((r for r in current if r["id"] == record_id), None)
        if match and match["content"] == ip and match.get("proxied") is False:
            print(f"skip {name} {ip} (unchanged)")
            return f"{ip} skip"
        url = f"https://api.cloudflare.com/client/v4/zones/{CF_ZONE_ID}/dns_records/{record_id}"
        result = http_json("PUT", url, payload)
    else:
        url = f"https://api.cloudflare.com/client/v4/zones/{CF_ZONE_ID}/dns_records"
        result = http_json("POST", url, payload)

    if result.get("success"):
        print(f"ok {name} → {ip} @ {now}")
        return f"{ip} ok"
    errors = result.get("errors") or []
    if any(e.get("code") == 81058 for e in errors):
        print(f"skip {name} {ip} (already exists)")
        return f"{ip} skip"
    raise RuntimeError(f"upsert failed: {result}")


def delete_a_record(record_id: str, name: str, ip: str) -> str:
    url = f"https://api.cloudflare.com/client/v4/zones/{CF_ZONE_ID}/dns_records/{record_id}"
    result = http_json("DELETE", url)
    if result.get("success"):
        print(f"del {name} {ip} (stale)")
        return f"{ip} del"
    raise RuntimeError(f"delete failed: {result}")


def sync_a_records(name: str, target_ips: list[str]) -> list[str]:
    """Match by IP content to avoid swap conflicts (CF 81058)."""
    records = list_a_records(name)
    target_set = set(target_ips)
    lines: list[str] = []

    for ip in target_ips:
        if any(r["content"] == ip for r in records):
            print(f"skip {name} {ip} (present)")
            lines.append(f"{ip} skip")
            continue

        spare = next((r for r in records if r["content"] not in target_set), None)
        if spare and spare.get("id"):
            lines.append(upsert_a_record(spare["id"], name, ip))
            spare["content"] = ip
            continue

        lines.append(upsert_a_record(None, name, ip))
        records.append({"id": "new", "content": ip, "proxied": False})

    for r in list_a_records(name):
        if r["content"] not in target_set and r.get("id"):
            lines.append(delete_a_record(r["id"], name, r["content"]))

    return lines


def push_plus(content: str) -> None:
    if not PUSHPLUS_TOKEN:
        return
    data = json.dumps(
        {
            "token": PUSHPLUS_TOKEN,
            "title": "assets cf-speed-dns",
            "content": content,
            "template": "markdown",
            "channel": "wechat",
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "http://www.pushplus.plus/send",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=TIMEOUT)
    except Exception as exc:  # noqa: BLE001
        print(f"pushplus failed: {exc}")


def main() -> int:
    if not all([CF_API_TOKEN, CF_ZONE_ID, CF_DNS_NAME]):
        print("missing CF_API_TOKEN / CF_ZONE_ID / CF_DNS_NAME", file=sys.stderr)
        return 1

    raw = fetch_text(IP_TOP_URL)
    if not raw:
        print("failed to fetch ipTop", file=sys.stderr)
        return 1

    ips = [ip.strip() for ip in raw.split(",") if ip.strip()]
    if not ips:
        print("no IPs parsed", file=sys.stderr)
        return 1

    # Reject if R2 read_only record blocks the name (should not be type A, but guard)
    all_records_url = (
        f"https://api.cloudflare.com/client/v4/zones/{CF_ZONE_ID}/dns_records?name={CF_DNS_NAME}"
    )
    all_recs = http_json("GET", all_records_url).get("result") or []
    for rec in all_recs:
        if (rec.get("meta") or {}).get("read_only"):
            print(
                f"R2 read_only DNS still present for {CF_DNS_NAME} — "
                "remove R2 Custom Domain first (Dashboard → R2 → Custom Domains)",
                file=sys.stderr,
            )
            return 1

    lines = sync_a_records(CF_DNS_NAME, ips)
    push_plus("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
