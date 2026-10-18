# info-curator テーブル定義(案)

情報を段階的に**収集 → 検証 → 修正 → 仕分け**し、選りすぐったものをCSVで出力するための、データベース(Supabase / Postgres)のテーブル定義。

最初の分野は「古代の戦地」。ほかの分野にも使い回せるよう、**共通基盤 + 分野ごとの詳細表**の構成にする。

関連チケット: `T-20261018-001`(705_AI-Dev リポジトリの service-desk)

---

## 1. 設計方針

1. **収集データ**と**あなたの判断(fav・カテゴリなど)**は別の表に分ける。再収集しても仕分けが消えない。
2. **検証・修正・収集の記録は追記のみ**。旧値は消さない。いつでも元に戻せる。
3. **使った AI(会社・モデル・バージョン・指示文の版)を、1回の実行(runs)ごとに記録**し、各データから参照する。モデル名は AI の自己申告ではなく、実行側(スクリプト・スキル)が自動で記録する。
4. 名前の揺れ(表記ゆれ)に備え、**日本語名・原語名・別名**を持つ。同一性の判定は名前ではなく**外部ID(Wikidata のQ番号など)**で行う。
5. 項目ごとの「確かさ」は、検証記録を集計して導く(表には直接持たない)。
6. 全表に `owner_id` を持たせ、**RLS(行ごとのアクセス制限)**で、ログインした本人だけが読み書きできるようにする。**データを入れる前に有効化する**。
7. 他の分野を足すときは、**詳細表(と、必要なら拡張表)を足すだけ**にする。共通基盤は変更しない。

### 種別(items.kind)

| kind | 意味 | 例 |
|---|---|---|
| `subject` | 主題(調べる対象の中心) | 戦い。分野によっては事件・条約・都市など |
| `person` | 人物 | 将軍、王 |
| `anecdote` | 逸話 | 戦いや人物にまつわる話 |
| `party` | 勢力・国 | 戦いの陣営として使う |

`subject` の細分類は `subject_details.subject_type`(最初は「戦い」)で持つ。

---

## 2. 共通基盤

すべての表に `id uuid`(主キー)、`owner_id uuid`、`created_at timestamptz`、`updated_at timestamptz` を持たせる(以下の表では省略)。

### domains(分野)
| 列 | 型 | 説明 |
|---|---|---|
| key | text unique | 例: `ancient_battles` |
| name_ja | text | 例: 古代の戦地 |
| description | text | 説明 |

### items(すべての「もの」の共通行)
| 列 | 型 | 説明 |
|---|---|---|
| domain_id | uuid → domains | 分野 |
| kind | text | `subject` / `person` / `anecdote` / `party` |
| name_ja | text | 日本語名(表示用) |
| name_orig | text | 原語名(英語名など) |
| lang_orig | text | 原語(`en` など) |
| external_ids | jsonb | 外部ID。例: `{"wikidata":"Q12345"}`。Q番号は一意にして重複を防ぐ |
| summary_ja | text | 日本語の概要(要約。原文の長い転載はしない) |

### item_aliases(別名・表記ゆれ)
| 列 | 型 | 説明 |
|---|---|---|
| item_id | uuid → items | |
| alias | text | 例: ペルシャ戦争 |
| lang | text | |
| kind | text | `variant`(表記ゆれ) / `old_name`(旧称) / `orig`(原語) など |

### item_texts(日本語化した文章と由来)
| 列 | 型 | 説明 |
|---|---|---|
| item_id | uuid → items | |
| field | text | どの項目の文章か |
| lang | text | 本文の言語(通常 `ja`) |
| body | text | 本文 |
| translated_from_lang | text null | 訳した場合の元の言語 |
| translation_method | text null | `wikipedia_ja` / `ai_translation` / `ai_summary` / `human` |
| source_excerpt_ref | text null | 元の英語原文の置き場(raw への参照) |
| run_id | uuid → runs | 作成した実行 |

### item_links(ひも付け)
| 列 | 型 | 説明 |
|---|---|---|
| from_item_id | uuid → items | |
| to_item_id | uuid → items | |
| relation | text | `participant`(参加者) / `side`(陣営) / `about`(逸話が扱う対象) / `parent`(上位の主題) など |
| role | text null | 例: 総大将、参謀、`side_a`、`side_b` |
| note | text null | |

