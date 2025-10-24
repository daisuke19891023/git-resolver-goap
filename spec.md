# GOAPGit 仕様書 v0.1 草案

## 概要

**GOAPGit** は、GOAP（Goal-Oriented Action Planning）を活用してGitリポジトリの「衝突解消＆鮮度維持（小まめなrebase/pull）」を半自動化するPythonパッケージです。

### 目的
- Gitリポジトリの競合解消をGOAPによる計画→実行→観測→再計画で半自動化
- 最新のGitベストプラクティスを組み込んだ安全な操作

### 非目的
- 意味解釈を伴う最終選択の完全自動化（必要時は人手介入へフォールバック）

## アーキテクチャ

```
goapgit/
├── core/            # GOAP中核
│   ├── models.py      # pydanticデータ型（State/Goal/Plan/ActionSpec…）
│   ├── planner.py     # A*プランナー + ヒューリスティクス
│   ├── executor.py    # 実行・観測・再計画ループ
│   ├── cost.py        # コスト・リスクモデル
│   └── explain.py     # Explainability（根拠/代替案）
├── git/
│   ├── facade.py      # Gitコマンド安全ラッパ（dry-run/timeout/戻り値正規化）
│   ├── observe.py     # 状態観測（status/merge-tree解析/競合抽出）
│   ├── parse.py       # porcelain v2・conflict markers・range-diff解析
│   └── strategies.py  # ours/theirs/zdiff3/rerere/merge driver等の戦術
├── actions/         # 原子的Action実装
│   ├── sync.py
│   ├── rebase.py
│   ├── conflict.py
│   ├── quality.py
│   └── safety.py
├── plugins/
│   └── json_merge.py  # 例: JSON/YAML専用マージドライバ
├── cli/
│   └── main.py        # TyperベースCLI
├── io/
│   ├── config.py      # 設定（pydantic）読み込み/検証
│   ├── logging.py     # 構造化ログ
│   └── snapshot.py    # ステートスナップショット
└── tests/           # pytest
```

## 機能要求

### ゴール（Goal）
- 競合ファイルがゼロ
- rebase/merge 操作が未進行
- 作業ツリーがクリーン
- 追跡ブランチとの差分が解消（fast‑forward/rebase 完了）
- オプション: テスト成功・push --force-with-lease 済

### コア機能

1. **計画**: A* により、目標到達までの最短アクション列を合成
2. **予測**: git merge-tree --write-tree でワークツリー非破壊の衝突予測（dry-run）を実施
3. **実行**: GitFacade が安全にコマンド発行（timeout/リトライ/ドライラン）
4. **観測**: git status --porcelain=v2、競合マーカー（zdiff3）解析で新状態を再構築
5. **再計画**: 予測と実測の差分や失敗を検知し、プランを再合成

## Git ベストプラクティス

### 安全な操作
- **安全な押し上げ**: `git push --force-with-lease` をデフォルト（`--force`は明示時のみ）
- **積み上げブランチ対応**: `git rebase --update-refs` を活用し、依存ブランチの参照を自動更新
- **衝突の見やすさ**: `merge.conflictStyle=zdiff3` を推奨（diff3より文脈が豊富）
- **再発衝突の自動解決**: `rerere.enabled=true`（必要に応じて `rerere.autoupdate=true`）

### 戦略の既定
- マージ戦略は既定の `ort`、必要に応じ `-X diff-algorithm=histogram/patience` を切替可能
- pull戦略: 直線履歴重視なら `git pull --rebase` を推奨
- 大規模リポジトリ: 必要に応じ `git sparse-checkout`（coneモード）や `git worktree` を活用

## データモデル（pydantic v2）

### 基本型
```python
class RiskLevel(str, Enum):
    low = "low"
    med = "med" 
    high = "high"

class ConflictType(str, Enum):
    text = "text"
    json = "json"
    yaml = "yaml"
    lock = "lock"
    binary = "binary"

class GoalMode(str, Enum):
    resolve_only = "resolve_only"
    rebase_to_upstream = "rebase_to_upstream"
    push_with_lease = "push_with_lease"
```

### リポジトリ状態
```python
class RepoState(BaseModel):
    repo_path: Path
    ref: RepoRef
    diverged_local: int = 0
    diverged_remote: int = 0
    working_tree_clean: bool = True
    staged_changes: bool = False
    ongoing_rebase: bool = False
    ongoing_merge: bool = False
    stash_entries: int = 0
    conflicts: tuple[ConflictDetail, ...] = Field(default_factory=tuple)
    conflict_difficulty: float = 0.0
    tests_last_result: Optional[bool] = None
    has_unpushed_commits: bool = False
    staleness_score: float = 0.0
    risk_level: RiskLevel = RiskLevel.low
```

