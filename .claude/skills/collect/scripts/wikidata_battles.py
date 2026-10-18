#!/usr/bin/env python3
"""Wikidata から「戦い」の候補(骨格)を取得し、raw/<run_id>/ に JSONL で書く。

  python wikidata_battles.py raw/<run_id> --from-year -3000 --to-year 500 --limit 50 [--offset 0] [--allow-no-coord]

- 年は歴史上の年(紀元前は負の数、0 年なし)。Wikidata は紀元前が 1 年ずれて返るので、ここで補正する。
- 判断は加えない。ラベルが日本語になければ name_ja は null、英語名を name_orig に入れる。
- 標準ライブラリだけで動く。
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "info-curator/0.1 (personal research tool; https://github.com/pense/info-curator)"
JST = timezone(timedelta(hours=9))
BATTLE = "Q178561"


def astro_from_historical(year: int) -> int:
    """歴史上の年(紀元前は負、0 なし)→ Wikidata の天文学的な年(紀元前1年 = 0)。"""
    return year + 1 if year < 0 else year


def historical_from_astro(year: int) -> int:
    """Wikidata の年 → 歴史上の年。0 以下は紀元前: -489 → -490, 0 → -1。"""
    return year - 1 if year <= 0 else year


def iso_literal(year_historical: int) -> str:
    y = astro_from_historical(year_historical)
    sign = "-" if y < 0 else ""
    return f'"{sign}{abs(y):04d}-01-01T00:00:00Z"^^xsd:dateTime'


def parse_year(value: str):
    m = re.match(r"^(-?)(\d{4,})-", value or "")
    if not m:
        return None
    y = int(m.group(2)) * (-1 if m.group(1) else 1)
    return historical_from_astro(y)


def precision_label(p):
    try:
        p = int(p)
    except (TypeError, ValueError):
        return "unknown"
    if p >= 11:
        return "exact"
    if p >= 9:
        return "year"
    if p == 8:
        return "decade"
    if p == 7:
        return "century"
    return "unknown"


def parse_point(value: str):
    m = re.match(r"^Point\((-?[\d.]+) (-?[\d.]+)\)$", value or "")
    if not m:
        return None, None
    return float(m.group(2)), float(m.group(1))  # lat, lng


def build_ids_query(y0: int, y1: int, limit: int, offset: int, need_coord: bool) -> str:
    """第1段: 条件に合う戦いの ID だけを取る(軽い)。"""
    coord = "?item wdt:P625 ?c0 ." if need_coord else ""
    return f"""
SELECT DISTINCT ?item WHERE {{
  ?item wdt:P31 wd:{BATTLE} .
  {coord}
  ?item wdt:P580|wdt:P585 ?s .
  FILTER(?s >= {iso_literal(y0)} && ?s < {iso_literal(y1 + 1)})
}} ORDER BY ?item LIMIT {int(limit)} OFFSET {int(offset)}
"""


def build_details_query(qids) -> str:
    """第2段: 取れた ID の詳細(ラベル・日付と精度・座標・上位の戦争)を取る。"""
    values = " ".join(f"wd:{q}" for q in qids)
    return f"""
