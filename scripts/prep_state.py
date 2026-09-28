# -*- coding: utf-8 -*-
"""截圖前後的資料狀態備份／還原（只用標準函式庫）。

截圖時點開對話會把未讀歸零、切換模式會改狀態……這些是「拍照的副作用」，拍完要還原。
本工具把指定資料表的指定欄位存成快照，事後逐筆比對、只改有變的列。

用法：
  python scripts/prep_state.py backup  --table sp8_threads --fields unread_count,ai_state --where app_domain=xxx
  python scripts/prep_state.py restore --table sp8_threads
  python scripts/prep_state.py diff    --table sp8_threads      # 只列出差異，不寫入

登入：環境變數 AIGO_TOKEN，或 AIGO_EMAIL／AIGO_PASSWORD（也可放在 --env 指定的檔案，預設 ~/.aigo/.env）。
★ 資料中心紀錄 PATCH 要包 {"data": {...}}，平面 body 會回 200 但不寫入；本工具寫完一律讀回驗證。
"""
import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path


def read_env(path):
    p = Path(os.path.expanduser(path))
    if not p.exists():
        return {}
    out = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip("\"'")
    return out


def req(base, method, path, token=None, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    r = urllib.request.Request(base + path, data=data, method=method, headers={"Content-Type": "application/json"})
    if token:
        r.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(r, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


def login(base, env_file):
    if os.environ.get("AIGO_TOKEN"):
        return os.environ["AIGO_TOKEN"]
    env = read_env(env_file)
    email = os.environ.get("AIGO_EMAIL") or env.get("AIGO_EMAIL")
    pw = os.environ.get("AIGO_PASSWORD") or env.get("AIGO_PASSWORD")
    if not email or not pw:
        sys.exit("需要 AIGO_TOKEN 或 AIGO_EMAIL／AIGO_PASSWORD")
    return req(base, "POST", "/api/v1/auth/login", body={"email": email, "password": pw})["access_token"]


def rows(base, tok, table):
    """逐頁讀（page_size 上限 200）；伺服器若忽略 page 參數，重複頁就停，避免無限迴圈。"""
    out, seen, page = [], set(), 1
    while True:
        j = req(base, "GET", f"/api/v1/data-center/tables/{table}/records?page_size=200&page={page}", tok)
        items = j.get("items", j if isinstance(j, list) else [])
        fresh = [r for r in items if r.get("id") not in seen]
        seen.update(r.get("id") for r in fresh)
        out += fresh
        if len(items) < 200 or not fresh:
            return out
        page += 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("op", choices=["backup", "restore", "diff"])
    ap.add_argument("--table", required=True)
    ap.add_argument("--fields", default="")
    ap.add_argument("--where", default="", help="欄位=值，只備份符合的列")
    ap.add_argument("--base", default="https://demo.ai-go.app")
    ap.add_argument("--env", default="~/.aigo/.env")
    ap.add_argument("--file", default="")
    a = ap.parse_args()
    snap = Path(a.file or f"state_backup.{a.table}.json")
    tok = login(a.base, a.env)
    data = rows(a.base, tok, a.table)
    if a.op == "backup":
        fields = [f for f in a.fields.split(",") if f]
        if not fields:
            sys.exit("backup 需要 --fields")
        k, _, v = a.where.partition("=")
        keep = {r["id"]: {f: r.get(f) for f in fields} for r in data if not k or str(r.get(k)) == v}
        snap.write_text(json.dumps({"table": a.table, "fields": fields, "rows": keep}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"備份 {len(keep)} 列 → {snap}")
        return
    s = json.loads(snap.read_text(encoding="utf-8"))
    cur = {r["id"]: r for r in data}
    changed = 0
    for rid, vals in s["rows"].items():
        now = cur.get(rid)
        if not now:
            print("（已不存在）", rid)
            continue
        diff = {f: v for f, v in vals.items() if now.get(f) != v}
        if not diff:
            continue
        changed += 1
        print(("還原 " if a.op == "restore" else "差異 ") + rid, {f: [now.get(f), v] for f, v in diff.items()})
        if a.op == "restore":
            req(a.base, "PATCH", f"/api/v1/data-center/tables/{a.table}/records/{rid}", tok, {"data": diff})
    if a.op == "restore" and changed:
        after = {r["id"]: r for r in rows(a.base, tok, a.table)}
        left = [rid for rid, vals in s["rows"].items() if rid in after and any(after[rid].get(f) != v for f, v in vals.items())]
        print("讀回驗證：", "全部還原" if not left else f"仍有 {len(left)} 列不同（可能是截圖期間真的有新訊息）")
    print("沒有差異" if not changed else f"{changed} 列")


if __name__ == "__main__":
    main()
