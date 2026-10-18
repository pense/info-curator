# 出力の形(raw/<run_id>/)

テーブル定義 [docs/schema.md](../../../../docs/schema.md) に沿った JSONL(1行 = 1レコード、UTF-8)。
Supabase 取り込み前なので、**uuid ではなく `ref`(この実行の中で一意な文字列)**でレコード同士をつなぐ。取り込み時に uuid へ変換する。

## ref の付け方
- Wikidata がある項目: `item:wikidata:Q31900`
- ない項目: `item:<種別>:<英数字のスラッグ>`(例: `item:person:themistocles`)
- ソース: `src:wikidata:Q31900` / `src:wikipedia:ja:マラトンの戦い` / `src:isbn:9784000000000` / `src:web:<ドメイン>:<スラッグ>`
- 同じ実体は、実行をまたいでも**同じ ref**にする(Wikidata の Q 番号で揃える)。

## ファイル一覧

すべての行に、必要に応じて下の項目を持つ。**空の値は `null`**(空文字にしない)。

### run.json(1つ)
`run_id`, `kind`("collect"), `stage`, `domain`, `actor_type`("ai" / "human" / "script"), `actor_name`, `model_id`, `model_id_source`("session" / "unknown" / "script"), `tool`, `skill_name`, `skill_version`, `prompt_version`, `params`(object), `started_at`, `finished_at`, `note`

### items.jsonl
`ref`, `kind`("subject" / "person" / "anecdote" / "party"), `domain`, `name_ja`, `name_orig`, `lang_orig`, `external_ids`(object。例 `{"wikidata":"Q31900"}`), `summary_ja`, `run_id`

### item_aliases.jsonl
`item_ref`, `alias`, `lang`, `kind`("variant" / "old_name" / "orig")

### item_texts.jsonl
`item_ref`, `field`, `lang`, `body`, `translated_from_lang`, `translation_method`("wikipedia_ja" / "ai_translation" / "ai_summary" / "human" / null), `source_excerpt_ref`, `run_id`
- `translation_method` が `ai_translation` のときは、`translated_from_lang` が必須。

### item_links.jsonl
`from_ref`, `to_ref`, `relation`("participant" / "side" / "about" / "parent"), `role`, `note`
- 陣営: `relation="side"`, `role="side_a"` / `"side_b"`、`to_ref` は `kind="party"` の item。
- 人物の参加: `relation="participant"`, `role` に役割(総大将など)。
- 逸話: `relation="about"`(逸話 → 戦い/人物)。

### sources.jsonl
`ref`, `type`("web" / "book" / "paper"), `url`, `isbn13`, `title`, `authors`, `publisher`, `year`, `edition`, `license`, `family`, `isbn_status`("unchecked" / "checksum_ok" / "matched" / "human_checked" / null), `retrieved_at`
- `family`: 元ネタが同じものは同じ値。Wikidata と Wikipedia は **`wikimedia`**。書籍は `book:<ISBN>`。Web は ドメイン名。
- `isbn13` は13桁(ハイフンなし)。ISBN-10 は13桁に変換して入れる。収集時は検算の結果を信用しない(`isbn_status="unchecked"`)。

### item_sources.jsonl
`item_ref`, `field`, `source_ref`, `locator`(該当ページ・章・節)
- `field`: どの項目の出典か(例: `skeleton`, `period`, `location`, `significance`, `body`)。

### subject_details.jsonl
`item_ref`, `subject_type`("戦い" など), `era_label`, `start_year`, `end_year`(紀元前は負の数), `date_precision`("exact" / "year" / "decade" / "century" / "unknown"), `outcome_summary`, `significance`, `parent_ref`, `lat`, `lng`, `location_confidence`("confirmed" / "estimated" / "unknown"), `location_basis`, `location_text`

### person_details.jsonl
`item_ref`, `birth_year`, `death_year`, `year_precision`, `affiliation`, `role_summary`

### anecdote_details.jsonl
`item_ref`, `body_ja`, `reliability`("sourced" / "legend" / "ai_unverified")
- 出典を示せない逸話は `ai_unverified`。`sourced` は、出典(`item_sources`)があるものだけ。

## 年の表し方
- **紀元前は負の数**(紀元前490年 = `-490`)。西暦は正の数。**0 年はない**。
- Wikidata の日付は、紀元前が 1 年ずれて返る(紀元前490年が `-0489`)。変換は `wikidata_battles.py` が行う。手で扱うときは、`年 ≤ 0 → 年 - 1`。

## 座標
- `lat`: -90〜90、`lng`: -180〜180(10進数の度)。
- Wikidata の座標は `location_confidence="estimated"`、`location_basis="Wikidata P625"` とする(確定にするのは検証の工程)。
