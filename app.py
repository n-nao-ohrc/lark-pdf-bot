from flask import Flask, request, jsonify
import requests
import os
import json

app = Flask(__name__)

APP_ID = os.getenv("LARK_APP_ID")
APP_SECRET = os.getenv("LARK_APP_SECRET")
APP_TOKEN = os.getenv("LARK_APP_TOKEN")
TABLE_ID = os.getenv("LARK_TABLE_ID")


def get_tenant_access_token():
    url = "https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal"
    r = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        json={"app_id": APP_ID, "app_secret": APP_SECRET},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    return data["tenant_access_token"]


def list_fields(token: str):
    url = f"https://open.larksuite.com/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/fields"
    r = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    return r.status_code, r.text, r.json() if "application/json" in r.headers.get("Content-Type", "") else {}


@app.route("/", methods=["GET"])
def health():
    return "OK", 200


@app.route("/fields", methods=["POST"])
def fields_debug():
    try:
        token = get_tenant_access_token()
        status, text, data = list_fields(token)
        print("FIELDS STATUS:", status)
        print("FIELDS RESPONSE:", text)
        return jsonify({
            "status": status,
            "data": data
        }), 200
    except Exception as e:
        print("FIELDS ERROR:", str(e))
        return jsonify({"error": str(e)}), 500


@app.route("/", methods=["POST"])
def webhook():
    try:
        data = request.get_json(silent=True)
        print("RAW BODY:", data)
        print("HEADERS:", dict(request.headers))

        if not data:
            return jsonify({"error": "invalid json"}), 400

        record_id = data.get("record_id")
        print("RECORD_ID:", record_id)

        if not record_id:
            return jsonify({"error": "record_id missing"}), 400

        token = get_tenant_access_token()

        # まずフィールド一覧を取得して field_id を特定
        fields_status, fields_text, fields_data = list_fields(token)
        print("FIELDS STATUS:", fields_status)
        print("FIELDS RESPONSE:", fields_text)

        items = fields_data.get("data", {}).get("items", [])
        text_field_id = None

        for f in items:
            # name / field_name のどちらで返る場合にも対応
            fname = f.get("field_name") or f.get("name")
            if fname == "テキスト":
                text_field_id = f.get("field_id")
                break

        if not text_field_id:
            return jsonify({
                "error": "field 'テキスト' not found",
                "fields": items
            }), 500

        # まずは1件だけ、field_id で作成して切り分け
        records = [
            {
                "fields": {
                    text_field_id: "テスト試薬A"
                }
            }
        ]

        payload = {"records": records}
        print("PAYLOAD:", json.dumps(payload, ensure_ascii=False))

        url = f"https://open.larksuite.com/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/records/batch_create"
        r = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )

        print("LARK API STATUS:", r.status_code)
        print("LARK API RESPONSE:", r.text)

        return jsonify({
            "status": "ok",
            "lark_status": r.status_code,
            "lark_response": r.json() if "application/json" in r.headers.get("Content-Type", "") else r.text
        }), 200

    except Exception as e:
        print("ERROR:", str(e))
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
