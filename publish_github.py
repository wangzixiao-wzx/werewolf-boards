#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把本目录发布到 GitHub 并开启 Pages（仅标准库，纯 REST API）。

为什么不用 git push：某些网络环境（HTTP 代理 / 受限终端）下 git 的
https 传输会挂起或反复索要用户名，而 REST API 通道正常。本脚本直接
通过 GitHub Git Data API 写入完整目录树，不依赖任何 git 网络操作。

Token 只通过 --token 或环境变量 GITHUB_TOKEN 传入，绝不写进仓库文件、
remote URL、git config 或日志输出。需要 classic PAT 的 repo 权限。

用法：
    python publish_github.py --token <PAT>
    GITHUB_TOKEN=<PAT> python publish_github.py
    python publish_github.py --token <PAT> --repo werewolf-boards --skip-pages
    GITHUB_TOKEN=<PAT> python publish_github.py --dir ../werewolf-db-public --repo werewolf-db
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
API = "https://api.github.com"


def say(*a):
    print(*a, flush=True)


class GitHub:
    def __init__(self, token, user, repo):
        self.token = token
        self.user = user
        self.repo = repo

    def __call__(self, method, path, payload=None, timeout=30, absolute=False):
        url = path if absolute else API + path
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(url, data=body, method=method, headers={
            "Authorization": "Bearer " + self.token,
            "Accept": "application/vnd.github+json",
            "User-Agent": "werewolf-boards-publisher",
            "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read().decode("utf-8")
                return r.status, (json.loads(raw) if raw.strip() else {})
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            try:
                return e.code, json.loads(raw)
            except ValueError:
                return e.code, {"message": raw[:200]}
        except Exception as e:
            return 0, {"message": type(e).__name__ + ": " + str(e)[:160]}

    def repo_path(self, suffix):
        return f"/repos/{self.user}/{self.repo}{suffix}"


def git(*args, check=False):
    r = subprocess.run(["git", "-C", str(ROOT)] + list(args),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    if check and r.returncode:
        raise RuntimeError("git " + " ".join(args[:2]) + " 失败：" + out[:300])
    return r.returncode, out


def b64(path):
    return base64.b64encode(path.read_bytes()).decode("ascii")


def align_local(sha):
    """保持本地工作区干净。

    远端提交由 API 创建，本地对象库里通常没有这个 commit 对象，
    直接 update-ref 会失败。因此：能对齐就对齐，否则把本地改动提交一次。
    发布流程完全走 REST API，不依赖 git push，本地与远端 commit sha 不同不影响使用。
    """
    ok, _ = git("cat-file", "-e", sha + "^{commit}")
    if ok == 0:
        git("update-ref", "refs/heads/main", sha)
        git("update-ref", "refs/remotes/origin/main", sha)
    else:
        _, st = git("status", "--porcelain")
        if st:
            git("commit", "-m", "更新版型库数据")


def main():
    global ROOT
    ap = argparse.ArgumentParser(description="发布静态站到 GitHub Pages")
    ap.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""), help="GitHub PAT")
    ap.add_argument("--user", default="", help="GitHub 用户名（默认取 token 所属账号）")
    ap.add_argument("--repo", default="werewolf-boards", help="仓库名")
    ap.add_argument("--dir", default=str(ROOT), help="要发布的目录（默认脚本所在目录）")
    ap.add_argument("--skip-pages", action="store_true", help="只同步仓库，不碰 Pages 设置")
    a = ap.parse_args()
    ROOT = Path(a.dir).resolve()

    token = (a.token or "").strip()
    if not token:
        raise SystemExit("缺少 token：用 --token 传入，或设置环境变量 GITHUB_TOKEN")

    code, me = GitHub(token, "", "")("GET", "/user")
    if code != 200:
        raise SystemExit(f"token 无效（HTTP {code}）：{me.get('message', '')}")
    user = a.user or me["login"]
    gh = GitHub(token, user, a.repo)
    say(f"账号：{user}｜仓库：{a.repo}")

    code, r = gh("POST", "/user/repos", {
        "name": a.repo,
        "description": "狼人杀版型库：板子配置 / 身份构成 / 特殊规则（只读、零依赖）",
        "homepage": f"https://{user}.github.io/{a.repo}/",
        "private": False, "has_issues": False, "has_wiki": False, "has_projects": False,
    })
    if code == 201:
        say("仓库已创建")
    elif code == 422:
        say("仓库已存在，复用")
    else:
        raise SystemExit(f"创建仓库失败（HTTP {code}）：{r.get('message', '')}")

    # 本地暂存区与工作区对齐（纯本地操作，不联网）
    if (ROOT / ".git").exists():
        git("add", "-A")
    _, listing = git("ls-files", "-z")
    paths = [p for p in listing.split("\0") if p.strip()]
    if not paths:
        raise SystemExit("没有可发布的文件")
    say(f"本地文件 {len(paths)} 个")

    # 空仓库（无任何 ref）时 Git Data API 会返回 409，先用 Contents API 落一个初始提交
    code, ref = gh("GET", gh.repo_path("/git/ref/heads/main"))
    if code == 200:
        head_sha = ref["object"]["sha"]
    else:
        seed = ".gitignore" if ".gitignore" in paths else paths[0]
        code, j = gh("PUT", gh.repo_path("/contents/" + seed),
                     {"message": "初始化仓库", "content": b64(ROOT / seed), "branch": "main"})
        if code not in (200, 201):
            raise SystemExit(f"初始提交失败（HTTP {code}）：{j.get('message', '')}")
        head_sha = j["commit"]["sha"]
        say("已创建 main 分支（初始提交）")

    # 上传全部文件为 blob，构造完整目录树
    tree = []
    for f in paths:
        code, j = gh("POST", gh.repo_path("/git/blobs"),
                     {"content": b64(ROOT / f), "encoding": "base64"})
        if code not in (200, 201) or "sha" not in j:
            raise SystemExit(f"上传 {f} 失败（HTTP {code}）：{j.get('message', '')}")
        tree.append({"path": f, "mode": "100644", "type": "blob", "sha": j["sha"]})
    code, j = gh("POST", gh.repo_path("/git/trees"), {"tree": tree})
    if code != 201:
        raise SystemExit(f"创建目录树失败（HTTP {code}）：{j.get('message', '')}")
    tree_sha = j["sha"]

    code, head = gh("GET", gh.repo_path("/git/commits/" + head_sha))
    if code == 200 and head.get("tree", {}).get("sha") == tree_sha:
        say("远端内容与本地完全一致，跳过提交")
    else:
        code, j = gh("POST", gh.repo_path("/git/commits"), {
            "message": "更新版型库数据", "tree": tree_sha, "parents": [head_sha],
        })
        if code != 201:
            raise SystemExit(f"创建提交失败（HTTP {code}）：{j.get('message', '')}")
        head_sha = j["sha"]
        code, j = gh("PATCH", gh.repo_path("/git/refs/heads/main"), {"sha": head_sha})
        if code != 200:
            raise SystemExit(f"更新 main 失败（HTTP {code}）：{j.get('message', '')}")
        say("已推送 main（" + head_sha[:8] + "）")

    if (ROOT / ".git").exists():
        align_local(head_sha)

    link = f"https://{user}.github.io/{a.repo}/"
    if a.skip_pages:
        say(f"仓库地址：https://github.com/{user}/{a.repo}")
        return

    code, p = gh("GET", gh.repo_path("/pages"))
    if code == 404:
        code, p = gh("POST", gh.repo_path("/pages"), {"source": {"branch": "main", "path": "/"}})
        say("Pages 已开启" if code == 201 else f"Pages 开启返回 HTTP {code}：{p.get('message', '')}")
    elif code == 200:
        src = p.get("source", {})
        if src.get("branch") != "main" or src.get("path") not in ("/", ""):
            gh("PUT", gh.repo_path("/pages"), {"source": {"branch": "main", "path": "/"}})
            say("Pages 配置已修正为 main / root")
        else:
            say("Pages 配置已是 main / root")
    else:
        say(f"Pages 查询返回 HTTP {code}（可稍后在仓库设置里手动开启）")

    for _ in range(8):
        code, s = gh("GET", gh.repo_path("/pages"))
        if code == 200 and s.get("status") == "built":
            say("Pages 构建完成：" + link)
            break
        time.sleep(3)
    else:
        say("Pages 仍在构建，稍后访问：" + link)
    say(f"仓库地址：https://github.com/{user}/{a.repo}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