### sources(出典)
| 列 | 型 | 説明 |
|---|---|---|
| type | text | `web` / `book` / `paper` |
| url | text null | |
| isbn13 | text null | 13桁に統一(ISBN-10は変換して保存) |
| title | text | 書名・ページ名 |
| authors | text null | |
| publisher | text null | |
| year | int null | |
| edition | text null | 版 |
| license | text null | 例: CC BY-SA |
| family | text null | **元になった出典の系統**(独立性の判定用。同じ元ネタのものは同じ値) |
| isbn_status | text null | `unchecked` / `checksum_ok` / `matched` / `human_checked` |
| retrieved_at | timestamptz null | 取得日 |

### item_sources(どの項目の出典か)
| 列 | 型 | 説明 |
|---|---|---|
| item_id | uuid → items | |
| field | text | 例: `period`, `location`, 逸話本文 |
| source_id | uuid → sources | |
| locator | text null | **該当ページ・章** |

---

## 3. 収集・検証・修正(追記のみ)

### runs(実行の記録)
収集・検証・修正の1回ごとに1行。誰が・何で・いつ、を共通の形で残す。

| 列 | 型 | 説明 |
|---|---|---|
| kind | text | `collect` / `verify` / `fix` |
| actor_type | text | `ai` / `human` |
| actor_name | text | AI の提供元、または人の名前 |
| model_id | text null | **モデルID(バージョンまで)**。実行側が自動記録 |
| tool | text null | 例: Claude Code |
| skill_name | text null | |
| skill_version | text null | |
| prompt_version | text null | 指示文の版 |
| params | jsonb null | 設定(わかる範囲で) |
| started_at / finished_at | timestamptz | |
| raw_ref | text null | 元の応答の置き場(Supabase のファイル置き場、または PC の `raw/`) |
| note | text null | |

### verifications(検証記録)
| 列 | 型 | 説明 |
|---|---|---|
| item_id | uuid → items | |
| field | text | 対象の項目 |
| run_id | uuid → runs | |
| result | text | `match` / `partial` / `mismatch` / `unverifiable` |
| diff | text null | どこがどう違ったか |
| evidence | text null | 根拠の**短い**抜粋 |
| confidence | numeric null | 0〜1 |
| human_status | text | `pending` / `confirmed` / `rejected` |

### verification_sources(何と比べたか)
| 列 | 型 | 説明 |
|---|---|---|
| verification_id | uuid → verifications | |
| source_id | uuid → sources | |
| locator | text null | 該当箇所 |

### requests(依頼キュー)
iPhone から出した依頼を、PC の Claude Code が取り出して処理する。

| 列 | 型 | 説明 |
|---|---|---|
| item_id | uuid → items | |
| field | text null | |
| instruction | text | **人の指示文(原文)** |
| evidence_refs | jsonb | **人が示した確認先**(URL / ISBN / ページ) |
| status | text | `queued` / `processing` / `proposed` / `done` / `failed` / `cancelled` |
| requested_by | uuid | |
| processed_run_id | uuid null → runs | 処理した実行 |
| result_note | text null | 失敗理由など |

### changes(変更履歴)
| 列 | 型 | 説明 |
|---|---|---|
| item_id | uuid → items | |
| field | text | |
| old_value | jsonb | **旧値(消さない)** |
| new_value | jsonb | |
| status | text | `proposed` / `approved` / `rejected` / `applied` |
| run_id | uuid → runs | 案を作った実行 |
| request_id | uuid null → requests | きっかけの依頼 |
| evidence | text null | 根拠の抜粋(**必須にする**) |
| approved_by | uuid null | |
| approved_at | timestamptz null | |

### term_dictionary(訂正辞書)
| 列 | 型 | 説明 |
|---|---|---|
| domain_id | uuid → domains | |
| kind | text | `person` / `place` / `term` など |
| orig | text | 原語 |
| preferred_ja | text | 採用する日本語表記 |
| from_change_id | uuid null → changes | 根拠となった訂正 |

---

## 4. 仕分け(あなたの判断。収集データとは別)

### user_item_state
| 列 | 型 | 説明 |
|---|---|---|
| item_id | uuid → items | |
| status | text | `unreviewed` / `hold` / `discard`(未整理 / 保留 / 不要) |
| fav | boolean | |
| fav_at | timestamptz null | |
| note | text null | |
| reviewed_at | timestamptz null | |

