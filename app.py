import os
import json
import math
import requests
import fitz  # PyMuPDF
from flask import Flask, request, jsonify
from openai import OpenAI

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

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)


# =========================
# Lark token 取得
# =========================
def get_tenant_access_token(app_id: str, app_secret: str) -> str:
    url = "https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal/"
    res = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=30
    )
    res.raise_for_status()
    data = res.json()
    token = data.get("tenant_access_token")
    if not token:
        raise ValueError(f"Failed to get tenant token: {data}")
    return token


# =========================
# 親レコード取得
# =========================
def get_record(token: str, app_token: str, table_id: str, record_id: str) -> dict:
    url = f"https://open.larksuite.com/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}"
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.get(url, headers=headers, timeout=30)
    res.raise_for_status()
    return res.json()


# =========================
# 添付PDFダウンロード
# =========================
def download_file(token: str, file_token: str) -> bytes:
    url = f"https://open.larksuite.com/open-apis/drive/v1/medias/{file_token}/download"
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.get(url, headers=headers, timeout=60)
    res.raise_for_status()
    return res.content


# =========================
# PDF文字抽出（PyMuPDF）
# =========================
def extract_text_from_pdf(file_bytes: bytes) -> str:
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages = []

    for i, page in enumerate(doc):
        text = page.get_text("text")
        pages.append(f"--- PAGE {i + 1} ---\n{text}")

    extracted = "\n\n".join(pages).strip()
    return extracted


# =========================
# 前処理
# =========================
def clean_extracted_text(text: str) -> str:
    """
    完全に削りすぎない範囲で、明らかなノイズを軽く減らす。
    各社フォーマット差に対応したいため、強すぎるフィルタはしない。
    """
    lines = [line.strip() for line in text.splitlines()]
    cleaned = []

    skip_keywords = [
        "TEL", "ＦＡＸ", "FAX", "登録番号", "見積有効期限",
        "納入期限", "納入場所", "支払条件"
    ]

    for line in lines:
        if not line:
            continue
        if any(k in line for k in skip_keywords):
            continue
        cleaned.append(line)

    return "\n".join(cleaned)


# =========================
# 税込計算
# =========================
def to_tax_included(amount: int, tax_category: str, tax_rate: float = 0.10) -> int:
    """
    tax_category:
      - '税込'
      - '税抜'
      - '不明'
    """
    if tax_category == "税抜":
        return int(round(amount * (1 + tax_rate)))
    return int(amount)


# =========================
# GPTで明細抽出
# =========================
def parse_pdf_with_gpt(extracted_text: str) -> list[dict]:
    prompt = f"""
あなたは日本の見積書・請求書・納品書から明細を抽出する専門家です。
以下のPDF抽出テキストから、明細行だけをJSON配列で抽出してください。

要件:
- 出力はJSON配列のみ。コードブロックや説明文は付けない。
- 各要素は必ず以下のキーを持つ:
  - 商品名: string
  - 数量: number
  - 金額: number
  - 税区分: string  # "税込" / "税抜" / "不明"
- 小計、合計、内消費税、外消費税、送料単独行、住所、電話番号、会社情報、見積番号などは除外
- 明細と判断できる行だけ抽出
- 数量と金額が両方取れない行は除外
- 金額は、その行の合計金額を優先
- 単価しかなく金額がない場合は、数量×単価で金額を算出してよい
- もし明細が税抜表示と判断できる場合は 税区分="税抜"
- もし税込表示と判断できる場合は 税区分="税込"
- 判定できない場合は 税区分="不明"
- 日本の通常税率は10%としてよいが、ここでは税込変換はせず、元の明細金額をそのまま金額に入れる
- 数量・金額は数値で出力する（カンマや円記号を除く）

PDF抽出テキスト:
{extracted_text}
""".strip()

    response = client.responses.create(
        model="gpt-5.4-mini",
        input=prompt
    )

    text = response.output_text.strip()
    print("GPT RAW OUTPUT:", text)

    items = json.loads(text)

    normalized = []
    for item in items:
        name = str(item["商品名"]).strip()
        qty = int(float(item["数量"]))
        amount = int(float(item["金額"]))
        tax_category = str(item.get("税区分", "不明")).strip()

        if tax_category not in ["税込", "税抜", "不明"]:
            tax_category = "不明"

        tax_included_amount = to_tax_included(amount, tax_category)

        normalized.append({
            "name": name,
            "qty": qty,
            "price_raw": amount,
            "tax_category": tax_category,
            "price_tax_included": tax_included_amount
        })

    return normalized


