import os
import json
import requests
import fitz
from flask import Flask, request, jsonify
from openai import OpenAI

app = Flask(__name__)

# =========================
# 設定
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

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# =========================
# Lark token
# =========================
def get_token(app_id, app_secret):
    res = requests.post(
        "https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal/",
        json={"app_id": app_id, "app_secret": app_secret}
    )
    return res.json()["tenant_access_token"]

# =========================
# PDF
# =========================
def extract_text(file_bytes):
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    return "\n".join([p.get_text() for p in doc])

# =========================
# GPT
# =========================
def parse_with_gpt(text):
    prompt = f"""
見積書テキストから明細を抽出してください。

出力JSON:
[
  {{
    "商品名": "...",
    "数量": 1,
    "単価": 1000,
    "税区分": "税込" or "税抜"
  }}
]

ルール:
- 明細のみ
- 税抜と明記されている場合のみ「税抜」
- それ以外は「税込」
- 数量・単価必須
- 合計や小計は除外

{text}
"""

    res = client.responses.create(
        model="gpt-5.4-mini",
        input=prompt
    )

    return json.loads(res.output_text)

# =========================
# Lark登録
# =========================
def create_records(token, app_token, table_id, parent_id, items):
    url = f"https://open.larksuite.com/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    records = []
    for i in items:
        records.append({
            "fields": {
                "テキスト": f"{i['商品名']} ×{i['数量']}",
                "レコード種別": "子",
                "親レコード": [parent_id],
                "商品名": i["商品名"],
                "数量": int(i["数量"]),
                "単価": int(i["単価"]),
                "税区分": i["税区分"]
            }
        })

    res = requests.post(url, headers=headers, json={"records": records})
    return res.json()

# =========================
# API
# =========================
@app.route("/", methods=["GET", "POST"])
def root():
    if request.method == "GET":
        return "OK", 200

    data = request.json

    tenant = data["tenant_key"]
    table_id = data["table_id"]
    record_id = data["record_id"]

    config = TENANT_CONFIG[tenant]

    token = get_token(config["APP_ID"], config["APP_SECRET"])

    # レコード取得
    rec = requests.get(
        f"https://open.larksuite.com/open-apis/bitable/v1/apps/{config['APP_TOKEN']}/tables/{table_id}/records/{record_id}",
        headers={"Authorization": f"Bearer {token}"}
    ).json()

    file_token = rec["data"]["record"]["fields"]["添付ファイル"][0]["file_token"]

    # PDF取得
    file_bytes = requests.get(
        f"https://open.larksuite.com/open-apis/drive/v1/medias/{file_token}/download",
        headers={"Authorization": f"Bearer {token}"}
    ).content

    text = extract_text(file_bytes)

    items = parse_with_gpt(text)

    result = create_records(token, config["APP_TOKEN"], table_id, record_id, items)

    return jsonify(result)

# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
