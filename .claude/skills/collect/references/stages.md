# 段階ごとの手順

どの段階も、共通の手順(SKILL.md)の中で行う。書き出した後は必ず `validate_output.py` を通す。

## 1. skeleton(戦いの骨格)

**スクリプトが行う。AI は判断を加えない。**

```
python .claude/skills/collect/scripts/wikidata_battles.py raw/<run_id> --from-year -3000 --to-year 500 --limit 50 [--offset 0] [--allow-no-coord]
```

- Wikidata から、種別が「戦い」の項目を取得する(座標あり、既定)。
- 出力: `items`(戦いと、上位の戦争)、`item_aliases`、`subject_details`(年・座標・上位の戦争)、`sources`、`item_sources`、`item_links`(`parent`)。
- 日本語ラベルがなければ `name_ja = null`、英語名を `name_orig`。**この段階で翻訳しない**(翻訳は `basics` で行い、由来を残す)。
- 続きを取るときは `--offset` を進めて、新しい run で実行する(同じ戦いは同じ `ref` になる)。
- 取得が失敗・タイムアウトしたら、件数を減らして再実行する。結果は報告に書く。

## 2. basics(基本情報)

対象の戦いごとに、次を集める。**ソースの優先順位: Wikidata → 日本語版 Wikipedia → 英語版 Wikipedia → 書籍・事典。**

1. 対象を決める: `対象=<raw/...の run>` なら、その `items.jsonl` の `kind="subject"` を読む。`対象=Q番号` ならその項目。
2. 各対象について、ソースを読み(WebFetch / WebSearch)、次を埋める。
   - `era_label`(時代の区分。ソースの表現に従う)
   - 陣営: `kind="party"` の item を作り、`item_links`(`relation="side"`, `role="side_a"/"side_b"`)で結ぶ。
   - `outcome_summary`(結果。1〜2文)
   - **`significance`**(より大きな流れ、特に**最終決着に対して、この戦いがどんな位置づけか**。1〜3文)。ソースに書かれた評価を、自分の言葉で要約する。評価が書かれていなければ `null`。
   - `summary_ja`(日本語の概要。3〜5文の要約)と、`item_texts` に由来(`wikipedia_ja` / `ai_summary` / `ai_translation`)。
   - `item_aliases`(表記ゆれ・別名。ソースに出ているもの)
3. **ソースの記録**: 読んだページを `sources` に入れ(`family="wikimedia"` など)、`item_sources` に **項目ごと・節ごと**の `locator` を書く。
4. ソース間で食い違いがあったら、**どちらかを選ばず**、`item_texts` の `field="note"` に「A では○○、B では△△」と書く(判定は検証の工程)。
5. 書籍が参考文献として載っていて ISBN が書かれていれば、`sources` に `type="book"` で入れる。**ISBN は文中にあるものだけ。**

## 3. location(位置)

- 骨格の座標がある戦いは対象外。
- 座標がない戦いについて、次の順で探す: Wikidata(別の項目・関連項目) → Wikipedia(座標欄、「戦場」「現在の○○」) → OpenStreetMap(地名からの検索)。
- 見つかった座標: `location_confidence="estimated"`、`location_basis` に**出どころ(1行)**、`location_text` に現在の地名。
- 場所の説明はあるが座標が決められない: 座標は `null`、`location_text` だけ入れる、確度 `unknown`。
- **推測で座標を作らない。** Google マップの結果を保存しない(座標は Wikidata / OpenStreetMap 由来のものだけ保存する)。

## 4. people(人物)

- 対象の戦いに関わる人物を、**ソースで名前が挙がっているものだけ**集める(Wikidata の participant / commander、Wikipedia の指揮官欄・本文)。
- `kind="person"` の item を作り、`person_details`(生没年と精度、所属、役割の要約)、`item_links`(`relation="participant"`, `role`)を書く。
- 日本語名・原語名・別名を入れる。日本語表記が定まらないものは、**ソースにある表記を優先**し、別の表記を `item_aliases` に入れる。
- 生没年が複数の説で食い違うときは、ソース記載の主な説を入れ、`item_texts` の `field="note"` に残す。

## 5. anecdotes(逸話)

- 対象(戦い・人物)ごとに、逸話を集める。件数は `件数=` の指定(既定 20、**最大 100**)。無理に数を満たさず、ソースで裏づく分だけでよい。
- 1件ごとに `kind="anecdote"` の item(`name_ja` は短い題)、`anecdote_details`、`item_links`(`relation="about"`)、`item_sources`(ソースと該当箇所)を書く。
- `reliability`:
  - 出典を示せる → `sourced`
  - 伝承・後世の創作とソース自身が述べている → `legend`
  - 出典を示せない・記憶に基づく → **`ai_unverified`**(確認されるまで、仕分けと出力の対象外にする)
- 本文は**要約**。原文の長い引用はしない。
- 同じ逸話の重複を避ける: 同じ対象の既存の逸話(同じ run 内)と、内容が同じなら入れない。
- 人物あたり 100 件を集めるような場合は、**テーマ(出自、戦闘、人間関係、最期、後世の評価 など)に分けて**、段階的に集める。

## 完了時の報告に含めること
- 件数(items の種別ごと)、ソースの種別・系統の内訳
- `estimated` / `ai_unverified` / `unknown` の件数
- 取れなかった項目、ソース間の食い違い(note に残したもの)
- 次の段階の提案(例: `basics` を `対象=raw/<run_id>` で)
