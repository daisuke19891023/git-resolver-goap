# GOAPGit 実装タスクリスト

## 基盤

### [T01] pydanticモデル定義
**内容**: §3の models.py を作成  
**出力**: `goapgit/core/models.py`  
**AC**: mypy/ruff通過、RepoState/Plan のJSON round-tripが通る（pytest）

### [T02] 設定ローダ
**内容**: TOML を読み Config にバリデート（Py3.11 は tomllib）  
**出力**: `io/config.py`  
**AC**: 不正キー/型で ValidationError、例の TOML がロード可

### [T03] 構造化ログ
**内容**: JSON Lines ロガー（level/ts/action_id）  
**AC**: --json 時に1行1JSON、INFO/ERRORでレベル切替

## Gitラッパ/観測

### [T10] GitFacade.run
**内容**: subprocess.run ラッパ（cwd/timeout/returncode/テキスト/ドライラン）  
**AC**: 正常/非正常終了の例外化、dry_run時はコマンド記録のみ

### [T11] fetch/rebase/push API
**内容**: fetch(), rebase(onto, opts), rebase_continue()/abort(), push_with_lease()  
**AC**: 実関数が所定の引数で git を呼ぶ（モックテスト）

### [T12] 状態観測（status/進行）
**内容**: git status --porcelain=v2 を解析し RepoState を構築  
**AC**: 変更あり/なし/競合ありの3ケースで期待値一致

### [T13] 競合詳細解析（zdiff3）
**内容**: 競合ファイルを開き <<<<<<</|||||||/=======/>>>>>>> から hunk数推定  
**AC**: サンプル競合ファイルで hunk_count 一致、ctype 推定（json/yaml拡張子）

### [T14] merge-tree による衝突予測
**内容**: git merge-tree --write-tree ours theirs 実行→出力から予測競合一覧を抽出  
**AC**: 実際にマージした場合と競合ファイル集合が一致（擬似リポで比較）

## プランナー/実行

### [T20] ヒューリスティクス h(s)
**内容**: α,β,γ,δ の重み付き関数  
**AC**: 競合数/乖離が多いほど h(s) が単調増加

### [T21] A* プランナー
**内容**: start→goal の Plan 生成（Action 群は注入）  
**AC**: 3–5 個のダミーアクションで期待経路を返す

### [T22] Executor（観測→再計画）
**内容**: 1ステップ実行→観測→差異あれば再計画  
**AC**: 故意にAction失敗させた場合、再計画分岐に入る

## アクション

### [T30] Sync:FetchAll
**AC**: git fetch --prune --tags を呼ぶログが出る

### [T31] Safety:CreateBackupRef
**AC**: refs/backup/goap/* に HEAD のSHAが作られる（git show-ref 検証）

### [T32] Safety:EnsureCleanOrStash
**AC**: 未コミット変更があると stash 作成、無いと何もしない

### [T33] Rebase:RebaseOntoUpstream（--update-refs対応）
**AC**: --update-refs が指定された場合、参照更新が行われる（テスト用軽量ブランチで確認）

### [T34] Conflict:AutoTrivialResolve（rerere）
**AC**: 既知衝突を rerere が自動で解決（再発ケースで diffs が空）

### [T35] Conflict:ApplyPathStrategy
**AC**: **/*.lock は theirs 採用、*.md whitespace-only は ours 採用

### [T36] Conflict:UseMergeDriver(JSON)
**AC**: .gitattributes + merge.json.driver でJSON競合を自動マージ（成功/失敗を0/非0で返す）

### [T37] Rebase:ContinueOrAbort
**AC**: 競合解消後 --continue が成功、未解消なら失敗を検知

### [T38] Sync:PushWithLease
**AC**: 追跡先が想定と異なる場合に拒否されることを確認（擬似リモート）

### [T39] Explain:RangeDiff
**AC**: rebase 前後で range-diff の要約が出力される

## 戦略/診断

### [T40] 推奨Git設定の提示
**内容**: conflictStyle=zdiff3, rerere.enabled=true, pull.rebase=true を提案  
**AC**: goapgit diagnose が推奨＆検出結果をJSONで出す（OS無依存）

### [T41] 大規模repo対応（sparse/worktreeガイダンス）
**AC**: diagnose がしきい値超過時に sparse-checkout/worktree を助言

## CLI

### [T50] CLI:plan
**AC**: 現状態→最短Plan（ActionSpec列）がJSON/人可読の両方で出力

### [T51] CLI:run
**AC**: --confirm が無い限りdry-run、--confirm 指定で実実行

### [T52] CLI:explain
**AC**: 各アクションの理由・代替案・コストが説明される

### [T53] CLI:dry-run
**AC**: 実世界変更なし（ファイル/refsが一切変わらない）

## QA/CI

### [T60] pytest シナリオ群
**AC**: 代表3シナリオ（単純/JSON/lock）で成功

### [T61] ruff+mypy+cov
**AC**: ruff/mypy通過、テストカバレッジ 80% 以上

## 実装優先順位

### Phase 1: 基盤（T01-T03）
- データモデル定義
- 設定管理
- ログ基盤

### Phase 2: Git操作（T10-T14）
- Gitコマンドラッパ
- 状態観測
- 競合解析

### Phase 3: プランニング（T20-T22）
- A*プランナー
- 実行エンジン
- 再計画ロジック

### Phase 4: アクション実装（T30-T39）
- 同期・安全アクション
- 競合解決アクション
- 品質・説明アクション

### Phase 5: CLI・診断（T40-T53）
- コマンドラインインターフェース
- 診断・推奨設定

### Phase 6: 品質保証（T60-T61）
- テストシナリオ
- 静的解析・カバレッジ

## 受け入れ基準

各タスクは以下の基準を満たす必要があります：

1. **コード品質**: `uv run nox -s lint` と `uv run nox -s typing` が通過
2. **テスト**: 該当する単体テストが存在し、期待値と一致
3. **ドキュメント**: 必要に応じてdocstringやコメントを追加
4. **設定**: 新しい設定項目は`.env.example`に反映
5. **ログ**: 重要な操作は構造化ログに記録

## 注意事項

- 各タスクは1-3時間程度の粒度で設計
- TDD（テスト駆動開発）を基本とする
- 実装前に必ずテストを書く
- 各タスク完了後は品質チェックを実行
- 大きな変更は小さなコミットに分割