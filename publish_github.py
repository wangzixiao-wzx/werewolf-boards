#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把本目录发布到 GitHub 并开启 Pages（仅标准库）。

Token 只通过 --token 或环境变量 GITHUB_TOKEN 传入，绝不写进仓库文件、remote URL 或日志。
需要 classic PAT 的 repo 权限（或 fine-grained token 对该账号仓库的读写权限）。

用法：
    python publish_github.py --token ghp_xxx
    GITHUB_TOKEN=ghp_xxx python publish_github.py
    python publish_github.py --token ghp_xxx --repo werewolf-boards --user your-name
"""
import argparse
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
API = "https://api.github.com"


def redact(s, token):
    return str(s).replace(token, "***") if token else str(s)


def api(method, path, token, payload=None):
    url = API + path
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=body, method=method, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "User-Agent": "werewolf-boards-publisher",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            raw = r.read().decode("utf-8")
            return r.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"message": raw[:200]}


def git(*args, token=None, check=True):
    r = subprocess.run(["git", "-C", str(ROOT)] + list(args),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = redact((r.stdout or "") + (r.stderr or ""), token).strip()
    if check and r.returncode:
        raise RuntimeError("git " + " ".join(args[:2]) + " 失败：" + out[:400])
    return r.returncode, out


def main():
    ap = argparse.ArgumentParser(description="发布版型库到 GitHub Pages")
    ap.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""), help="GitHub PAT")
    ap.add_argument("--user", default="", help="GitHub 用户名（默认取 token 所属账号）")
    ap.add_argument("--repo", default="werewolf-boards", help="仓库名")
    ap.add_argument("--skip-pages", action="store_true", help="只推仓库，不开 Pages")
    a = ap.parse_args()

    token = (a.token or "").strip()
    if not token:
        raise SystemExit("缺少 token：用 --token 传入，或设置环境变量 GITHUB_TOKEN")

    code, me = api("GET", "/user", token)
    if code != 200:
        raise SystemExit(f"token 无效（HTTP {code}）：{me.get('message','')}")
    user = a.user or me["login"]
    print(f"账号：{user}｜仓库：{a.repo}")

    code, r = api("POST", "/user/repos", token, {
        "name": a.repo,
        "description": "狼人杀版型库：板子配置 / 身份构成 / 特殊规则（只读、零依赖）",
        "homepage": f"https://{user}.github.io/{a.repo}/",
        "private": False,
        "has_issues": False,
        "has_wiki": False,
        "has_projects": False,
    })
    if code == 201:
        print("仓库已创建")
    elif code == 422:
        print("仓库已存在，复用")
    else:
        raise SystemExit(f"创建仓库失败（HTTP {code}）：{r.get('message','')}")

    # 本地仓库初始化与提交（保留已有历史，不重复提交）
    if not (ROOT / ".git").exists():
        git("init", "-b", "main", token=token)
    cur, branch = git("branch", "--show-current", token=token, check=False)
    if branch != "main":
        code_b, _ = git("checkout", "-b", "main", token=token, check=False)
        if code_b:
            git("branch", "-M", "main", token=token)
    git("add", "-A", token=token)
    _, status = git("status", "--porcelain", token=token)
    if status:
        code_c, out = git("commit", "-m", "版型库：69 板型 / 120 身份 / 184 规则", token=token, check=False)
        print("已提交：" + ("成功" if code_c == 0 else out[:200]))
    else:
        print("无新改动，跳过提交")

    remote = f"https://github.com/{user}/{a.repo}.git"
    _, existing = git("remote", "get-url", "origin", token=token, check=False)
    if existing != remote:
        code_r, _ = git("remote", "remove", "origin", token=token, check=False)
        git("remote", "add", "origin", remote, token=token)

    # 通过 http.extraheader 传递凭据，不把 token 写进 remote 或命令行 URL
    push = subprocess.run(
        ["git", "-C", str(ROOT), "-c", "http.extraheader=AUTHORIZATION: bearer " + token,
         "push", "-u", "origin", "main"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    push_out = redact((push.stdout or "") + (push.stderr or ""), token).strip()
    if push.returncode:
        raise SystemExit("推送失败：" + push_out[:600])
    print("推送完成：main")

    if a.skip_pages:
        print(f"仓库地址：https://github.com/{user}/{a.repo}")
        return

    code, p = api("POST", f"/repos/{user}/{a.repo}/pages", token,
                  {"source": {"branch": "main", "path": "/"}})
    if code == 201:
        print("Pages 已开启")
    elif code == 409:
        print("Pages 已存在，触发重建")
        api("PUT", f"/repos/{user}/{a.repo}/pages", token,
            {"source": {"branch": "main", "path": "/"}})
    else:
        print(f"Pages 开启返回 HTTP {code}：{p.get('message','')}（可稍后在仓库设置里手动开启）")

    link = f"https://{user}.github.io/{a.repo}/"
    for _ in range(12):
        code, s = api("GET", f"/repos/{user}/{a.repo}/pages", token)
        if code == 200 and s.get("status") == "built":
            print("Pages 构建完成：" + link)
            break
        time.sleep(5)
    else:
        print("Pages 仍在构建，稍后访问：" + link)
    print(f"仓库地址：https://github.com/{user}/{a.repo}")


if __name__ == "__main__":
    main()