### 計画とアクション
```python
class Plan(BaseModel):
    actions: list[ActionSpec]
    estimated_cost: float
    notes: list[str] = Field(default_factory=list)

class ActionSpec(BaseModel):
    name: str
    params: Mapping[str, str] | None = None
    cost: float
    rationale: str | None = None
```

## アクション設計

### 準備・安全
- **Safety:CreateBackupRef**: `git update-ref refs/backup/goap/<ts> HEAD`
- **Safety:EnsureCleanOrStash**: `git stash push --include-untracked -m goap/<ts>`（必要時）

### 同期
- **Sync:FetchAll**: `git fetch --prune --tags`

### Rebase / Merge
- **Rebase:RebaseOntoUpstream**: `git rebase <tracking>`（`--update-refs`サポート）
- **Merge:PreviewWithMergeTree**: `git merge-tree --write-tree <ours> <theirs>` で非破壊衝突検出

### 競合解決
- **Conflict:AutoTrivialResolve**: `git rerere` + 既知解決の適用
- **Conflict:ApplyPathStrategy**: パターンマッチによる自動解決
- **Conflict:UseMergeDriver**: `.gitattributes` + カスタムマージドライバ
- **Conflict:MergetoolDeferred**: ユーザのmergetool起動

### 仕上げ
- **Rebase:ContinueOrAbort**: `git rebase --continue | --skip | --abort`
- **Quality:RunTests**: ユーザ設定のテストコマンド実行
- **Sync:PushWithLease**: `git push --force-with-lease`

## GOAPプランナー

- **A***: ノード＝RepoState、エッジ＝Action
- **コスト**: Action.cost + リスクペナルティ + 時間推定
- **ヒューリスティクス**: α*conflicts + β*diverged + γ*(ongoing_rebase) + δ*staleness
- **停止**: GoalSpec 充足

## CLI 仕様

```bash
$ goapgit plan        # 乾式：merge-treeで衝突予測＋最短プラン提示
$ goapgit run         # 実行：1アクションずつ観測しつつ再計画
$ goapgit dry-run     # 実世界変更なしで実行手順/影響を一覧
$ goapgit explain     # 意思決定の根拠・代替案・range-diffの提示
$ goapgit diagnose    # リポの健全性/推奨Git設定を提示
```

共通オプション: `--repo PATH`, `--config FILE`, `--json`, `--verbose`, `--confirm`

## 設定（TOML例）

```toml
[goal]
mode = "rebase_to_upstream"
tests_must_pass = false
push_with_lease = true

[strategy]
enable_rerere = true
conflict_style = "zdiff3"
rules = [
  { pattern = "**/*.lock", resolution = "theirs" },
  { pattern = "**/*.json", resolution = "merge-driver:json" }
]

[safety]
dry_run = true
allow_force_push = false
max_test_runtime_sec = 600
```

## プロジェクト管理

### pyproject.toml
```toml
[project]
name = "goapgit"
version = "0.1.0"
description = "GOAP-driven Git conflict resolver and freshness keeper"
requires-python = ">=3.11"
dependencies = [
  "pydantic>=2.6",
  "typer>=0.12",
  "rich>=13.7",
]

[project.optional-dependencies]
plugins = ["ruamel.yaml>=0.18", "jsonschema>=4.23"]
dev = ["pytest>=8", "pytest-cov>=4", "ruff>=0.6", "mypy>=1.11"]

[project.scripts]
goapgit = "goapgit.cli.main:app"
```

## ログ/テレメトリ

- JSON Lines（1行1イベント）で時系列トレース
- Plan/Action/結果/観測の因果関係IDを付与
- `--json` で機械可読出力（CIパイプラインやダッシュボード連携）

## セキュリティ/安全

- 既定は dry-run、`--confirm` で実実行
- `--force-with-lease` 以外の強制更新はデフォルト禁止
- 認証トークンやURLはログに出さない（サニタイズ）

## 代表ユーザーフロー

1. **goapgit plan**: merge-tree で衝突予測 → 競合と難度を提示
2. **goapgit run --confirm**: バックアップ作成 → fetch → rebase → 競合解決 → テスト → push
3. **goapgit explain**: range-diff で rebase 前後差分を出力

## リスク/補足

- rebase時のours/theirs反転は必ず内部で吸収
- merge=ours/theirs の過剰適用は危険（必要最小限のパスに限定）
- 乾式計画は merge-tree を第一選択として作業ツリーを汚さない

## 参考出典

- push --force-with-lease の安全性（公式）
- rebase --update-refs（新機能／利用例・manページ）
- merge-tree --write-tree による非破壊マージ（公式）
- merge.conflictStyle=zdiff3（公式man/解説）
- rebase中の ours/theirs の意味（公式）
- pull --rebase/--ff-only（公式）
- sparse-checkout coneモード（公式）
- worktree（公式）
- range-diff（公式）
- merge-ort/diffアルゴリズム（公式）