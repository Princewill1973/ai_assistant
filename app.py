import os
import hmac
import hashlib
import json
import requests
import boto3
import openai
from flask import Flask, request, jsonify

# ========== CONFIG ==========
app = Flask(__name__)

openai.api_key = os.getenv("OPENAI_API_KEY")
WHOP_API_KEY = os.getenv("WHOP_API_KEY")
WHOP_WEBHOOK_SECRET = os.getenv("WHOP_WEBHOOK_SECRET")

# AWS S3
s3 = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION")
)
S3_BUCKET = os.getenv("S3_BUCKET")

# ========== IN-MEMORY LICENSE STORE ==========
licenses = {}  # { license_key: {"status": "active", "user": "..."} }

# ========== HELPERS ==========

def verify_whop_license(license_key):
    """Call Whop API if not found in local DB"""
    url = "https://api.whop.com/api/v2/licenses/verify"
    headers = {"Authorization": f"Bearer {WHOP_API_KEY}"}
    data = {"key": license_key}
    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        return response.json()
    return None

def upload_to_s3(file_path, key_name, content_type):
    s3.upload_file(file_path, S3_BUCKET, key_name, ExtraArgs={'ContentType': content_type})
    return f"https://{S3_BUCKET}.s3.amazonaws.com/{key_name}"

# ========== ROUTES ==========

@app.route("/")
def home():
    return render_template("chat.html")

@app.route("/ask", methods=["POST"])
def ask():
    data = request.get_json()
    user_input = data.get("message")
    license_key = data.get("license_key")

    if not user_input or not license_key:
        return jsonify({"error": "Missing message or license_key"}), 400

    # 1. Check local DB first
    lic = licenses.get(license_key)
    if not lic or lic["status"] != "active":
        lic = verify_whop_license(license_key)
        if not lic or lic.get("data", {}).get("status") != "active":
            return jsonify({"error": "Invalid or expired license"}), 403
        # store active license in memory
        licenses[license_key] = {"status": "active", "user": lic.get("data", {}).get("user_id")}

    # 2. AI response
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": user_input}]
        )
        answer = response.choices[0].message["content"].strip()
        return jsonify({"response": answer})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ========== WHOP WEBHOOK ==========
@app.route("/webhook/whop", methods=["POST"])
def whop_webhook():
    sig = request.headers.get("Whop-Signature")
    body = request.data

    # verify HMAC
    digest = hmac.new(WHOP_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(digest, sig):
        return "Invalid signature", 400

    event = request.json
    license_key = event.get("data", {}).get("license")
    status = event.get("data", {}).get("status")

    if license_key:
        licenses[license_key] = {"status": status}
        print(f"Webhook updated license {license_key}: {status}")

    return "ok", 200

# ========== OPENAI TTS ==========
@app.route("/tts", methods=["POST"])
def tts():
    data = request.get_json()
    text = data.get("text", "Hello from AI Assistant")

    audio_file = "speech.mp3"
    with openai.audio.speech.with_streaming_response.create(
        model="gpt-4o-mini-tts",
        voice="alloy",
        input=text
    ) as response:
        response.stream_to_file(audio_file)

    url = upload_to_s3(audio_file, "speech.mp3", "audio/mpeg")
    return jsonify({"url": url})

# ========== OPENAI IMAGE ==========
@app.route("/image", methods=["POST"])
def image():
    data = request.get_json()
    prompt = data.get("prompt", "AI generated art")

    result = openai.images.generate(model="gpt-image-1", prompt=prompt, size="512x512")
    img_url = result.data[0].url
    return jsonify({"url": img_url})

# TODO: FFmpeg video generation routes can be added here.

if __name__ == "__main__":
    app.run(debug=True)
