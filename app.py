import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# =========================
# テナント設定
# =========================
TENANT_CONFIG = {
    "irp": {
        "APP_ID": os.getenv("IRP_LARK_APP_ID"),
        "APP_SECRET": os.getenv("IRP_LARK_APP_SECRET"),
        "APP_TOKEN": os.getenv("IRP_LARK_APP_TOKEN"),
    },
    "ohrc": {
        "APP_ID": os.getenv("OHRC_LARK_APP_ID"),
        "APP_SECRET": os.getenv("OHRC_LARK_APP_SECRET"),
        "APP_TOKEN": os.getenv("OHRC_LARK_APP_TOKEN"),
    }
}


# =========================
# トークン取得
# =========================
def get_tenant_access_token(app_id, app_secret):
    url = "https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal/"
    res = requests.post(url, json={
        "app_id": app_id,
        "app_secret": app_secret
    }).json()

    return res.get("tenant_access_token")


# =========================
# レコード取得
# =========================
def get_record(token, app_token, table_id, record_id):
    url = f"https://open.larksuite.com/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}"

    headers = {
        "Authorization": f"Bearer {token}"
    }

    res = requests.get(url, headers=headers).json()
    return res


# =========================
# 添付ファイルダウンロード
# =========================
def download_file(token, file_token):
    url = f"https://open.larksuite.com/open-apis/drive/v1/medias/{file_token}/download"

    headers = {
        "Authorization": f"Bearer {token}"
    }

    res = requests.get(url, headers=headers)

    return res.content


# =========================
# 子レコード作成
# =========================
def create_children(token, app_token, table_id, parent_id, items):
    url = f"https://open.larksuite.com/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    records = []
    for item in items:
        records.append({
            "fields": {
                "テキスト": f"{item['name']} ×{item['qty']}",
                "レコード種別": "子",
                "親レコード": [parent_id],
                "商品名": item["name"],
                "数量": item["qty"],
                "金額": item["price"]
            }
        })

    payload = {"records": records}

    print("PAYLOAD:", payload)

    res = requests.post(url, headers=headers, json=payload)
    print("LARK:", res.text)

    return res.json()


# =========================
# 仮のPDF解析（後で置き換え）
# =========================
def parse_pdf(file_bytes):
    # TODO: ここをGPTやOCRに置き換え
    return [
        {"name": "テスト試薬A", "qty": 1, "price": 1000},
        {"name": "テスト試薬B", "qty": 2, "price": 2000}
    ]


# =========================
# メイン
# =========================
@app.route("/", methods=["POST"])
def webhook():
    body = request.json
    print("RAW BODY:", body)

    tenant_key = body.get("tenant_key", "irp")
    table_id = body.get("table_id")
    record_id = body.get("record_id")

    print("TENANT:", tenant_key)
    print("TABLE:", table_id)
    print("RECORD:", record_id)

    config = TENANT_CONFIG.get(tenant_key)
    if not config:
        return jsonify({"error": "invalid tenant"}), 400

    token = get_tenant_access_token(config["APP_ID"], config["APP_SECRET"])

    # レコード取得
    record = get_record(token, config["APP_TOKEN"], table_id, record_id)

    fields = record["data"]["record"]["fields"]

    print("FIELDS:", fields)

    # 添付ファイル取得
    attachments = fields.get("添付ファイル", [])

    if not attachments:
        return jsonify({"error": "no attachment"}), 200

    file_token = attachments[0]["file_token"]

    print("FILE TOKEN:", file_token)

    file_bytes = download_file(token, file_token)

    print("FILE SIZE:", len(file_bytes))

    # PDF解析
    items = parse_pdf(file_bytes)

    # 子レコード作成
    result = create_children(
        token,
        config["APP_TOKEN"],
        table_id,
        record_id,
        items
    )

    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
