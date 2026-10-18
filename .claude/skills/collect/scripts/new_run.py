#!/usr/bin/env python3
"""収集の実行(run)の開始・終了を記録する。

  開始: python new_run.py start --stage skeleton --model-id "<モデルID>" --params '{"limit": 50}'
  終了: python new_run.py finish raw/<run_id> --note "50件"

`start` は raw/<run_id>/run.json を作り、フォルダのパスを標準出力に出す。
モデルIDは、AI の自己申告ではなく、実行する側(Claude Code のセッション情報)から渡す。
わからないときは --model-id を省略する(null になり、model_id_source は unknown)。
"""
import argparse
import json
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SKILL_NAME = "collect"
SKILL_VERSION = "0.1.0"
PROMPT_VERSION = "collect-0.1.0"
STAGES = ["skeleton", "basics", "location", "people", "anecdotes"]
JST = timezone(timedelta(hours=9))


def now() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def repo_root() -> Path:
    here = Path(__file__).resolve()
    # <root>/.claude/skills/collect/scripts/new_run.py
    return here.parents[4]


def start(args: argparse.Namespace) -> int:
    stamp = datetime.now(JST).strftime("%Y%m%dT%H%M%S")
    run_id = f"{stamp}-{args.stage}-{secrets.token_hex(2)}"
    out = Path(args.raw_dir) if args.raw_dir else repo_root() / "raw"
    run_dir = out / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    try:
        params = json.loads(args.params) if args.params else {}
    except json.JSONDecodeError as e:
        print(f"--params が JSON ではありません: {e}", file=sys.stderr)
        return 2
    is_script = args.stage == "skeleton"
    run = {
        "run_id": run_id,
        "kind": "collect",
        "stage": args.stage,
        "domain": args.domain,
        "actor_type": "script" if is_script else "ai",
        "actor_name": "wikidata_battles.py" if is_script else (args.actor_name or "Anthropic"),
        "model_id": None if is_script else args.model_id,
        "model_id_source": "script" if is_script else ("session" if args.model_id else "unknown"),
        "tool": None if is_script else (args.tool or "Claude Code"),
        "skill_name": SKILL_NAME,
        "skill_version": SKILL_VERSION,
        "prompt_version": PROMPT_VERSION,
        "params": params,
        "started_at": now(),
        "finished_at": None,
        "note": None,
    }
    (run_dir / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(run_dir)
    return 0


def finish(args: argparse.Namespace) -> int:
    path = Path(args.run_dir) / "run.json"
    if not path.exists():
        print(f"run.json がありません: {path}", file=sys.stderr)
        return 2
    run = json.loads(path.read_text(encoding="utf-8"))
    run["finished_at"] = now()
    if args.note:
        run["note"] = args.note
    path.write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"finished {run['run_id']}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("--stage", required=True, choices=STAGES)
    s.add_argument("--domain", default="ancient_battles")
    s.add_argument("--model-id", default=None)
    s.add_argument("--actor-name", default=None)
    s.add_argument("--tool", default=None)
    s.add_argument("--params", default=None, help="JSON 文字列")
    s.add_argument("--raw-dir", default=None, help="出力先(既定: リポジトリ直下の raw/)")
    s.set_defaults(func=start)
    f = sub.add_parser("finish")
    f.add_argument("run_dir")
    f.add_argument("--note", default=None)
    f.set_defaults(func=finish)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
