from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

LARK_APP_TOKEN = os.getenv("LARK_APP_TOKEN")
LARK_TABLE_ID = os.getenv("LARK_TABLE_ID")
LARK_APP_ID = os.getenv("LARK_APP_ID")
LARK_APP_SECRET = os.getenv("LARK_APP_SECRET")

def get_tenant_token():
    url = "https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal"
    resp = requests.post(url, json={
        "app_id": LARK_APP_ID,
        "app_secret": LARK_APP_SECRET
    })
    return resp.json()["tenant_access_token"]

@app.route("/", methods=["POST"])
def webhook():
    data = request.json
    record_id = data.get("record_id")

    token = get_tenant_token()

    # 仮の明細（まずは固定でOK）
    items = [
        {"商品名": "テスト試薬A", "数量": 1, "金額": 1000},
        {"商品名": "テスト試薬B", "数量": 2, "金額": 2000}
    ]

    url = f"https://open.larksuite.com/open-apis/bitable/v1/apps/{LARK_APP_TOKEN}/tables/{LARK_TABLE_ID}/records/batch_create"

    headers = {
        "Authorization": f"Bearer {token}"
    }

    records = []
    for item in items:
        records.append({
            "fields": {
                "レコード種別": "子",
                "親ID": record_id,
                "商品名": item["商品名"],
                "数量": item["数量"],
                "金額": item["金額"]
            }
        })

    requests.post(url, headers=headers, json={"records": records})

    return jsonify({"status": "ok"})