from flask import Flask, request, jsonify
import requests
import os
import json

app = Flask(__name__)


def get_tenant_config(tenant_key: str):
    tenant_key = tenant_key.upper()

    return {
        "app_id": os.getenv(f"{tenant_key}_LARK_APP_ID"),
        "app_secret": os.getenv(f"{tenant_key}_LARK_APP_SECRET"),
        "app_token": os.getenv(f"{tenant_key}_LARK_APP_TOKEN"),
        "table_id": os.getenv(f"{tenant_key}_LARK_TABLE_ID"),
    }


def get_tenant_token(app_id: str, app_secret: str):
    url = "https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal"
    resp = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        json={
            "app_id": app_id,
            "app_secret": app_secret
        },
        timeout=30
    )
    resp.raise_for_status()
    data = resp.json()
    return data["tenant_access_token"]


@app.route("/", methods=["GET"])
def healthcheck():
    return "Lark PDF bot is running", 200


@app.route("/", methods=["POST"])
def webhook():
    try:
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

        parent_record_id = data.get("record_id")
        tenant_key = data.get("tenant_key")

        if not parent_record_id:
            return jsonify({"status": "error", "message": "record_id is missing"}), 400
        if not tenant_key:
            return jsonify({"status": "error", "message": "tenant_key is missing"}), 400

        print("PARENT RECORD ID:", parent_record_id)
        print("TENANT KEY:", tenant_key)

        config = get_tenant_config(tenant_key)

        if not all(config.values()):
            return jsonify({
                "status": "error",
                "message": "Tenant config is incomplete",
                "tenant_key": tenant_key,
                "config": config
            }), 500

        token = get_tenant_token(config["app_id"], config["app_secret"])

        # まずは固定データ
        # 後でここをPDF抽出結果に置き換える
        items = [
            {"商品名": "テスト試薬A", "数量": 1, "金額": 1000},
            {"商品名": "テスト試薬B", "数量": 2, "金額": 2000}
        ]

        url = f"https://open.larksuite.com/open-apis/bitable/v1/apps/{config['app_token']}/tables/{config['table_id']}/records/batch_create"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        records = []
        for item in items:
            records.append({
                "fields": {
                    "テキスト": f"{item['商品名']} ×{item['数量']}",
                    "レコード種別": "子",
                    "親レコード": [parent_record_id],
                    "商品名": str(item["商品名"]),
                    "数量": int(item["数量"]),
                    "金額": int(item["金額"])
                }
            })

        payload = {"records": records}
        print("PAYLOAD:", json.dumps(payload, ensure_ascii=False))

        resp = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=30
        )

        print("LARK API STATUS:", resp.status_code)
        print("LARK API RESPONSE:", resp.text)

        return jsonify({
            "status": "ok",
            "tenant_key": tenant_key,
            "lark_status": resp.status_code,
            "lark_response": resp.json() if "application/json" in resp.headers.get("Content-Type", "") else resp.text
        }), 200

    except Exception as e:
        print("ERROR:", str(e))
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
