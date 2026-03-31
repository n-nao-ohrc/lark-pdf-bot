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
        json={
            "app_id": LARK_APP_ID,
            "app_secret": LARK_APP_SECRET
        },
        timeout=30
    )
    resp.raise_for_status()
    return resp.json()["tenant_access_token"]


def list_fields(token):
    url = f"https://open.larksuite.com/open-apis/bitable/v1/apps/{LARK_APP_TOKEN}/tables/{LARK_TABLE_ID}/fields"
    resp = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30
    )
    resp.raise_for_status()
    return resp.json()


@app.route("/", methods=["GET"])
def healthcheck():
    return "Lark PDF bot is running", 200


@app.route("/", methods=["POST"])
def webhook():
    try:
        raw_body = request.get_data(as_text=True)
        print("RAW BODY:", raw_body)

        data = request.get_json(silent=True)
        if data is None:
            data = json.loads(raw_body)

        parent_record_id = data.get("record_id")
        if not parent_record_id:
            return jsonify({"error": "record_id missing"}), 400

        print("PARENT RECORD ID:", parent_record_id)

        token = get_tenant_token()

        fields_data = list_fields(token)
        print("FIELDS:", json.dumps(fields_data, ensure_ascii=False))

        items = fields_data.get("data", {}).get("items", [])

        text_field_id = None
        record_type_field_id = None
        parent_link_field_id = None

        for f in items:
            field_name = f.get("field_name")
            if field_name == "テキスト":
                text_field_id = f.get("field_id")
            elif field_name == "レコード種別":
                record_type_field_id = f.get("field_id")
            elif field_name == "親レコード":
                parent_link_field_id = f.get("field_id")

        print("text_field_id:", text_field_id)
        print("record_type_field_id:", record_type_field_id)
        print("parent_link_field_id:", parent_link_field_id)

        if not text_field_id:
            return jsonify({"error": "テキスト field not found"}), 500
        if not record_type_field_id:
            return jsonify({"error": "レコード種別 field not found"}), 500
        if not parent_link_field_id:
            return jsonify({"error": "親レコード field not found"}), 500

        # 親レコードリンクの形式を試す
        records = [
            {
                "fields": {
                    text_field_id: "親子テスト",
                    record_type_field_id: "子",
                    parent_link_field_id: [parent_record_id]
                }
            }
        ]

        payload = {"records": records}
        print("PAYLOAD:", json.dumps(payload, ensure_ascii=False))

        url = f"https://open.larksuite.com/open-apis/bitable/v1/apps/{LARK_APP_TOKEN}/tables/{LARK_TABLE_ID}/records/batch_create"
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
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
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
