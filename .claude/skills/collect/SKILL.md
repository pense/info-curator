---
name: collect
description: info-curator の「情報収集」を、段階ごと(骨格 → 基本情報 → 位置 → 人物 → 逸話)に行い、テーブル定義(docs/schema.md)に沿った JSONL として raw/ に書き出す。最初の分野は古代の戦地。収集だけを担当し、検証・修正・仕分けはしない。「戦地を集めて」「戦いの候補を取得」「人物を集めて」「逸話を集めて」「収集して」のような依頼で使う。
---

# collect — 情報収集スキル(v0.1.0)

info-curator の収集工程を担当する。**集めるだけ**で、正しさの判定(検証)、直し(修正)、仕分けは別の工程。

出力は、テーブル定義 [docs/schema.md](../../../docs/schema.md) に沿った JSONL を `raw/<run_id>/` に書く。Supabase への取り込みは、あとの工程で行う。`raw/` は Git に入れない(`.gitignore` 済み)。

## 守ること(最重要)

1. **作り話を入れない。** 座標、年代、ISBN、人名、引用は、**取得したソースに書いてあったものだけ**を入れる。見つからないときは `null` にして、推測した値を事実のように入れない。
2. **推測は印を付ける。** 位置を推測するなら `location_confidence = "estimated"` と根拠、逸話で出典が弱いものは `reliability = "ai_unverified"`。
3. **ISBN は、ソースの文中・書誌データに載っているものだけ**を入れる。AI の記憶で補わない。入れたら `isbn_status = "unchecked"`(検算と照合は検証の工程)。
4. **ソースを必ず残す。** すべての項目に、どのソース(URL・ISBN)のどこ(該当ページ・章・節)かを `item_sources` に書く。
5. **日本語で書く。** 英語のソースから日本語にしたときは、`translation_method` と `translated_from_lang` を入れる。**日本語名・原語名・別名**の両方を残す。
6. **原文を長く転載しない。** 本文は要約にする。根拠の抜粋は短く(300字以内)。
7. **実行の記録(run.json)を必ず作る。** 使ったモデルID、スキルの版、指示文の版を入れる。モデルIDは**このセッションの環境に書かれているもの**を使い、わからなければ `null`(`model_id_source` を `unknown`)。推測で書かない。
8. **書き出したら、必ず検証スクリプトを通す。** エラーが残ったまま完了にしない。
9. 秘密情報(鍵、トークン)を `raw/` やコードに書かない。

## 使い方

```
/collect <段階> [範囲や対象の指定]
```

| 段階 | やること | 担当 |
|---|---|---|
| `skeleton` | 戦いの候補リスト(名前・年代・座標・上位の戦争・Wikidata ID)を取得する | **スクリプト**(AI の判断は入らない) |
| `basics` | 時代区分、対戦者(陣営)、結果、**最終決着に対する位置づけ**、日本語の概要 | AI(ソースを読んで要約) |
| `location` | 座標と確度を整える(骨格で取れなかったものを探す) | AI |
| `people` | 戦いに関わる人物を集める | AI |
| `anecdotes` | 戦い・人物にまつわる逸話を集める(1対象あたり既定 20 件、最大 100 件) | AI |

各段階の手順は [references/stages.md](references/stages.md)、出力の形は [references/output-format.md](references/output-format.md) を読む。

### 例
- `/collect skeleton` — 紀元前3000年〜西暦500年の戦いを、座標つきで最初の 50 件
- `/collect skeleton 範囲=-500..-300 件数=200`
- `/collect basics 対象=raw/20261019T0900-skeleton-ab12`(その実行の戦いに、基本情報を足す)
- `/collect anecdotes 対象=Q31900 件数=30`

## 共通の手順

1. 段階と対象を確認する。**あいまいなときは、始める前に質問する。**
2. 実行を開始する:
   ```
   python .claude/skills/collect/scripts/new_run.py start --stage <段階> --model-id "<セッションのモデルID>" --params '{"...": "..."}'
   ```
   `raw/<run_id>/run.json` ができる。パスを以降で使う。
3. 段階の手順に従って、`raw/<run_id>/` に JSONL を書く(`skeleton` はスクリプトが書く)。
4. 検証する:
   ```
   python .claude/skills/collect/scripts/validate_output.py raw/<run_id>
   ```
   エラー(`ERROR`)は直す。警告(`WARN`)は内容を報告する。
5. 実行を終える:
   ```
   python .claude/skills/collect/scripts/new_run.py finish raw/<run_id> --note "<件数や気づき>"
   ```
6. **報告する:** 何件集めたか、ソースの内訳、`estimated` や `ai_unverified` の件数、取れなかった項目、次の段階の提案。

## やらないこと
- 集めた内容が正しいかの判定(→ 検証スキル)
- 既存データの上書き・修正(→ 修正の工程)。このスキルは**追記のみ**で、新しい `run_id` のフォルダに書く
- fav・カテゴリ付け(→ 仕分けアプリ)
- Supabase への書き込み

## 範囲の既定
- 分野: `ancient_battles`(古代の戦地)
- 年代: 紀元前3000年〜西暦500年(`-3000..500`)。紀元前は負の数。
- 言語: 日本語を主に、原語名を併記
