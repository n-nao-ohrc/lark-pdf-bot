from flask import Flask, request, jsonify
import requests
import os
import json

app = Flask(__name__)

# ===== 環境変数 =====
APP_ID = os.getenv("APP_ID")
APP_SECRET = os.getenv("APP_SECRET")
APP_TOKEN = os.getenv("APP_TOKEN")
TABLE_ID = os.getenv("TABLE_ID")

# ===== Lark トークン取得 =====
def get_tenant_access_token():
    url = "https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal"
    headers = {"Content-Type": "application/json"}
    data = {
        "app_id": APP_ID,
        "app_secret": APP_SECRET
    }

    r = requests.post(url, headers=headers, json=data)
    res = r.json()
    return res.get("tenant_access_token")

# ===== Webhook =====
@app.route("/", methods=["POST"])
def webhook():
    try:
        # ----- 受信データ -----
        data = request.json
        print("RAW BODY:", data)
        print("HEADERS:", dict(request.headers))

        record_id = data.get("record_id")
        print("RECORD_ID:", record_id)

        if not record_id:
            return jsonify({"error": "record_id missing"}), 400

        # ----- 仮データ（PDF解析の代わり）-----
        items = [
            {"商品名": "テスト試薬A", "数量": 1, "金額": 1000},
            {"商品名": "テスト試薬B", "数量": 2, "金額": 2000}
        ]

        # ----- レコード作成（まずは最小構成）-----
        records = []
        for item in items:
            records.append({
                "fields": {
                    "テキスト": item["商品名"]
                }
            })

        payload = {"records": records}
        print("PAYLOAD:", json.dumps(payload, ensure_ascii=False))

        # ----- Lark API 呼び出し -----
        tenant_access_token = get_tenant_access_token()

        url = f"https://open.larksuite.com/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/records/batch_create"

        headers = {
            "Authorization": f"Bearer {tenant_access_token}",
            "Content-Type": "application/json"
        }

        r = requests.post(url, headers=headers, json=payload)

        print("LARK API STATUS:", r.status_code)
        print("LARK API RESPONSE:", r.text)

        return jsonify({
            "status": "ok"
        })

    except Exception as e:
        print("ERROR:", str(e))
        return jsonify({"error": str(e)}), 500


# ===== Health Check =====
@app.route("/", methods=["GET"])
def health():
    return "OK", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
