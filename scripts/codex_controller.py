#!/usr/bin/env python3
"""Resumable local Codex -> tests -> review -> GitHub PR migration runner."""
from __future__ import annotations

import argparse
import contextlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / ".codex-controller"
QUEUE = ROOT / "config" / "migration_queue.json"
PROTECTED = {"scripts/codex_controller.py", "config/migration_queue.json",
             "tests/test_codex_controller.py", ".github/workflows/codex-controller.yml"}
SCHEMA = {"type": "object", "properties": {
    "approved": {"type": "boolean"},
    "blocking_findings": {"type": "array", "items": {"type": "string"}},
    "summary": {"type": "string"}},
    "required": ["approved", "blocking_findings", "summary"], "additionalProperties": False}


class GateError(RuntimeError):
    pass


def save(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)


def load_queue(path: Path = QUEUE) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    tasks = data["tasks"]
    keys = [task["id"] for task in tasks]
    if not keys or len(keys) != len(set(keys)):
        raise GateError("Migration task IDs must be unique and nonempty")
    if not data.get("required_workflows") or not data.get("local_checks"):
        raise GateError("Required local and CI gates must be configured")
    for task in tasks:
        if not task.get("objective") or not task.get("acceptance") or not task.get("title"):
            raise GateError(f"Incomplete task specification: {task}")
    return data


def decide_checks(checks: list[dict], required: list[str]) -> str:
    """Fail closed: missing or skipped workflows cannot count as success."""
    if not checks:
        return "pending"
    found: dict[str, list[str]] = {}
    for item in checks:
        name = item.get("workflow") or item.get("name")
        found.setdefault(name, []).append(str(item.get("bucket", "")).lower())
    if any(name not in found for name in required):
        return "pending"
    if any(v in ("fail", "cancel") for values in found.values() for v in values):
        return "failed"
    if all(v == "pass" for values in found.values() for v in values):
        return "passed"
    return "pending"


def check_protected(paths: set[str]) -> None:
    blocked = {p.replace("\\", "/") for p in paths} & PROTECTED
    if blocked:
        raise GateError("Codex modified protected controller/queue files: " + ", ".join(sorted(blocked)))