### tags(カテゴリ。使いながら増やす)
| 列 | 型 | 説明 |
|---|---|---|
| name | text | |
| parent_id | uuid null → tags | あとで階層化できる |

### item_tags
| 列 | 型 | 説明 |
|---|---|---|
| item_id | uuid → items | |
| tag_id | uuid → tags | |
| tagged_at | timestamptz | 付けた日時 |

### saved_views(保存済みの絞り込み条件)
| 列 | 型 | 説明 |
|---|---|---|
| name | text | |
| filter | jsonb | 絞り込み条件 |
| export_columns | jsonb | CSV に出す列 |

---

## 5. 分野ごとの詳細表(最初の分野: 古代の戦地)

### subject_details(`items.kind = 'subject'` の詳細)
| 列 | 型 | 説明 |
|---|---|---|
| item_id | uuid → items (unique) | |
| subject_type | text | 最初は「戦い」 |
| era_label | text null | 時代の区分 |
| start_year / end_year | int null | 紀元前は負の数 |
| date_precision | text null | `exact` / `year` / `decade` / `century` / `unknown` |
| outcome_summary | text null | 結果の概要 |
| significance | text null | **より大きな流れ(最終決着)に対する位置づけ** |
| parent_item_id | uuid null → items | 上位の主題(例: 戦争)。`item_links` の `parent` と同期 |
| lat / lng | numeric null | 座標(Wikidata / OpenStreetMap 由来) |
| location_confidence | text null | `confirmed` / `estimated` / `unknown` |
| location_basis | text null | 位置の根拠(1行) |
| location_text | text null | 現在の地名など |

陣営は `item_links`(`relation = 'side'`、`role = 'side_a' / 'side_b'`、先は `kind = 'party'` の item)で表す。

### person_details(`items.kind = 'person'` の詳細)
| 列 | 型 | 説明 |
|---|---|---|
| item_id | uuid → items (unique) | |
| birth_year / death_year | int null | |
| year_precision | text null | |
| affiliation | text null | 所属・国 |
| role_summary | text null | 役割の概要 |

### anecdote_details(`items.kind = 'anecdote'` の詳細)
| 列 | 型 | 説明 |
|---|---|---|
| item_id | uuid → items (unique) | |
| body_ja | text | 本文(日本語。要約) |
| reliability | text | `sourced`(出典あり) / `legend`(伝承) / `ai_unverified`(AI生成・未確認) |

`ai_unverified` は、確認するまで仕分けとCSV出力の対象から外せるようにする。

---

## 6. 運用の取り決め

- **項目の確かさ**は、`verifications` を集計するビューで導く。例: 独立した出典の系統(`sources.family`)が2つ以上で `match` なら「裏付けあり」、`mismatch` があれば「要確認」。
- **ISBN**は、チェックディジットの検算 → 書誌データベースでの照合 → 不一致は `isbn_status` を `unchecked` のまま確認キューへ。原書と邦訳のISBNは、別の `sources` として両方持つ。
- **CSV出力**は、分野ごとのビューと `saved_views` を組み合わせて作る。日本語名の列に加え、原語名・外部ID・出典URLの列も選べるようにする。
- **バックアップ**(`backups` 表で記録): 全表の書き出しと `raw/` を、日付つきの圧縮ファイル1つにして Google Drive の指定フォルダへ保存する。まず手動(半自動)。最後に成功した日をアプリに表示し、7日以上空いたら警告する。
- **AI 処理**は PC の Claude Code(スキル)で手動実行し、iPhone とは `requests` を介してやりとりする。

### `backups`
| 列 | 型 | 説明 |
|---|---|---|
| started_at / finished_at | timestamptz | |
| status | text | `success` / `failed` |
| location | text null | 保存先 |
| size_bytes | bigint null | |
| tables | jsonb null | 対象の表 |
| note | text null | 失敗理由など |

---

## 7. まだ決まっていないこと

- 生データ(元の AI 応答)の置き場: Supabase のファイル置き場か、PC の `raw/` か(両方でも可)。
- GitHub 上のリポジトリの作成(名前は `info-curator`、公開)。
- 収集の骨格の入手元の詳細(Wikidata から戦いの項目と座標を取る範囲)。
- 検証スキルの仕様(入力・出力・各項目の判定ルール)。
- アプリ(PWA)の画面設計。
