"""Publish a static page folder to a public HTTPS address on xhostd — no sign-up, no email.

    python publish.py <page-folder>

The first run opens an xhostd account for this computer by itself (an SSH key, no
email). Every page lives in ONE site of that account, each in a folder of its own:

    https://pages-<username>.xhostd.app/<page-name>/

An account nobody confirmed by email may be deleted 7 days after it was opened, so
a publish never promises more than that: when the account is older than
FRESH_DAYS, a new one is opened first and the page gets a new address. Before the
upload it writes ``share-link.json`` into the page folder ({url, valid_until}),
which the page's share menu reads.

Prints ONE JSON line: {"ok": true, "url": ..., "valid_until": ...} or
{"ok": false, "error": ...}. Never prints a token. Needs: python 3.9+, git,
ssh-keygen (OpenSSH 8.0+). Stdlib only.

State lives in ~/.config/xhostd/ (override with XHOSTD_STATE_DIR):
    key, key.pub   the account's SSH key — its only durable credential
    token          30-day API token (mode 0600)
    account.json   {"username", "registered_at"}
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.xhostd.com"
SITE = "pages"  # the one static app every page of this computer goes into
LIFETIME_DAYS = 7  # an unconfirmed account may be deleted after this
FRESH_DAYS = 6  # open a new account before the old one can expire under a new link
DEPLOY_POLL_SECONDS = 3
DEPLOY_MAX_POLLS = 100  # ~5 minutes; a static deploy takes seconds
SKIP = {".git", ".DS_Store", "Thumbs.db", "node_modules"}


class PublishError(Exception):
    pass


# ── state ──────────────────────────────────────────────────────────────────


def state_dir() -> Path:
    d = Path(os.environ.get("XHOSTD_STATE_DIR") or Path.home() / ".config" / "xhostd")
    d.mkdir(parents=True, exist_ok=True)
    try:
        d.chmod(0o700)
    except OSError:
        pass
    return d


def write_secret(path: Path, value: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, value.encode())
    finally:
        os.close(fd)


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# ── HTTP ───────────────────────────────────────────────────────────────────


def api(method: str, path: str, token: str | None = None, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"error": {"message": raw.decode(errors="replace")[:300]}}


def error_text(payload: dict) -> str:
    err = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(err, dict):
        return f"{err.get('code', '')}: {err.get('message', '')}".strip(": ")
    return str(payload)[:300]


# ── account ────────────────────────────────────────────────────────────────


def ssh_keygen(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    exe = shutil.which("ssh-keygen")
    if not exe:
        raise PublishError("ssh-keygen was not found (install OpenSSH 8.0 or later)")
    return subprocess.run([exe, *args], cwd=cwd, capture_output=True, text=True)


def sign(key: Path, namespace: str, message: str) -> str:
    with tempfile.TemporaryDirectory() as work:
        msg = Path(work) / "msg"
        msg.write_text(message, encoding="utf-8", newline="\n")
        done = ssh_keygen("-Y", "sign", "-f", str(key), "-n", namespace, str(msg))
        if done.returncode != 0:
            raise PublishError(f"could not sign with the SSH key: {done.stderr.strip()[:300]}")
        return (Path(work) / "msg.sig").read_text()


def register(sd: Path) -> str:
    """Open a fresh account with a fresh key; answer its token."""
    key = sd / "key"
    for old in (key, key.with_suffix(".pub")):
        if old.exists():
            old.replace(old.with_name(old.name + ".old"))
    done = ssh_keygen("-t", "ed25519", "-N", "", "-C", "flowpad-pages", "-f", str(key))
    if done.returncode != 0:
        raise PublishError(f"could not create an SSH key: {done.stderr.strip()[:300]}")
    ts = int(time.time())
    signature = sign(key, "xhostd-register", f"xhostd-register\n\n{ts}\n")
    status, r = api(
        "POST",
        "/registrations",
        body={
            "public_key": key.with_suffix(".pub").read_text().strip(),
            "timestamp": ts,
            "signature": signature,
            "label": "flowpad-pages",
        },
    )
    if status >= 300 or "token" not in r:
        raise PublishError(f"could not open an xhostd account ({status}) {error_text(r)}")
    write_secret(sd / "token", r["token"])
    (sd / "account.json").write_text(
        json.dumps({"username": r["username"], "registered_at": now().isoformat()}), encoding="utf-8"
    )
    return r["token"]


def login(sd: Path) -> str | None:
    """A fresh token from the existing key, or None when the account is gone."""
    key = sd / "key"
    if not key.exists():
        return None
    fp = ssh_keygen("-lf", str(key.with_suffix(".pub")))
    if fp.returncode != 0:
        return None
    fingerprint = fp.stdout.split()[1]  # "256 SHA256:... comment (ED25519)"
    ts = int(time.time())
    signature = sign(key, "xhostd-login", f"xhostd-login\n{fingerprint}\n{ts}\n")
    status, r = api(
        "POST",
        "/auth/ssh-key",
        body={"public_key": key.with_suffix(".pub").read_text().strip(), "timestamp": ts, "signature": signature},
    )
    if status >= 300 or "token" not in r:
        return None
    write_secret(sd / "token", r["token"])
    return r["token"]


def account(sd: Path) -> tuple[str, str, dt.datetime]:
    """(token, username, registered_at) of a live account young enough to promise a week."""
    info_path = sd / "account.json"
    info = json.loads(info_path.read_text()) if info_path.exists() else None
    registered = dt.datetime.fromisoformat(info["registered_at"]) if info else None
    if info is None or registered is None or now() - registered > dt.timedelta(days=FRESH_DAYS):
        token = register(sd)
    else:
        token_path = sd / "token"
        token = token_path.read_text().strip() if token_path.exists() else ""
        if not token or api("GET", "/apps", token)[0] in (401, 403):
            token = login(sd) or register(sd)
    info = json.loads(info_path.read_text())
    return token, info["username"], dt.datetime.fromisoformat(info["registered_at"])


# ── site ───────────────────────────────────────────────────────────────────


def site(token: str) -> tuple[dict, dict]:
    """The account's one static app and its prod channel, created on first use."""
    status, apps = api("GET", "/apps", token)
    if status >= 300:
        raise PublishError(f"could not list sites ({status}) {error_text(apps)}")
    app = next((a for a in apps.get("apps", []) if a.get("name") == SITE), None)
    if app is None:
        status, app = api("POST", "/apps", token, {"name": SITE, "template": "static", "branch": "master"})
        if status >= 300:
            raise PublishError(f"could not create the site ({status}) {error_text(app)}")
    status, full = api("GET", f"/apps/{app['id']}", token)
    if status < 300:
        app = full
    channels = app.get("channels") or []
    prod = next((c for c in channels if c.get("name") == "prod"), channels[0] if channels else None)
    if prod is None:
        raise PublishError("the site has no prod channel")
    return app, prod


