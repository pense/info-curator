#!/usr/bin/env python3
"""raw/<run_id>/ の JSONL が、テーブル定義(docs/schema.md)に沿っているかを検査する。

  python validate_output.py raw/<run_id>

ERROR があれば終了コード 1。WARN は内容を報告するための注意(終了コードには影響しない)。
標準ライブラリだけで動く。
"""
import json
import re
import sys
from pathlib import Path

KINDS = {"subject", "person", "anecdote", "party"}
ALIAS_KINDS = {"variant", "old_name", "orig"}
TRANSLATION_METHODS = {"wikipedia_ja", "ai_translation", "ai_summary", "human", None}
RELATIONS = {"participant", "side", "about", "parent"}
SOURCE_TYPES = {"web", "book", "paper"}
ISBN_STATUS = {"unchecked", "checksum_ok", "matched", "human_checked", None}
PRECISION = {"exact", "year", "decade", "century", "unknown", None}
LOC_CONF = {"confirmed", "estimated", "unknown", None}
RELIABILITY = {"sourced", "legend", "ai_unverified"}
ACTOR_TYPES = {"ai", "human", "script"}
MODEL_SOURCES = {"session", "unknown", "script"}
STAGES = {"skeleton", "basics", "location", "people", "anecdotes"}

MAX_TEXT = 4000
MAX_EXCERPT = 300

errors: list[str] = []
warns: list[str] = []


def err(msg):
    errors.append(msg)


def warn(msg):
    warns.append(msg)


def isbn13_ok(s: str) -> bool:
    if not re.fullmatch(r"\d{13}", s or ""):
        return False
    total = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(s[:12]))
    return (10 - total % 10) % 10 == int(s[12])


def load(run_dir: Path, name: str):
    path = run_dir / name
    rows = []
    if not path.exists():
        return rows
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            err(f"{name}:{n} JSON として読めません: {e}")
            continue
        if not isinstance(row, dict):
            err(f"{name}:{n} オブジェクトではありません")
            continue
        row["__line"] = n
        rows.append(row)
    return rows


def need(name, row, keys):
    for k in keys:
        if k not in row:
            err(f"{name}:{row.get('__line')} 必須の項目がありません: {k}")


