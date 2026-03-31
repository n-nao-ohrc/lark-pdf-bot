from flask import Flask, request, jsonify
import requests
import os
import json

app = Flask(__name__)


def get_tenant_config(tenant_key: str):
    tenant_key = tenant_key.upper()

    config = {
        "app_id": os.getenv(f"{tenant_key}_LARK_APP_ID"),
        "app_secret": os.getenv(f"{tenant_key}_LARK_APP_SECRET"),
        "app_token": os.getenv(f"{tenant_key}_LARK_APP_TOKEN"),
    }

    print("CONFIG:", config)
    return config


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
    return "IRP bot running", 200


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
        table_id = data.get("table_id")

        if not parent_record_id:
            return jsonify({"error": "record_id missing"}), 400
        if not tenant_key:
            return jsonify({"error": "tenant_key missing"}), 400
        if not table_id:
            return jsonify({"error": "table_id missing"}), 400

        print("TENANT:", tenant_key)
        print("TABLE ID:", table_id)
        print("PARENT RECORD:", parent_record_id)

        config = get_tenant_config(tenant_key)

        if not all(config.values()):
            return jsonify({
                "error": "config missing",
                "tenant": tenant_key,
                "config": config
            }), 500

        token = get_tenant_token(config["app_id"], config["app_secret"])

        url = f"https://open.larksuite.com/open-apis/bitable/v1/apps/{config['app_token']}/tables/{table_id}/records/batch_create"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        # 仮データ（後でPDF解析結果に置き換える）
        items = [
            {"商品名": "テスト試薬A", "数量": 1, "金額": 1000},
            {"商品名": "テスト試薬B", "数量": 2, "金額": 2000}
        ]

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

        print("LARK STATUS:", resp.status_code)
        print("LARK RESPONSE:", resp.text)

        return jsonify({
            "status": "ok",
            "tenant": tenant_key,
            "table_id": table_id,
            "lark_status": resp.status_code,
            "lark_response": resp.json() if "application/json" in resp.headers.get("Content-Type", "") else resp.text
        }), 200

    except Exception as e:
        print("ERROR:", str(e))
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
