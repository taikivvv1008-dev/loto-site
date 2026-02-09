# LotoLogic - ロト6/7予想サイト

FastAPI + 静的HTML/CSS/JS構成のロト6/7予想サービス。
Stripe決済によるサブスクリプション課金（月額550円・税込）。

## ローカル開発

```bash
# 依存インストール
pip install -r requirements.txt

# サーバー起動
uvicorn backend.app:app --reload --port 8010
```

ブラウザで `http://localhost:8010` にアクセス。

## 環境変数

`.env` ファイルをプロジェクトルートに配置してください。

| 変数名 | 説明 | 例 |
|---|---|---|
| `STRIPE_SECRET_KEY` | Stripe シークレットキー | `sk_test_...` |
| `STRIPE_PUBLISHABLE_KEY` | Stripe 公開キー | `pk_test_...` |
| `STRIPE_PRICE_ID` | Stripe Price ID (月額550円) | `price_...` |
| `STRIPE_WEBHOOK_SECRET` | Stripe Webhook 署名シークレット | `whsec_...` |
| `SECRET_KEY` | JWT署名用シークレット | ランダム文字列 |
| `DATABASE_URL` | DB接続文字列 | `sqlite:///./loto.db` |
| `ALLOWED_ORIGINS` | CORS許可オリジン (カンマ区切り) | `*` or `https://example.com` |

## API エンドポイント

### 認証
- `POST /auth/register` - ユーザー登録
- `POST /auth/login` - ログイン
- `GET /auth/me` - ログインユーザー情報取得 (要認証)

### 決済
- `POST /billing/create-checkout-session` - Stripe Checkout セッション作成 (要認証)
- `POST /billing/create-portal-session` - Stripe カスタマーポータル (要認証)
- `POST /webhook` - Stripe Webhook 受信

### 予想 (要認証 + 有料プラン)
- `GET /predict` - 予想取得
- `GET /engine/prediction` - 予想取得 (エイリアス)

### 公開
- `GET /draw/latest` - 最新抽選情報

## Render デプロイ手順

1. GitHubリポジトリをRenderに接続
2. `render.yaml` が自動検出される
3. 環境変数を設定（上記テーブル参照）
4. Stripe Dashboard で Webhook URL を設定: `https://<your-domain>/webhook`
   - イベント: `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`
5. デプロイ実行

## 技術スタック

- **Backend**: FastAPI, SQLAlchemy, python-jose (JWT), passlib (bcrypt)
- **Frontend**: 静的HTML/CSS/JS (FastAPI StaticFiles でホスティング)
- **決済**: Stripe Checkout + Customer Portal + Webhook
- **DB**: SQLite (開発) / PostgreSQL (本番推奨)