def check_int(name, row, key):
    v = row.get(key)
    if v is not None and (not isinstance(v, int) or isinstance(v, bool)):
        err(f"{name}:{row['__line']} {key} は整数か null にしてください: {v!r}")
    if v == 0:
        err(f"{name}:{row['__line']} {key}=0 は使えません(0 年はない。紀元前1年は -1)")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    run_dir = Path(sys.argv[1])
    run_path = run_dir / "run.json"
    if not run_path.exists():
        print(f"ERROR run.json がありません: {run_path}")
        return 1
    try:
        run = json.loads(run_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"ERROR run.json が JSON ではありません: {e}")
        return 1

    # ---- run.json
    for k in ["run_id", "kind", "stage", "domain", "actor_type", "actor_name", "model_id_source", "skill_name", "skill_version", "prompt_version", "started_at"]:
        if not run.get(k):
            err(f"run.json: {k} がありません")
    if run.get("kind") != "collect":
        err("run.json: kind は collect にしてください")
    if run.get("stage") not in STAGES:
        err(f"run.json: stage が不正です: {run.get('stage')}")
    if run.get("actor_type") not in ACTOR_TYPES:
        err(f"run.json: actor_type が不正です: {run.get('actor_type')}")
    if run.get("model_id_source") not in MODEL_SOURCES:
        err(f"run.json: model_id_source が不正です: {run.get('model_id_source')}")
    if run.get("actor_type") == "ai":
        if not run.get("model_id"):
            warn("run.json: AI の実行ですが model_id がありません(わからない場合は model_id_source=unknown)")
        if run.get("model_id") and run.get("model_id_source") != "session":
            err("run.json: model_id があるときは model_id_source=session にしてください")
    if not run.get("finished_at"):
        warn("run.json: finished_at がありません(new_run.py finish を実行してください)")
    run_id = run.get("run_id")

    items = load(run_dir, "items.jsonl")
    aliases = load(run_dir, "item_aliases.jsonl")
    texts = load(run_dir, "item_texts.jsonl")
    links = load(run_dir, "item_links.jsonl")
    sources = load(run_dir, "sources.jsonl")
    item_sources = load(run_dir, "item_sources.jsonl")
    subjects = load(run_dir, "subject_details.jsonl")
    persons = load(run_dir, "person_details.jsonl")
    anecdotes = load(run_dir, "anecdote_details.jsonl")

    # ---- items
    refs = {}
    wikidata_ids = {}
    for r in items:
        need("items.jsonl", r, ["ref", "kind", "domain", "run_id"])
        ref = r.get("ref")
        if ref in refs:
            err(f"items.jsonl:{r['__line']} ref が重複しています: {ref}")
        refs[ref] = r
        if r.get("kind") not in KINDS:
            err(f"items.jsonl:{r['__line']} kind が不正です: {r.get('kind')}")
        if r.get("run_id") != run_id:
            err(f"items.jsonl:{r['__line']} run_id が run.json と違います")
        if not r.get("name_ja") and not r.get("name_orig"):
            err(f"items.jsonl:{r['__line']} 名前(name_ja か name_orig)がありません: {ref}")
        ext = r.get("external_ids")
        if ext is not None and not isinstance(ext, dict):
            err(f"items.jsonl:{r['__line']} external_ids はオブジェクトにしてください")
        elif isinstance(ext, dict) and ext.get("wikidata"):
            q = ext["wikidata"]
            if not re.fullmatch(r"Q\d+", q):
                err(f"items.jsonl:{r['__line']} Wikidata ID が不正です: {q}")
            if q in wikidata_ids:
                err(f"items.jsonl:{r['__line']} 同じ Wikidata ID が重複しています: {q}")
            wikidata_ids[q] = ref
        if r.get("summary_ja") and len(r["summary_ja"]) > MAX_TEXT:
            err(f"items.jsonl:{r['__line']} summary_ja が長すぎます({len(r['summary_ja'])}字)。要約にしてください")

    def known(ref, ctx):
        if ref not in refs:
            err(f"{ctx} 存在しない item を参照しています: {ref}")

    # ---- aliases
    for r in aliases:
        need("item_aliases.jsonl", r, ["item_ref", "alias", "kind"])
        known(r.get("item_ref"), f"item_aliases.jsonl:{r['__line']}")
        if r.get("kind") not in ALIAS_KINDS:
            err(f"item_aliases.jsonl:{r['__line']} kind が不正です: {r.get('kind')}")

    # ---- sources
    src_refs = {}
    for r in sources:
        need("sources.jsonl", r, ["ref", "type", "title", "family"])
        if r.get("ref") in src_refs:
            err(f"sources.jsonl:{r['__line']} ref が重複しています: {r.get('ref')}")
        src_refs[r.get("ref")] = r
        if r.get("type") not in SOURCE_TYPES:
            err(f"sources.jsonl:{r['__line']} type が不正です: {r.get('type')}")
        if r.get("type") == "web" and not r.get("url"):
            err(f"sources.jsonl:{r['__line']} Web のソースに url がありません")
        if r.get("isbn_status") not in ISBN_STATUS:
            err(f"sources.jsonl:{r['__line']} isbn_status が不正です: {r.get('isbn_status')}")
        isbn = r.get("isbn13")
        if isbn is not None:
            if not isinstance(isbn, str) or not re.fullmatch(r"\d{13}", isbn):
                err(f"sources.jsonl:{r['__line']} isbn13 は13桁の数字(ハイフンなし)にしてください: {isbn!r}")
            elif not isbn13_ok(isbn):
                warn(f"sources.jsonl:{r['__line']} ISBN のチェックディジットが合いません: {isbn}(検証の工程へ回してください)")
            if r.get("isbn_status") in {"matched", "human_checked", "checksum_ok"}:
                err(f"sources.jsonl:{r['__line']} 収集の段階では isbn_status は unchecked にしてください")
        if r.get("type") == "book" and not isbn:
            warn(f"sources.jsonl:{r['__line']} 書籍に ISBN がありません: {r.get('title')}")

    # ---- item_sources
    sourced_items = set()
    for r in item_sources:
        need("item_sources.jsonl", r, ["item_ref", "field", "source_ref"])
        known(r.get("item_ref"), f"item_sources.jsonl:{r['__line']}")
        if r.get("source_ref") not in src_refs:
            err(f"item_sources.jsonl:{r['__line']} 存在しない source を参照しています: {r.get('source_ref')}")
        sourced_items.add(r.get("item_ref"))
    for ref, it in refs.items():
        if ref not in sourced_items:
            err(f"出典がありません(item_sources に1行以上必要): {ref}")

    # ---- texts
    for r in texts:
        need("item_texts.jsonl", r, ["item_ref", "field", "lang", "body", "run_id"])
        known(r.get("item_ref"), f"item_texts.jsonl:{r['__line']}")
        if r.get("translation_method") not in TRANSLATION_METHODS:
            err(f"item_texts.jsonl:{r['__line']} translation_method が不正です: {r.get('translation_method')}")
        if r.get("translation_method") == "ai_translation" and not r.get("translated_from_lang"):
            err(f"item_texts.jsonl:{r['__line']} ai_translation には translated_from_lang が必要です")
        if isinstance(r.get("body"), str) and len(r["body"]) > MAX_TEXT:
            err(f"item_texts.jsonl:{r['__line']} 本文が長すぎます({len(r['body'])}字)。要約にしてください")

    # ---- links
    for r in links:
        need("item_links.jsonl", r, ["from_ref", "to_ref", "relation"])
        known(r.get("from_ref"), f"item_links.jsonl:{r['__line']}")
        if r.get("relation") not in RELATIONS:
            err(f"item_links.jsonl:{r['__line']} relation が不正です: {r.get('relation')}")
        if r.get("to_ref") not in refs:
            if r.get("relation") == "parent" and re.fullmatch(r"item:wikidata:Q\d+", r.get("to_ref") or ""):
                warn(f"item_links.jsonl:{r['__line']} 上位の主題がこの実行にありません: {r.get('to_ref')}")
            else:
                err(f"item_links.jsonl:{r['__line']} 存在しない item を参照しています: {r.get('to_ref')}")
        if r.get("relation") == "side" and r.get("role") not in {"side_a", "side_b"}:
            err(f"item_links.jsonl:{r['__line']} side の role は side_a / side_b にしてください")

    # ---- subject_details
    seen = set()
    n_est = n_unknown = 0
    for r in subjects:
        need("subject_details.jsonl", r, ["item_ref"])
        ctx = f"subject_details.jsonl:{r['__line']}"
        known(r.get("item_ref"), ctx)
        if r.get("item_ref") in refs and refs[r["item_ref"]].get("kind") != "subject":
            err(f"{ctx} kind が subject の item ではありません: {r['item_ref']}")
        if r.get("item_ref") in seen:
            err(f"{ctx} 同じ item の行が重複しています: {r.get('item_ref')}")
        seen.add(r.get("item_ref"))
        for k in ("start_year", "end_year"):
            check_int("subject_details.jsonl", r, k)
        if isinstance(r.get("start_year"), int) and isinstance(r.get("end_year"), int) and r["end_year"] < r["start_year"]:
            warn(f"{ctx} 終了年が開始年より前です: {r['start_year']}〜{r['end_year']}")
        if r.get("date_precision") not in PRECISION:
            err(f"{ctx} date_precision が不正です: {r.get('date_precision')}")
        lat, lng = r.get("lat"), r.get("lng")
        if (lat is None) != (lng is None):
            err(f"{ctx} lat と lng は両方入れるか、両方 null にしてください")
        if lat is not None:
            if not (isinstance(lat, (int, float)) and -90 <= lat <= 90):
                err(f"{ctx} lat が範囲外です: {lat}")
            if not (isinstance(lng, (int, float)) and -180 <= lng <= 180):
                err(f"{ctx} lng が範囲外です: {lng}")
        if r.get("location_confidence") not in LOC_CONF:
            err(f"{ctx} location_confidence が不正です: {r.get('location_confidence')}")
        if lat is not None:
            if r.get("location_confidence") in (None, "unknown"):
                err(f"{ctx} 座標があるのに location_confidence が未設定/unknown です")
            if not r.get("location_basis"):
                err(f"{ctx} 座標の根拠(location_basis)がありません")
            if r.get("location_confidence") == "confirmed":
                warn(f"{ctx} 収集の段階で confirmed にしています(確定は検証の工程)")
        if r.get("location_confidence") == "estimated":
            n_est += 1
        if r.get("location_confidence") in (None, "unknown"):
            n_unknown += 1
        pr = r.get("parent_ref")
        if pr and pr not in refs and not re.fullmatch(r"item:wikidata:Q\d+", pr):
            err(f"{ctx} parent_ref が存在しません: {pr}")

    # ---- person_details / anecdote_details
    for r in persons:
        need("person_details.jsonl", r, ["item_ref"])
        known(r.get("item_ref"), f"person_details.jsonl:{r['__line']}")
        for k in ("birth_year", "death_year"):
            check_int("person_details.jsonl", r, k)
        if refs.get(r.get("item_ref"), {}).get("kind") not in (None, "person"):
            err(f"person_details.jsonl:{r['__line']} kind が person の item ではありません")
    n_unverified = 0
    for r in anecdotes:
        need("anecdote_details.jsonl", r, ["item_ref", "body_ja", "reliability"])
        ctx = f"anecdote_details.jsonl:{r['__line']}"
        known(r.get("item_ref"), ctx)
        if r.get("reliability") not in RELIABILITY:
            err(f"{ctx} reliability が不正です: {r.get('reliability')}")
        if r.get("reliability") == "sourced":
            has = any(s["item_ref"] == r.get("item_ref") and s.get("source_ref") in src_refs for s in item_sources)
            if not has:
                err(f"{ctx} sourced なのに出典(item_sources)がありません")
        if r.get("reliability") == "ai_unverified":
            n_unverified += 1
        if isinstance(r.get("body_ja"), str) and len(r["body_ja"]) > MAX_TEXT:
            err(f"{ctx} body_ja が長すぎます。要約にしてください")
        if refs.get(r.get("item_ref"), {}).get("kind") not in (None, "anecdote"):
            err(f"{ctx} kind が anecdote の item ではありません")

    # ---- 種別ごとに、詳細表があるか
    have = {"subject": {r.get("item_ref") for r in subjects}, "person": {r.get("item_ref") for r in persons}, "anecdote": {r.get("item_ref") for r in anecdotes}}
    for ref, it in refs.items():
        k = it.get("kind")
        if k in have and ref not in have[k]:
            warn(f"{k} の詳細表に行がありません: {ref}")

    # ---- 逸話の件数(1対象あたり最大100件)
    per_target = {}
    for r in links:
        if r.get("relation") == "about":
            per_target[r.get("to_ref")] = per_target.get(r.get("to_ref"), 0) + 1
    for target, n in per_target.items():
        if n > 100:
            err(f"逸話が1対象あたり100件を超えています: {target} = {n}")

    kinds = {}
    for it in refs.values():
        kinds[it.get("kind")] = kinds.get(it.get("kind"), 0) + 1
    print(f"run: {run_id} / 段階: {run.get('stage')}")
    print("items: " + (", ".join(f"{k}={v}" for k, v in sorted(kinds.items())) or "0") + f" / sources={len(src_refs)}")
    print(f"座標 estimated={n_est} unknown/未設定={n_unknown} / ai_unverified の逸話={n_unverified}")
    for w in warns:
        print("WARN  " + w)
    for e in errors:
        print("ERROR " + e)
    print(f"結果: ERROR {len(errors)} 件 / WARN {len(warns)} 件")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
