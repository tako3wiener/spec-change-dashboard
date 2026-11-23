# Spec Change Dashboard v1.2（独立アプリ）

v5.1〜v5.3 の `/spec-change` の調査資料、Git差分、承認状況、JUnit・Playwrightスクリーンショット/Traceを閲覧する**読み取り専用**Webアプリです。

## インストール方法（初回導入）

開発ツール本体とは別のフォルダにcloneして使用します。Python標準ライブラリのみで起動でき、pip install、Node.js、データベース、公開鍵の設定は不要です。

### 1. 前提環境

- Python 3.9以降、Git、Webブラウザ。
- GitHubのPrivateリポジトリへのアクセス権限とGit認証。
- 開発ツールを導入した、同じPCから読み取れる実際のJava Gitリポジトリ（v5.3推奨）。ダッシュボードをJavaリポジトリにコピーする必要はない。

```bash
python3 --version
git --version
```

### 2. GitHubから取得

```bash
mkdir -p "$HOME/work"
cd "$HOME/work"
git clone https://github.com/tako3wiener/spec-change-dashboard.git
cd spec-change-dashboard
```

SSH認証を設定済みの場合は `git clone git@github.com:tako3wiener/spec-change-dashboard.git` でも取得できる。認証情報をURLに埋め込まない。

### 3. 起動してブラウザで開く

```bash
# 実際に開発ツールを導入したJavaリポジトリの絶対パスを指定
python3 -m sdd_dashboard --repo "$HOME/work/your-java-project" --port 8765
```

ブラウザで <http://127.0.0.1:8765> を開く。起動したターミナルで Ctrl+C を押すと停止する。8765番ポートが使用中なら `--port 8766` に変更し、ブラウザも8766番を開く。

Javaリポジトリでまだ `/project-setup` や `/spec-change` を実施していなければ、設定・変更ID・進捗が表示されない場合がある。開発ツールの [README](https://github.com/tako3wiener/claude-spec-driven-development/blob/main/README.md) に従って準備する。

旧版の開発ツールで署名が必須の場合、その要件は旧版側に残る。v1.2のダッシュボードは電子署名を検証しないため、v5.3以降との組み合わせを推奨する。

### 4. 更新・取り外し

```bash
cd "$HOME/work/spec-change-dashboard"
git pull --ff-only
python3 -m unittest discover -s tests -v
```

起動中なら停止して再起動する。取り外す場合はサービスを停止し、ダッシュボード側のcloneフォルダだけを削除する。開発ツール本体やJavaリポジトリの設定・証跡に変更は不要。

## 使い方

Python 3.9以降。外部Pythonライブラリは不要です。実際のJavaリポジトリを指定してください。

```bash
cd /任意の場所/spec-change-dashboard
python3 -m sdd_dashboard --repo /work/your-java-project --port 8765
# ベースブランチを明示する場合
python3 -m sdd_dashboard --repo /work/your-java-project --base-ref origin/main --port 8765
# ブラウザで http://127.0.0.1:8765 を開く
```

画面は15秒ごとに状態を再取得します。進捗（ゲート・次アクション）はv5.2の`/spec-change`が`.claude/local/progress/CHG-ID.json`へ書く任意の進捗イベントを優先し、それがなければ既存成果物から推定します。**進捗イベントは自己申告であり承認やテストのPASS証明ではありません。** イベント内のブランチと現在のGitブランチが異なる場合、イベントは採用しません。

## 表示範囲

- コードベース・現在のGitブランチとコミット、変更ID一覧、ゲート、次アクション
- `docs/changes/<CHG>` の調査・要求・テストケース・計画、`docs/spec` の仕様書索引
- 作業ツリーにおけるコードのGit差分（変更ID単位の特定は不可）
- G2/NET/G6の人間承認記録と対象ハッシュの整合性（電子署名不要・本人認証なし）
- `project-env.json`が設定した保存先からJUnit、E2E PNG、Trace、XML、実行サマリー
- G2/G6の承認対象確認用JSON（PENDING）。実際の承認は開発ツールv5.3の record-* コマンドを人が別ターミナルで実行します。

## 疎結合とセキュリティ

- ダッシュボードは既存システムのスクリプトをimportも実行もせず、ファイルと `git` を**読み取り**に使用します。v1.2では承認に関する電子署名やOpenSSLの検証は行いません。
- `spec-change`を動かすのにダッシュボードやHTTPサービスは必要ありません。ダッシュボードを削除しても動作に影響しません。
- 既定で`127.0.0.1`のみに待受け、書込み/承認/マージ/デプロイのAPIを持ちません。社外・社内LAN公開用途には**未対応**です。
- PNGやTraceには個人情報・認証情報が含まれ得るため、合成テストデータを使い、起動ホストのアクセス権を制御してください。
- ローカルの作業者権限内で動きます。OSレベルの監査・リモート閲覧・承認者本人確認・Tamper-proofの証跡保証はありません。
- v1.2: G2/NET/G6の公開鍵設定・署名ファイルは不要。ローカルJSONの整合確認のみを表示します。

## 動作確認

```bash
python3 -m unittest discover -s tests -v
```

## v1.1：MarkdownビューアーとDiffビューアー

`/spec-change` のコア機能は変更せず、**ダッシュボードのみ**の更新です。v1.0と同様にPython標準ライブラリだけで起動できます。ブラウザで使用する2つのビューアーも追加ライブラリ・CDN・インターネット接続を必要としません。

### Markdown（仕様・調査資料／承認資料／E2Eレポート）

- `.md` ファイルの「表示」から整形表示を開きます。見出し、段落、太字/斜体、箇条書き、チェックリスト、引用、テーブル、コードブロック、リンク、水平線を表示します。
- ダイアログ内の「Markdown原文」でソース表示に切り替えられます。
- **Markdown中の生HTML、スクリプト、埋め込み画像は実行/自動読込しません**。ユーザー提供ファイルを安全側で閲覧するため、完全なCommonMark/GFM互換ではありません。安全な `https://` / `http://` / `mailto:` リンクだけ開けます。
- PDFなどの既存ファイル形式は従来どおりです。

### Git Diff（コード変更タブ）

- ファイルごとの「Diffビューアー」で統合表示（unified）と左右比較（split）を切り替えられます。
- 追加行を緑、削除行を赤で強調し、旧/新の行番号、hunkヘッダー、追加/削除行数を表示します。
- Gitの未追跡ファイルを含む既存の差分取得APIをそのまま利用します。コピー可能です。
- 大きな差分はブラウザ性能のため最初の4,000行まで表示します。Gitの取得サイズ制限・機密ファイル非表示のルールは従来どおりです。

### 検証

```bash
python3 -m unittest discover -s tests -v
```

元のバックエンド11件に加え、新規ビューアー4件を追加。Chromium UIテストの実行には**テスト時のみ**`playwright` PythonパッケージとシステムChromiumが必要で、存在しなければ該当ケースをスキップします。アプリの利用にはいずれも不要です。
