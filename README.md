# Bot Studio

コードを書かずにDiscord Botを作成・カスタマイズできる、Render対応の管理ツールです。

## 主な機能

- Bot名、ステータス、アクティビティ、コマンド接頭辞の設定
- 参加・退出メッセージと送信先チャンネルの設定
- カスタムコマンドとキーワード自動返信の追加
- 禁止ワードの自動削除と警告
- Botの接続状態と参加サーバー数の確認
- 管理パスワードによるダッシュボード保護
- スマートフォン対応の日本語管理画面

設定は `bot_config.json` に保存され、Botを再起動せずに反映されます。

## Discord Botを準備する

1. [Discord Developer Portal](https://discord.com/developers/applications) でアプリケーションを作成します。
2. **Bot** ページでBotを追加し、トークンを取得します。
3. **Privileged Gateway Intents** の `SERVER MEMBERS INTENT` と `MESSAGE CONTENT INTENT` を有効にします。
4. **OAuth2 > URL Generator** で `bot` を選択し、次の権限を付けてサーバーへ招待します。
   - View Channels
   - Send Messages
   - Read Message History
   - Manage Messages（モデレーションを使う場合）

## ローカル起動

Python 3.11を使用します。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShellの場合:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

環境変数を設定して起動します。

```powershell
$env:DISCORD_TOKEN="Discord Botのトークン"
$env:ADMIN_PASSWORD="管理画面のパスワード"
python main.py
```

`DISCORD_TOKEN` を設定しない場合も、ダッシュボードのみ確認できます。ローカル環境では `ADMIN_PASSWORD` を省略できます。

ブラウザで `http://localhost:10000` を開きます。

## Renderへデプロイ

1. このリポジトリをGitHubへプッシュします。
2. Renderで **New > Blueprint** を選び、このリポジトリを接続します。
3. 作成時に次のSecretを入力します。
   - `DISCORD_TOKEN`: Discord Developer Portalで取得したBotトークン
   - `ADMIN_PASSWORD`: 管理画面で使用する十分に長いパスワード
4. デプロイ完了後、RenderのURLから管理画面を開きます。

`SESSION_SECRET` はRenderによって自動生成されます。

> Render Free Web Serviceのファイルシステムは永続化されません。再デプロイやサービス再作成に備えて、確定した初期設定は `bot_config.json` にも反映してください。

## 設定で使える変数

参加・退出・警告メッセージでは次の変数を使用できます。

| 変数 | 内容 |
| --- | --- |
| `{user}` | ユーザーへのメンション |
| `{username}` | ユーザーの表示名 |
| `{server}` | サーバー名 |
| `{member_count}` | 現在のメンバー数 |

## 組み込みコマンド

接頭辞が `!` の場合:

- `!help`: 利用可能なコマンドを表示
- `!ping`: Discordとの通信遅延を表示
- `!server`: サーバー情報を表示
- `!avatar`: 実行したユーザーのアバターURLを表示
