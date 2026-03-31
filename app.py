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
    resp = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        json={
            "app_id": LARK_APP_ID,
            "app_secret": LARK_APP_SECRET
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
        if not parent_record_id:
            return jsonify({
                "status": "error",
                "message": "record_id is missing",
                "received": data
            }), 400

        print("PARENT RECORD ID:", parent_record_id)

        token = get_tenant_token()

        url = f"https://open.larksuite.com/open-apis/bitable/v1/apps/{LARK_APP_TOKEN}/tables/{LARK_TABLE_ID}/records/batch_create"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        # 同一テーブル内で親子レコードを1件だけ試作
        records = [
            {
                "fields": {
                    "テキスト": "親子テスト",
                    "レコード種別": "子",
                    "親レコード": [parent_record_id]
                }
            }
        ]

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
