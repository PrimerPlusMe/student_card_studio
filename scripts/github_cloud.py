"""GitHub Actions helper. Never prints or writes authentication secrets."""
from __future__ import annotations
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request


def token_from_environment():
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    try:
        result = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                                text=True, capture_output=True, timeout=20, env=env)
        fields = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
        return fields.get("password")
    except (OSError, subprocess.TimeoutExpired):
        return None


def api(token, path, data=None, method=None):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "StudentCardStudio-build"}
    request = urllib.request.Request("https://api.github.com" + path, headers=headers,
                                     data=None if data is None else json.dumps(data).encode(), method=method)
    with urllib.request.urlopen(request, timeout=40) as response:
        payload = response.read()
        return json.loads(payload) if payload else {}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["check", "create", "runs", "dispatch"])
    parser.add_argument("--repo", default="student-card-studio-20261101")
    args = parser.parse_args()
    token = token_from_environment()
    if not token:
        print("GitHub authentication unavailable. Connect GitHub or run Git Credential Manager login first.")
        return 2
    user = api(token, "/user")
    owner = user["login"]
    print(f"Authenticated GitHub account: {owner}")
    if args.action == "check":
        return 0
    name = args.repo if "/" not in args.repo else args.repo.split("/", 1)[1]
    repository = args.repo if "/" in args.repo else f"{owner}/{name}"
    if args.action == "create":
        result = api(token, "/user/repos", {"name": name, "private": True, "description": "Offline student card desktop application and dual-platform builds"})
        print(json.dumps({"repo": result["full_name"], "private": result["private"], "url": result["html_url"]}))
        project = Path(__file__).resolve().parents[1]
        subprocess.run(["git", "init", "-b", "main"], cwd=project, check=True)
        subprocess.run(["git", "config", "user.name", user.get("name") or owner], cwd=project, check=True)
        subprocess.run(["git", "config", "user.email", f"{user['id']}+{owner}@users.noreply.github.com"], cwd=project, check=True)
        subprocess.run(["git", "add", "."], cwd=project, check=True)
        subprocess.run(["git", "commit", "-m", "Build student card desktop app with validated cross-platform workflows"], cwd=project, check=True)
        subprocess.run(["git", "remote", "add", "origin", result["clone_url"]], cwd=project, check=True)
        auth = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env = dict(os.environ, GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="http.https://github.com/.extraheader", GIT_CONFIG_VALUE_0="AUTHORIZATION: basic " + auth, GIT_TERMINAL_PROMPT="0")
        subprocess.run(["git", "push", "-u", "origin", "main"], cwd=project, env=env, check=True)
    elif args.action == "dispatch":
        api(token, f"/repos/{repository}/actions/workflows/build.yml/dispatches", {"ref": "main"})
        print("Cloud build dispatched")
    elif args.action == "runs":
        result = api(token, f"/repos/{repository}/actions/runs?per_page=5")
        print(json.dumps([{"id": r["id"], "url": r["html_url"], "status": r["status"], "conclusion": r["conclusion"]} for r in result.get("workflow_runs", [])], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as exc:
        print(f"GitHub request failed: HTTP {exc.code} {exc.reason}")
        raise SystemExit(3)
