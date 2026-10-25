# Codex Controller — persistent local migration queue

Runs `MIG-01 .. MIG-09` from `config/migration_queue.json` against the private authorized RoBAS C# reference directory.

## Prerequisites
- Windows PowerShell or Linux terminal with **Git checkout**, Git, GitHub CLI (`gh`), Codex CLI, Node.js 20+, npm and Python 3.11.
- Authenticated CLI sessions: `gh auth login`, `codex login`. No API tokens belong in the repository.
- Existing Conda environment containing CadQuery, OCP, ezdxf and svgwrite.
- Private extracted RoBAS source **outside** public `Bearing_CAD`; obtain explicit permission to use this code.
- Create branch protection/ruleset on `main`, require CI and independent reviews in repository settings. The controller **cannot configure GitHub settings**; no ruleset was observed at development time.
- Before running check `gh pr checks` JSON on one test PR; this controller requires all configured workflows. The CI workflow name mapping can vary per GitHub CLI version; if uncertain stop rather than silently passing.
- Running on an always-on computer / VM provides persistence; this chat cannot guarantee continuous execution. Controller state lives in `.codex-controller/state.json` and logs in `.codex-controller/history.log` (both gitignored).

## Quickstart (PowerShell)

```powershell
git fetch origin
git switch main
git pull --ff-only
conda activate bearing-cad02
$env:ROBAS_SOURCE_DIR = "D:\PrivateSources\RoBAS"
gh auth status
codex login status
python scripts/codex_controller.py status
python scripts/codex_controller.py run --watch
```

Default `run --watch` develops the next MIG, runs baseline local tests, invokes a **separate read-only structured Codex review**, pushes a draft PR and polls CI. After CI passes it marks PR ready, then **waits for you to merge**. It will continue to the next MIG only after merge. To resume safely after reboot, run the same command again from a clean checkout. Linux uses `export ROBAS_SOURCE_DIR=/secure/path/RoBAS` instead.

Optional full automation (only after protected branches/required review are configured): `python scripts/codex_controller.py run --auto-merge`. This is explicit and potentially destructive. It still stops on missing CI, failed tests, review blockers, license uncertainty or exhausted retries.

Useful:
```powershell
python scripts/codex_controller.py status
python scripts/codex_controller.py reset-blocked --task MIG-01
```

## Limitations and fail-stop conditions

- Requires machine online; **no guarantee** of continued operation after process/machine shutdown unless configured with a system service or Task Scheduler.
- GitHub CLI/ Codex CLI flags may differ; verify installed versions before granting auto-merge.
- This initial controller uses local `git` for writes and GitHub CLI for PRs, not a hosted service.
- Never store secrets in prompts or commits. Human and engineering approval gates are mandatory when formula ambiguity, geometric interference or source licensing is unresolved.
- Three repair passes maximum. Failed gates, missing workflows and malformed review payloads block progress. The workflow tests the controller only; real rolling-bearing tests are added in downstream MIG PRs.
- The executor assumes all local checks have prerequisites installed. It intentionally fails closed rather than skipping full CAD tests.