def git(*args: str, cwd: Path, token: str) -> subprocess.CompletedProcess:
    exe = shutil.which("git")
    if not exe:
        raise PublishError("git was not found")
    env = dict(os.environ)
    # The token rides in the environment, never in argv or a remote URL.
    env.update(
        GIT_CONFIG_COUNT="1",
        GIT_CONFIG_KEY_0="http.extraHeader",
        GIT_CONFIG_VALUE_0=f"Authorization: Bearer {token}",
        GIT_TERMINAL_PROMPT="0",
        GCM_INTERACTIVE="never",
    )
    return subprocess.run(
        [exe, "-c", "credential.helper=", "-c", "core.autocrlf=false", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
    )


def upload(token: str, repo_url: str, page: Path, name: str) -> None:
    """Replace the folder ``name/`` of the site with ``page``, keeping every other page."""
    for attempt in range(3):
        with tempfile.TemporaryDirectory() as work:
            repo = Path(work)
            git("init", "-q", cwd=repo, token=token)
            fetched = git("fetch", "-q", repo_url, "master", cwd=repo, token=token)
            if fetched.returncode == 0:
                git("checkout", "-q", "-B", "master", "FETCH_HEAD", cwd=repo, token=token)
            else:
                git("checkout", "-q", "--orphan", "master", cwd=repo, token=token)
            target = repo / name
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(page, target, ignore=shutil.ignore_patterns(*SKIP))
            index = repo / "index.html"
            if not index.exists():
                index.write_text(
                    '<!doctype html><meta charset="utf-8"><title>Pages</title>'
                    "<p>Made with Flowpad.</p>",
                    encoding="utf-8",
                )
            git("add", "-A", cwd=repo, token=token)
            committed = git(
                "-c", "user.name=Flowpad", "-c", "user.email=pages@flowpad.invalid",
                "commit", "-q", "-m", f"publish {name}",
                cwd=repo, token=token,
            )
            if committed.returncode != 0 and "nothing to commit" not in (committed.stdout + committed.stderr):
                raise PublishError(f"could not commit: {committed.stderr.strip()[:300]}")
            pushed = git("push", "-q", repo_url, "HEAD:master", cwd=repo, token=token)
            if pushed.returncode == 0:
                return
            last = pushed.stderr.strip()
        time.sleep(1 + attempt)  # another publish landed first: fetch again and retry
    raise PublishError(f"could not upload: {last[:300]}")


def deploy(token: str, app: dict, channel: dict) -> None:
    base = f"/apps/{app['id']}/channels/{channel['id']}"
    status, d = api("POST", f"{base}/deploy", token, {"ref": "master"})
    if status >= 300:
        raise PublishError(f"could not start the deploy ({status}) {error_text(d)}")
    deploy_id = d["deploy_id"]
    for _ in range(DEPLOY_MAX_POLLS):
        status, log = api("GET", f"{base}/logs?deploy={deploy_id}&max_bytes=2000", token)
        state = log.get("status") if status < 300 else None
        if state == "success":
            return
        if state == "superseded" and log.get("superseded_by"):
            deploy_id = log["superseded_by"]
        elif state in ("failed", "cancelled"):
            raise PublishError(f"the deploy {state}: {str(log.get('log', ''))[-300:]}")
        time.sleep(DEPLOY_POLL_SECONDS)
    raise PublishError("the deploy did not finish")


def page_name(folder: Path) -> str:
    name = re.sub(r"[^a-z0-9-]+", "-", folder.name.lower()).strip("-")
    return name or "page"


def main() -> int:
    if len(sys.argv) != 2:
        print(json.dumps({"ok": False, "error": "usage: publish.py <page-folder>"}))
        return 2
    page = Path(sys.argv[1]).resolve()
    if not (page / "index.html").is_file():
        print(json.dumps({"ok": False, "error": f"{page} has no index.html"}))
        return 2
    try:
        sd = state_dir()
        token, username, registered = account(sd)
        app, channel = site(token)
        name = page_name(page)
        host = channel.get("hostname") or f"{SITE}-{username}.xhostd.app"
        url = f"https://{host}/{name}/"
        valid_until = (registered + dt.timedelta(days=LIFETIME_DAYS)).date().isoformat()
        (page / "share-link.json").write_text(
            json.dumps({"url": url, "valid_until": valid_until}, ensure_ascii=False), encoding="utf-8"
        )
        upload(token, app["repo_url"], page, name)
        deploy(token, app, channel)
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                live = resp.status == 200
        except urllib.error.URLError:
            live = False
        print(json.dumps({"ok": True, "url": url, "valid_until": valid_until, "live": live}))
        return 0
    except PublishError as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