# =========================
# 子レコード作成
# =========================
def create_children(
    token: str,
    app_token: str,
    table_id: str,
    parent_id: str,
    items: list[dict]
) -> dict:
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
                "数量": int(item["qty"]),
                "金額": int(item["price_tax_included"]),
                "税区分": item["tax_category"]
            }
        })

    payload = {"records": records}
    print("PAYLOAD:", json.dumps(payload, ensure_ascii=False))

    res = requests.post(url, headers=headers, json=payload, timeout=30)
    print("LARK STATUS:", res.status_code)
    print("LARK RESPONSE:", res.text)
    res.raise_for_status()
    return res.json()


# =========================
# ヘルスチェック
# =========================
@app.route("/", methods=["GET"])
def healthcheck():
    return "multi-tenant Lark PDF bot running", 200


# =========================
# Webhook本体
# =========================
@app.route("/", methods=["POST"])
def webhook():
    try:
        raw_body = request.get_data(as_text=True)
        print("RAW BODY:", raw_body)

        data = request.get_json(silent=True)
        if data is None:
            try:
                data = json.loads(raw_body)
            except Exception:
                return jsonify({"error": "invalid json", "raw_body": raw_body}), 400

        tenant_key = data.get("tenant_key")
        table_id = data.get("table_id")
        record_id = data.get("record_id")

        if not tenant_key:
            return jsonify({"error": "tenant_key missing"}), 400
        if not table_id:
            return jsonify({"error": "table_id missing"}), 400
        if not record_id:
            return jsonify({"error": "record_id missing"}), 400

        print("TENANT:", tenant_key)
        print("TABLE:", table_id)
        print("RECORD:", record_id)

        config = TENANT_CONFIG.get(tenant_key)
        if not config:
            return jsonify({"error": f"invalid tenant_key: {tenant_key}"}), 400
        if not all(config.values()):
            return jsonify({"error": "tenant config incomplete", "tenant": tenant_key, "config": config}), 500

        token = get_tenant_access_token(config["APP_ID"], config["APP_SECRET"])

        # 親レコード取得
        record = get_record(token, config["APP_TOKEN"], table_id, record_id)
        fields = record["data"]["record"]["fields"]
        print("FIELDS:", fields)

        attachments = fields.get("添付ファイル", [])
        if not attachments:
            return jsonify({"error": "no attachment"}), 200

        # 最初のPDFを処理
        pdf_attachment = None
        for att in attachments:
            if att.get("type") == "application/pdf":
                pdf_attachment = att
                break

        if pdf_attachment is None:
            return jsonify({"error": "no pdf attachment found"}), 200

        file_token = pdf_attachment["file_token"]
        print("FILE TOKEN:", file_token)

        file_bytes = download_file(token, file_token)
        print("FILE SIZE:", len(file_bytes))

        extracted_text = extract_text_from_pdf(file_bytes)
        print("EXTRACTED TEXT PREVIEW:", extracted_text[:2000])

        if not extracted_text.strip():
            return jsonify({"error": "no text extracted from pdf"}), 500

        cleaned_text = clean_extracted_text(extracted_text)
        print("CLEANED TEXT PREVIEW:", cleaned_text[:2000])

        items = parse_pdf_with_gpt(cleaned_text)
        print("PARSED ITEMS:", items)

        if not items:
            return jsonify({"error": "no items parsed"}), 500

        result = create_children(
            token=token,
            app_token=config["APP_TOKEN"],
            table_id=table_id,
            parent_id=record_id,
            items=items
        )

        return jsonify({
            "status": "ok",
            "tenant": tenant_key,
            "table_id": table_id,
            "record_id": record_id,
            "items_count": len(items),
            "items": items,
            "lark_result": result
        }), 200

    except Exception as e:
        print("ERROR:", str(e))
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
