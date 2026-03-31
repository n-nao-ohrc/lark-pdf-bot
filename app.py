from flask import Flask, request, jsonify
import requests
import os
import json

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
    resp.raise_for_status()
    data = resp.json()
    return data["tenant_access_token"]


@app.route("/", methods=["GET"])
def healthcheck():
    return "Lark PDF bot is running", 200


@app.route("/", methods=["POST"])
def webhook():
    raw_body = request.get_data(as_text=True)
    print("RAW BODY:", raw_body)
    print("HEADERS:", dict(request.headers))

    data = request.get_json(silent=True)

    if data is None:
        try:
            data = json.loads(raw_body)
        except Exception:
            return jsonify({
                "status": "error",
                "message": "Invalid JSON received",
                "raw_body": raw_body
            }), 400

    record_id = data.get("record_id")
    if not record_id:
        return jsonify({
            "status": "error",
            "message": "record_id is missing",
            "received": data
        }), 400

    token = get_tenant_token()

    items = [
        {"商品名": "テスト試薬A", "数量": 1, "金額": 1000},
        {"商品名": "テスト試薬B", "数量": 2, "金額": 2000}
    ]

    url = f"https://open.larksuite.com/open-apis/bitable/v1/apps/{LARK_APP_TOKEN}/tables/{LARK_TABLE_ID}/records/batch_create"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
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

    r = requests.post(url, headers=headers, json={"records": records})
    print("LARK API STATUS:", r.status_code)
    print("LARK API RESPONSE:", r.text)

    return jsonify({
        "status": "ok",
        "record_id": record_id,
        "lark_status": r.status_code
    }), 200
