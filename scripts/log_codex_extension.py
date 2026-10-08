#!/usr/bin/env python3
"""
Codex IDE extension log scanner.

Codex in VS Code/Cursor stores local JSONL transcripts under:
    ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl

The IDE extension does not reliably execute the repo .codex/hooks.json hook,
so this script sweeps those transcripts before submit, similar to the
Antigravity scanner. It logs explicit user prompts from extension sessions
that belong to the current repo.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

VN_TZ = timezone(timedelta(hours=7))
CODEX_SESSIONS_DIR = Path.home() / ".codex" / "sessions"
OUTPUT_TOOL_NAME = "codex"
LEGACY_TOOL_NAMES = {"codex", "codex-extension"}

BOOTSTRAP_PREFIXES = (
    "<recommended_plugins>",
    "<environment_context>",
    "<permissions instructions>",
    "<collaboration_mode>",
    "<apps_instructions>",
    "<skills_instructions>",
    "The following is the Codex agent history",
)


def git(cmd: str) -> str:
    try:
        return subprocess.check_output(
            cmd.split(), shell=False, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return ""


def _normalize(p: str) -> str:
    if not p:
        return ""
    return p.strip().lower().replace("/", "\\").rstrip("\\")


def _matches_repo(path: str, repo_root_n: str) -> bool:
    p = _normalize(path)
    if not p or not repo_root_n:
        return False
    return (
        p == repo_root_n
        or p.startswith(repo_root_n + "\\")
        or repo_root_n.startswith(p + "\\")
    )


def _parse_ts(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _to_vn_iso(ts: str) -> str:
    dt = _parse_ts(ts)
    if not dt:
        return datetime.now(VN_TZ).isoformat()
    return dt.astimezone(VN_TZ).isoformat()


def _text_from_message(payload: dict) -> str:
    parts = []
    for part in payload.get("content") or []:
        if isinstance(part, dict) and part.get("type") == "input_text":
            text = part.get("text", "")
            if text:
                parts.append(text)
    return "".join(parts).strip()


def _is_bootstrap(text: str) -> bool:
    stripped = text.lstrip()
    return any(stripped.startswith(prefix) for prefix in BOOTSTRAP_PREFIXES)


def _transcript_paths(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(root.glob("**/rollout-*.jsonl"))


def _logged_keys(log_dir: Path) -> set[str]:
    keys: set[str] = set()
    candidates = []
    live = log_dir / "session.jsonl"
    if live.exists():
        candidates.append(live)
    archive = log_dir / "archive"
    if archive.exists():
        candidates.extend(sorted(archive.glob("*.jsonl")))

    for path in candidates:
        try:
            with open(path, encoding="utf-8-sig") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if entry.get("tool") not in LEGACY_TOOL_NAMES:
                        continue
                    entry_id = entry.get("entry_id")
                    if entry_id:
                        keys.add(entry_id)
                    session_id = entry.get("session_id")
                    turn_id = entry.get("turn_id")
                    if session_id and turn_id:
                        keys.add(f"codex-extension-{session_id}-{turn_id}")
        except OSError:
            continue
    return keys


def iter_user_prompts(transcript: Path, cutoff: datetime | None,
                      repo_root_n: str, no_repo_filter: bool):
    session_id = ""
    model = ""
    is_extension_session = False
    transcript_cwds: set[str] = set()
    user_messages: list[dict] = []

    try:
        with open(transcript, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                typ = entry.get("type")
                payload = entry.get("payload") or {}

                if typ == "session_meta":
                    session_id = payload.get("session_id") or payload.get("id") or session_id
                    originator = payload.get("originator")
                    source = payload.get("source")
                    is_extension_session = (
                        originator == "codex_vscode" or source == "vscode"
                    )
                    cwd = payload.get("cwd")
                    if isinstance(cwd, str):
                        transcript_cwds.add(cwd)
                    continue

                if typ == "turn_context":
                    model = payload.get("model") or model
                    cwd = payload.get("cwd")
                    if isinstance(cwd, str):
                        transcript_cwds.add(cwd)
                    for root in payload.get("workspace_roots") or []:
                        if isinstance(root, str):
                            transcript_cwds.add(root)
                    continue

                if typ != "response_item":
                    continue
                if payload.get("type") != "message" or payload.get("role") != "user":
                    continue

                text = _text_from_message(payload)
                if len(text) < 2 or _is_bootstrap(text):
                    continue

                ts = entry.get("timestamp") or ""
                dt = _parse_ts(ts)
                if cutoff and dt and dt < cutoff:
                    continue

                meta = payload.get("internal_chat_message_metadata_passthrough") or {}
                turn_id = meta.get("turn_id") or payload.get("id") or ""
                user_messages.append({
                    "timestamp": ts,
                    "turn_id": turn_id,
                    "model": model,
                    "prompt": text,
                })
    except OSError:
        return

    if not is_extension_session:
        return

    if not no_repo_filter:
        if not any(_matches_repo(cwd, repo_root_n) for cwd in transcript_cwds):
            return

    if not session_id:
        session_id = transcript.stem.removeprefix("rollout-")

    seen_turns: set[str] = set()
    for msg in user_messages:
        turn_id = msg["turn_id"]
        if turn_id and turn_id in seen_turns:
            continue
        if turn_id:
            seen_turns.add(turn_id)
        yield {
            **msg,
            "session_id": session_id,
            "transcript_path": str(transcript),
        }


def build_entry(msg: dict, repo: str, branch: str, commit: str,
                student: str) -> dict:
    session_id = msg["session_id"]
    turn_id = msg["turn_id"]
    entry_id = f"codex-extension-{session_id}-{turn_id}" if turn_id else (
        "codex-extension-"
        f"{session_id}-{hashlib.sha1(msg['prompt'].encode('utf-8')).hexdigest()[:12]}"
    )
    return {
        "ts": _to_vn_iso(msg["timestamp"]),
        "tool": OUTPUT_TOOL_NAME,
        "event": "UserPromptSubmit",
        "entry_id": entry_id,
        "session_id": session_id,
        "model": msg["model"],
        "repo": repo,
        "branch": branch,
        "commit": commit,
        "student": student,
        "prompt": msg["prompt"][:1000],
        "turn_id": turn_id,
        "transcript_path": msg["transcript_path"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract Codex IDE extension prompts into .ai-log/session.jsonl."
    )
    parser.add_argument("--auto", action="store_true",
                        help="Default mode: scan recent transcripts.")
    parser.add_argument("--hours", type=int, default=24,
                        help="Window in hours when scanning (default: 24).")
    parser.add_argument("--all", action="store_true",
                        help="Ignore the time window; scan all transcripts.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be logged, do not write.")
    parser.add_argument("--no-repo-filter", action="store_true",
                        help="Do not filter transcripts by current repo.")
    parser.add_argument("--sessions-dir",
                        help="Override Codex sessions directory.")
    args = parser.parse_args()

    sessions_dir = Path(args.sessions_dir) if args.sessions_dir else CODEX_SESSIONS_DIR
    paths = _transcript_paths(sessions_dir)
    if not paths:
        print(f"[codex-extension-log] No Codex transcripts found in {sessions_dir}.",
              file=sys.stderr)
        sys.exit(0)

    cutoff = None
    if not args.all:
        cutoff = datetime.now(tz=VN_TZ) - timedelta(hours=args.hours)

    log_dir = Path(os.environ.get("AI_LOG_DIR", ".ai-log"))
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "session.jsonl"
    logged = _logged_keys(log_dir)

    repo_root_n = "" if args.no_repo_filter else _normalize(str(Path.cwd()))
    repo = git("git remote get-url origin").split("/")[-1].replace(".git", "")
    branch = git("git rev-parse --abbrev-ref HEAD")
    commit = git("git rev-parse --short HEAD")
    student = git("git config user.email") or os.environ.get(
        "USERNAME", os.environ.get("USER", "unknown"))

    new_entries: list[dict] = []
    for transcript in paths:
        for msg in iter_user_prompts(transcript, cutoff, repo_root_n,
                                     args.no_repo_filter):
            entry = build_entry(msg, repo or Path.cwd().name, branch, commit,
                                student)
            if entry["entry_id"] in logged:
                continue
            new_entries.append(entry)
            logged.add(entry["entry_id"])

    if not new_entries:
        scope = "all" if args.all else f"{args.hours}h"
        repo_note = "any repo" if args.no_repo_filter else f"repo={repo_root_n or '(unknown)'}"
        print(f"[codex-extension-log] No new prompts ({repo_note}, window={scope}).",
              file=sys.stderr)
        sys.exit(0)

    if args.dry_run:
        print(f"\n[codex-extension-log] DRY RUN - would log "
              f"{len(new_entries)} entries:\n")
        for entry in new_entries:
            preview = entry["prompt"].replace("\n", " ")[:120]
            print(f"  [{entry['ts'][:19]}] {preview}")
        sys.exit(0)

    with open(log_file, "a", encoding="utf-8") as f:
        for entry in new_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"[codex-extension-log] Logged {len(new_entries)} prompt(s) from "
          f"Codex IDE extension.", file=sys.stderr)


if __name__ == "__main__":
    main()