SELECT ?item ?ja ?en ?start ?startPrec ?end ?coord ?parent ?parentJa ?parentEn WHERE {{
  VALUES ?item {{ {values} }}
  {{ ?item p:P580/psv:P580 ?sv }} UNION {{ ?item p:P585/psv:P585 ?sv }}
  ?sv wikibase:timeValue ?start ; wikibase:timePrecision ?startPrec .
  OPTIONAL {{ ?item wdt:P582 ?end . }}
  OPTIONAL {{ ?item wdt:P625 ?coord . }}
  OPTIONAL {{ ?item rdfs:label ?ja . FILTER(LANG(?ja) = "ja") }}
  OPTIONAL {{ ?item rdfs:label ?en . FILTER(LANG(?en) = "en") }}
  OPTIONAL {{
    ?item wdt:P361 ?parent .
    OPTIONAL {{ ?parent rdfs:label ?parentJa . FILTER(LANG(?parentJa) = "ja") }}
    OPTIONAL {{ ?parent rdfs:label ?parentEn . FILTER(LANG(?parentEn) = "en") }}
  }}
}}
"""


def fetch(query: str, retries: int = 3):
    url = ENDPOINT + "?" + urllib.parse.urlencode({"query": query, "format": "json"})
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/sparql-results+json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)["results"]["bindings"]
        except urllib.error.HTTPError as e:
            last = e
            wait = 5 * (attempt + 1)
            if e.code == 429:  # 混雑時は、指定された時間だけ待つ(連打しない)
                try:
                    wait = max(wait, int(e.headers.get("Retry-After", "0")))
                except ValueError:
                    pass
            time.sleep(min(wait, 90))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Wikidata への問い合わせに失敗しました: {last}")


def val(b, key):
    return b[key]["value"] if key in b else None


def qid(uri):
    return uri.rsplit("/", 1)[-1] if uri else None


def write_jsonl(path: Path, rows):
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir")
    ap.add_argument("--from-year", type=int, default=-3000)
    ap.add_argument("--to-year", type=int, default=500)
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--allow-no-coord", action="store_true", help="座標のない戦いも取る")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    run_json = run_dir / "run.json"
    if not run_json.exists():
        print("run.json がありません。先に new_run.py start を実行してください。", file=sys.stderr)
        return 2
    run_id = json.loads(run_json.read_text(encoding="utf-8"))["run_id"]
    retrieved = datetime.now(JST).isoformat(timespec="seconds")

    id_rows = fetch(build_ids_query(args.from_year, args.to_year, args.limit, args.offset, not args.allow_no_coord))
    qids = [qid(val(b, "item")) for b in id_rows]
    rows = []
    for i in range(0, len(qids), 40):  # 詳細は 40 件ずつ
        if i:
            time.sleep(1.5)
        rows.extend(fetch(build_details_query(qids[i : i + 40])))

    battles = {}  # Q -> record
    for b in rows:
        q = qid(val(b, "item"))
        if q in battles:
            continue
        lat, lng = parse_point(val(b, "coord"))
        battles[q] = {
            "q": q,
            "ja": val(b, "ja"),
            "en": val(b, "en"),
            "start": parse_year(val(b, "start")),
            "prec": precision_label(val(b, "startPrec")),
            "end": parse_year(val(b, "end")),
            "lat": lat,
            "lng": lng,
            "parent": qid(val(b, "parent")),
            "parent_ja": val(b, "parentJa"),
            "parent_en": val(b, "parentEn"),
        }

    items, aliases, details, sources, item_sources, links = [], [], [], [], [], []
    parents_done = set()
    for q, r in sorted(battles.items(), key=lambda kv: (kv[1]["start"] is None, kv[1]["start"], kv[0])):
        ref = f"item:wikidata:{q}"
        src = f"src:wikidata:{q}"
        items.append({
            "ref": ref, "kind": "subject", "domain": "ancient_battles",
            "name_ja": r["ja"], "name_orig": r["en"] or r["ja"], "lang_orig": "en" if r["en"] else ("ja" if r["ja"] else None),
            "external_ids": {"wikidata": q}, "summary_ja": None, "run_id": run_id,
        })
        if r["ja"] and r["en"]:
            aliases.append({"item_ref": ref, "alias": r["en"], "lang": "en", "kind": "orig"})
        has_coord = r["lat"] is not None
        details.append({
            "item_ref": ref, "subject_type": "戦い", "era_label": None,
            "start_year": r["start"], "end_year": r["end"], "date_precision": r["prec"],
            "outcome_summary": None, "significance": None,
            "parent_ref": f"item:wikidata:{r['parent']}" if r["parent"] else None,
            "lat": r["lat"], "lng": r["lng"],
            "location_confidence": "estimated" if has_coord else "unknown",
            "location_basis": "Wikidata P625" if has_coord else None,
            "location_text": None,
        })
        sources.append({
            "ref": src, "type": "web", "url": f"https://www.wikidata.org/wiki/{q}", "isbn13": None,
            "title": f"Wikidata {q}", "authors": None, "publisher": "Wikimedia Foundation", "year": None, "edition": None,
            "license": "CC0-1.0", "family": "wikimedia", "isbn_status": None, "retrieved_at": retrieved,
        })
        item_sources.append({"item_ref": ref, "field": "skeleton", "source_ref": src, "locator": None})
        if r["parent"]:
            pref = f"item:wikidata:{r['parent']}"
            links.append({"from_ref": ref, "to_ref": pref, "relation": "parent", "role": None, "note": "Wikidata P361(part of)"})
            if r["parent"] not in parents_done and r["parent"] not in battles:
                parents_done.add(r["parent"])
                items.append({
                    "ref": pref, "kind": "subject", "domain": "ancient_battles",
                    "name_ja": r["parent_ja"], "name_orig": r["parent_en"] or r["parent_ja"],
                    "lang_orig": "en" if r["parent_en"] else ("ja" if r["parent_ja"] else None),
                    "external_ids": {"wikidata": r["parent"]}, "summary_ja": None, "run_id": run_id,
                })
                details.append({
                    "item_ref": pref, "subject_type": "戦争・紛争(未分類)", "era_label": None,
                    "start_year": None, "end_year": None, "date_precision": "unknown",
                    "outcome_summary": None, "significance": None, "parent_ref": None,
                    "lat": None, "lng": None, "location_confidence": "unknown", "location_basis": None, "location_text": None,
                })
                psrc = f"src:wikidata:{r['parent']}"
                sources.append({
                    "ref": psrc, "type": "web", "url": f"https://www.wikidata.org/wiki/{r['parent']}", "isbn13": None,
                    "title": f"Wikidata {r['parent']}", "authors": None, "publisher": "Wikimedia Foundation", "year": None, "edition": None,
                    "license": "CC0-1.0", "family": "wikimedia", "isbn_status": None, "retrieved_at": retrieved,
                })
                item_sources.append({"item_ref": pref, "field": "skeleton", "source_ref": psrc, "locator": None})

    write_jsonl(run_dir / "items.jsonl", items)
    write_jsonl(run_dir / "item_aliases.jsonl", aliases)
    write_jsonl(run_dir / "subject_details.jsonl", details)
    write_jsonl(run_dir / "sources.jsonl", sources)
    write_jsonl(run_dir / "item_sources.jsonl", item_sources)
    write_jsonl(run_dir / "item_links.jsonl", links)

    no_ja = sum(1 for r in battles.values() if not r["ja"])
    print(f"戦い {len(battles)} 件(日本語名なし {no_ja} 件)、上位の戦争 {len(parents_done)} 件を {run_dir} に書きました。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