@contextlib.contextmanager
def single_runner():
    """Native advisory lock; released by the OS after a crash."""
    DATA.mkdir(parents=True, exist_ok=True)
    with (DATA / "controller.lock").open("a+b") as stream:
        stream.seek(0)
        stream.write(b"x")
        stream.flush()
        try:
            if os.name == "nt":
                import msvcrt
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise GateError("Controller already running") from exc
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class Controller:
    def __init__(self, args, config, executor=subprocess.run):
        self.args, self.config, self.executor = args, config, executor
        self.path = DATA / "state.json"
        self.state = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {"tasks": {}}
        self.repo = config["repository"]
        self.max_attempts = config.get("max_attempts", 3)
        self.poll = config.get("poll_seconds", 30)

    def update(self, key, **fields):
        rec = self.state["tasks"].setdefault(key, {"phase": "PENDING", "attempts": 0})
        rec.update(fields)
        save(self.path, self.state)
        print(f"{key} / {rec['phase']} / attempts {rec['attempts']}", flush=True)
        return rec

    def run_cmd(self, command, *, stdin=None, timeout=1200, valid=(0,), label="command"):
        command = [str(c) for c in command]
        result = self.executor(command, cwd=str(ROOT), capture_output=True, text=True,
                               input=stdin, encoding="utf-8", errors="replace", timeout=timeout)
        DATA.mkdir(parents=True, exist_ok=True)
        with (DATA / "history.log").open("a", encoding="utf-8") as output:
            output.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] {label}\n")
            output.write((result.stdout or "")[-15000:] + "\n" + (result.stderr or "")[-6000:])
        if result.returncode not in valid:
            raise GateError(f"{label} failed ({result.returncode}): {(result.stderr or result.stdout)[-1600:]}")
        return result.stdout

    def gh(self, argv, valid=(0,)):
        raw = self.run_cmd(["gh", *argv, "--repo", self.repo], valid=valid, label="gh " + argv[0])
        try:
            return json.loads(raw)
        except ValueError as exc:
            raise GateError("GitHub CLI returned invalid JSON") from exc

    def preflight(self):
        for command in ("git", "gh", "codex", "npm", "node"):
            if not shutil.which(command):
                raise GateError(f"Install required CLI and add to PATH: {command}")
        source = os.getenv("ROBAS_SOURCE_DIR", "")
        if not source or not Path(source).is_dir():
            raise GateError("Set ROBAS_SOURCE_DIR to an authorized, extracted RoBAS source folder")
        if Path(source).resolve().is_relative_to(ROOT.resolve()):
            raise GateError("Private RoBAS source must be OUTSIDE the public Git repository")
        self.run_cmd(["git", "rev-parse", "--show-toplevel"], label="git preflight")
        self.run_cmd(["gh", "auth", "status"], label="GitHub login")
        self.run_cmd(["codex", "--version"], label="Codex CLI")
        self.run_cmd([sys.executable, "-c", "import cadquery,ezdxf,svgwrite"], label="CadQuery dependencies")
        self.clean_tree()

    def clean_tree(self):
        changed = self.run_cmd(["git", "status", "--porcelain"], label="worktree state")
        if changed.strip():
            raise GateError("Uncommitted files present; refusing to overwrite: " + changed[-600:])

    def task_branch(self, task):
        name = f"codex/{task['id'].lower()}"
        self.clean_tree()
        self.run_cmd(["git", "fetch", "origin", "main"], label="fetch main")
        exists = self.run_cmd(["git", "branch", "--list", name], label="find task branch")
        if exists.strip():
            self.run_cmd(["git", "switch", name], label="resume existing branch")
        else:
            self.run_cmd(["git", "switch", "main"], label="switch main")
            self.run_cmd(["git", "merge", "--ff-only", "origin/main"], label="fast-forward main")
            self.run_cmd(["git", "switch", "-c", name], label="create task branch")
        return name

    def find_pr(self, branch):
        results = self.gh(["pr", "list", "--head", branch, "--state", "all",
                           "--json", "number,state,mergedAt,isDraft,url,headRefOid"])
        return next((pr for pr in results if pr["state"] == "OPEN" or pr.get("mergedAt")), None)

    def codex(self, task, message, phase):
        answer = DATA / f"{task['id']}-{phase}.txt"
        command = ["codex", "exec", "--sandbox", "read-only" if phase == "review" else "workspace-write",
                   "--ask-for-approval", "never", "--output-last-message", str(answer)]
        if phase == "review":
            schema = DATA / "review-schema.json"
            save(schema, SCHEMA)
            command.extend(["--output-schema", str(schema)])
        command.append("-")
        self.run_cmd(command, stdin=message, timeout=self.config.get("codex_timeout_seconds", 3600),
                     label="Codex " + phase)
        if not answer.is_file():
            raise GateError("Codex did not produce a final answer")
        return answer.read_text(encoding="utf-8")

    def develop(self, task, previous):
        message = f"""Task {task['id']}: {task['objective']}
Acceptance: {json.dumps(task['acceptance'], ensure_ascii=False)}.
Read AGENTS.md and inspect authorized reference C# files in {os.environ['ROBAS_SOURCE_DIR']}.
Preserve existing sliding-bearing behavior; convert geometric units explicitly to mm.
Make only task-scoped changes; no C# source, Eyeshot binaries or RoBAS ZIP in this public repo.
Do not change controller, migration queue, its tests, or its CI workflow.
Do not git commit, push, merge, run gh, or access credentials. Controller owns GitHub actions.
Run targeted tests. Record reproducible CAD evidence at docs/migration/evidence/{task['id']}.md.
Never hide failures, weaken tests or invent engineering parameters.
If ambiguity, licensing uncertainty or unresolvable geometry is found, output BLOCKED: with reasons.
Previous validation feedback: {previous[:3000]}"""
        result = self.codex(task, message, "develop")
        if "BLOCKED:" in result:
            raise GateError("Codex reported an engineering or source-license blocker: " + result[-1200:])

    def local_gates(self):
        for i, argv in enumerate(self.config["local_checks"]):
            try:
                self.run_cmd(argv, timeout=self.config.get("test_timeout_seconds", 1800),
                             label=f"local acceptance {i+1}")
            except GateError as error:
                return str(error)
        return ""

    def commit_and_review(self, task):
        tracked = self.run_cmd(["git", "diff", "--name-only"], label="modified files").splitlines()
        staged = self.run_cmd(["git", "diff", "--cached", "--name-only"], label="staged files").splitlines()
        added = self.run_cmd(["git", "ls-files", "--others", "--exclude-standard"], label="new files").splitlines()
        names = {s.strip() for s in tracked + staged + added if s.strip()}
        check_protected(names)
        if not names:
            raise GateError("Codex produced no changed files")
        self.run_cmd(["git", "add", "--", *sorted(names)], label="stage code")
        self.run_cmd(["git", "commit", "-m", f"{task['id']}: {task['title']}"], label="commit task")
        prompt = (f"Independently review migration {task['id']} without editing files. "
                  "Read AGENTS.md, the task evidence, and inspect git diff origin/main...HEAD. "
                  "Inspect source licensing, formula/unit validity, rolling-element geometry, "
                  "B-Rep correctness, test quality and sliding-bearing regressions. "
                  "Do not trust just test exit codes. If evidence is insufficient, block. "
                  "Return strictly JSON: approved boolean, blocking_findings list of strings, summary string.")
        try:
            decision = json.loads(self.codex(task, prompt, "review"))
        except ValueError as exc:
            raise GateError("Independent Codex review failed JSON validation") from exc
        if decision.get("approved") is not True or decision.get("blocking_findings"):
            return "; ".join(decision.get("blocking_findings", ["Review not approved"])) or "Review not approved"
        return ""

    def publish(self, task, branch, pr):
        self.run_cmd(["git", "push", "-u", "origin", branch], label="push branch")
        if pr:
            return pr
        body = (f"Codex migration {task['id']}\n\n{task['objective']}\n\nAcceptance:\n" +
                "\n".join("- " + x for x in task["acceptance"]) +
                f"\n\nEvidence: docs/migration/evidence/{task['id']}.md\n\n" +
                "Do not merge without required CI and independent review.")
        self.run_cmd(["gh", "pr", "create", "--repo", self.repo, "--head", branch,
                      "--base", "main", "--title", f"{task['id']}: {task['title']}",
                      "--body", body, "--draft"], label="create draft PR")
        pr = self.find_pr(branch)
        if not pr:
            raise GateError("Could not find PR after creation; inspect GitHub before retry")
        return pr

    def ci_gate(self, number):
        deadline = time.monotonic() + self.config.get("ci_timeout_seconds", 2700)
        while time.monotonic() < deadline:
            try:
                checks = self.gh(["pr", "checks", str(number), "--json", "name,bucket,workflow"],
                                 valid=(0, 1, 8))
                outcome = decide_checks(checks, self.config["required_workflows"])
            except GateError:
                outcome = "pending"
            if outcome != "pending":
                return outcome
            time.sleep(self.poll)
        return "timeout"

    def inspect_pr(self, task, record, pr):
        if pr.get("mergedAt"):
            self.update(task["id"], phase="COMPLETE", pr=pr["number"], error="")
            return True
        if pr["state"] != "OPEN":
            raise GateError("PR closed without merging")
        if record["phase"] == "WAITING_MERGE":
            if self.args.auto_merge:
                raise GateError("Existing manual-approval PR cannot silently become auto-merge")
            if not self.args.watch:
                return False
            time.sleep(self.poll)
            return None
        result = self.ci_gate(pr["number"])
        if result == "failed":
            self.update(task["id"], phase="REPAIR", error="GitHub CI failed; inspect gh pr checks and workflow logs")
            return None
        if result != "passed":
            raise GateError("CI timed out or a required workflow is missing")
        self.run_cmd(["gh", "pr", "ready", str(pr["number"]), "--repo", self.repo],
                     label="mark PR ready")
        if self.args.auto_merge:
            head = self.gh(["pr", "view", str(pr["number"]), "--json", "headRefOid,state"])
            if head.get("state") != "OPEN":
                raise GateError("PR state changed before merge")
            self.run_cmd(["gh", "pr", "merge", str(pr["number"]), "--repo", self.repo,
                          "--squash", "--match-head-commit", head["headRefOid"]],
                         label="squash merge gated PR")
            self.update(task["id"], phase="COMPLETE", pr=pr["number"], error="")
            return True
        self.update(task["id"], phase="WAITING_MERGE", pr=pr["number"], error="")
        return False

    def one_task(self, task):
        key, branch = task["id"], f"codex/{task['id'].lower()}"
        record = self.state["tasks"].setdefault(key, {"phase": "PENDING", "attempts": 0})
        while True:
            if record["phase"] == "BLOCKED":
                raise GateError("Task is blocked. Inspect status; use reset-blocked explicitly.")
            pr = self.find_pr(branch)
            if pr and (record["phase"] in ("PUBLISHED", "WAITING_MERGE") or pr.get("mergedAt")):
                outcome = self.inspect_pr(task, record, pr)
                if outcome is not None:
                    return outcome
                record = self.state["tasks"][key]
                continue
            if record["attempts"] >= self.max_attempts:
                raise GateError(f"Exceeded {self.max_attempts} repair passes")
            self.task_branch(task)
            record = self.update(key, phase="WORKING", attempts=record["attempts"] + 1)
            try:
                self.develop(task, record.get("error", ""))
                error = self.local_gates()
                if not error:
                    error = self.commit_and_review(task)
                if error:
                    record = self.update(key, phase="REPAIR", error=error)
                    continue
                pr = self.publish(task, branch, pr)
                record = self.update(key, phase="PUBLISHED", pr=pr["number"], error="")
            except GateError as exc:
                self.update(key, phase="BLOCKED", error=str(exc))
                raise

    def run(self):
        self.preflight()
        for task in self.config["tasks"]:
            if self.state["tasks"].get(task["id"], {}).get("phase") == "COMPLETE":
                continue
            try:
                done = self.one_task(task)
            except (GateError, subprocess.TimeoutExpired) as exc:
                self.update(task["id"], phase="BLOCKED", error=str(exc))
                print("STOPPED:", exc, file=sys.stderr)
                return 2
            if not done:
                print("Waiting for PR merge. Restart after merge or use --watch.")
                return 0
        print("All migration PR tasks COMPLETE.")
        return 0


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("command", choices=("run", "status", "reset-blocked"))
    cli.add_argument("--watch", action="store_true", help="Wait for human-approved PR merges")
    cli.add_argument("--auto-merge", action="store_true", help="Explicit opt-in to PR merging after every gate passes")
    cli.add_argument("--task", help="For reset-blocked: MIG-XX")
    args = cli.parse_args(argv)
    config = load_queue()
    runner = Controller(args, config)
    if args.command == "status":
        print(json.dumps(runner.state, indent=2, ensure_ascii=False))
        return 0
    with single_runner():
        if args.command == "reset-blocked":
            record = runner.state["tasks"].get(args.task, {})
            if record.get("phase") != "BLOCKED":
                raise GateError("Only BLOCKED tasks can be reset")
            runner.update(args.task, phase="REPAIR", attempts=0,
                          error="Operator reset: " + record.get("error", ""))
            return 0
        return runner.run()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (GateError, OSError, ValueError) as error:
        print("CONTROLLER BLOCKED:", error, file=sys.stderr)
        sys.exit(2)
