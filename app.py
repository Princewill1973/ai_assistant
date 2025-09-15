import os
import time
import uuid
import json
import openai
import requests
from flask import Flask, request, jsonify, render_template, make_response

# --- Config / env ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WHOP_API_KEY = os.getenv("WHOP_API_KEY")
WHOP_WEBHOOK_SECRET = os.getenv("WHOP_WEBHOOK_SECRET", "")  # set this in Render for webhook verification
SECRET_KEY = os.getenv("FLASK_SECRET_KEY", os.urandom(24).hex())

openai.api_key = OPENAI_API_KEY

app = Flask(__name__, template_folder="templates")
app.secret_key = SECRET_KEY

# --- Simple in-memory stores (for demo/prototype only) ---
SESSIONS = {}         # session_id -> {"history": [{"role":"user"/"assistant", "content":...}, ...], "license_key": ...}
LICENSE_CACHE = {}    # license_key -> {"valid": True/False, "timestamp": epoch, "raw": {...}}
LICENSE_DB = {}       # (optionally filled by webhook) license_key -> {"status": "active"/... , "raw": {...}}

CACHE_TTL = 60 * 5   # 5 minutes cache for license checks

# --- Helpers ---
def get_session_id():
    session_id = request.cookies.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
    return session_id

def save_session_cookie(resp, session_id):
    # Set cookie for 7 days
    resp.set_cookie("session_id", session_id, max_age=7*24*3600, httponly=True, samesite="Lax")
    return resp

def cache_license(license_key, license_info):
    LICENSE_CACHE[license_key] = {"valid": license_info.get("valid", False), "timestamp": time.time(), "raw": license_info}
    return LICENSE_CACHE[license_key]

def is_license_cached_valid(license_key):
    item = LICENSE_CACHE.get(license_key)
    if not item:
        return False
    if time.time() - item["timestamp"] > CACHE_TTL:
        return False
    return item["valid"]

# --- Whop license verification ---
def verify_whop_license(license_key):
    """
    Verify license via Whop API and cache results.
    Returns the JSON response on success or None/False when invalid.
    """
    if not WHOP_API_KEY:
        app.logger.error("WHOP_API_KEY not set in env")
        return None

    # If webhook recorded activation in LICENSE_DB and it's active, skip remote call
    db_entry = LICENSE_DB.get(license_key)
    if db_entry and db_entry.get("status") in ("active", "paid"):
        app.logger.info("License found active in local LICENSE_DB (from webhook).")
        resp = {"valid": True, "source": "webhook-cache", "raw": db_entry.get("raw")}
        cache_license(license_key, resp)
        return resp

    # Check short-term cache first
    if is_license_cached_valid(license_key):
        return LICENSE_CACHE[license_key]["raw"]

    url = "https://api.whop.com/api/v2/licenses/verify"
    headers = {"Authorization": f"Bearer {WHOP_API_KEY}", "Content-Type": "application/json"}
    payload = {"key": license_key}

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        app.logger.info(f"Whop verify status: {r.status_code} body: {r.text}")
        if r.status_code == 200:
            data = r.json()
            # Whop's response shape may be different; inspect it and adjust this check.
            # Here we store the raw response and a boolean "valid" field if present.
            valid_flag = data.get("valid", True) if isinstance(data, dict) else True
            store = {"valid": valid_flag, **({"raw": data} if isinstance(data, dict) else {})}
            cache_license(license_key, store)
            return store
        else:
            app.logger.warning("Whop license verify failed (non-200).")
            # store negative result in cache to prevent hammering
            store = {"valid": False, "raw": {"status_code": r.status_code, "body": r.text}}
            cache_license(license_key, store)
            return store
    except Exception as e:
        app.logger.exception("Exception when calling Whop API")
        return None

# --- Routes ---

@app.route("/", methods=["GET"])
def home():
    return "✅ Flask is running. Visit /chat to open the assistant."

@app.route("/chat", methods=["GET"])
def chat_ui():
    session_id = get_session_id()
    if session_id not in SESSIONS:
        SESSIONS[session_id] = {"history": [], "license_key": None}
    resp = make_response(render_template("chat.html"))
    return save_session_cookie(resp, session_id)

@app.route("/ask", methods=["GET"])
def ask_get():
    return jsonify({"info": "POST JSON { message, license_key } to /ask"})

@app.route("/ask", methods=["POST"])
def ask():
    session_id = get_session_id()
    if session_id not in SESSIONS:
        SESSIONS[session_id] = {"history": [], "license_key": None}

    data = request.get_json() or {}
    user_input = data.get("message")
    license_key = data.get("license_key") or SESSIONS[session_id].get("license_key")

    if not user_input or not license_key:
        return jsonify({"error": "Missing 'message' or 'license_key'"}), 400

    # store license key in session if not already
    SESSIONS[session_id]["license_key"] = license_key

    # Verify license
    license_info = verify_whop_license(license_key)
    if not license_info or not license_info.get("valid"):
        return jsonify({"error": "Invalid or expired license key", "raw": license_info}), 403

    # Ensure history exists
    history = SESSIONS[session_id].setdefault("history", [])
    # append user message to history
    history.append({"role": "user", "content": user_input})

    try:
        # Use ChatCompletion (chat-based)
        # NOTE: model name may vary depending on availability and your OpenAI plan
        resp = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role":"system","content":"You are a helpful AI personal assistant."}] + history,
            max_tokens=300,
            temperature=0.7
        )
        answer = resp["choices"][0]["message"]["content"].strip()

        # append assistant reply to history
        history.append({"role": "assistant", "content": answer})

        # Save history back
        SESSIONS[session_id]["history"] = history

        response = jsonify({"response": answer})
        return save_session_cookie(response, session_id)
    except Exception as e:
        app.logger.exception("OpenAI request failed")
        return jsonify({"error": str(e)}), 500

# --- Whop webhook to receive purchase/license events (configure this URL in Whop) ---
@app.route("/webhook/whop", methods=["POST"])
def whop_webhook():
    # Basic verification: compare secret header or payload
    signature = request.headers.get("X-Whop-Signature", "")
    # NOTE: Whop's actual webhook signing mechanism may differ; adjust to match Whop docs.
    if WHOP_WEBHOOK_SECRET:
        if signature != WHOP_WEBHOOK_SECRET:
            app.logger.warning("Invalid webhook signature")
            return jsonify({"error":"invalid signature"}), 403

    payload = request.get_json() or {}
    app.logger.info(f"Received Whop webhook: {json.dumps(payload)[:2000]}")

    # Example: determine license_key and event type from payload
    license_key = payload.get("license_key") or payload.get("data", {}).get("key")
    event_type = payload.get("event") or payload.get("type")

    # Update local license DB with raw payload (for caching/fast lookup)
    if license_key:
        LICENSE_DB[license_key] = {"status": "active" if event_type in ("purchase", "activated", "payment_success") else event_type, "raw": payload}
        return jsonify({"ok": True})
    return jsonify({"ok": False}), 400

# --- Placeholder: Text-to-speech endpoint (implement provider inside) ---
@app.route("/tts", methods=["POST"])
def tts():
    data = request.get_json() or {}
    text = data.get("text")
    voice = data.get("voice", "default")
    if not text:
        return jsonify({"error":"missing text"}), 400

    # Integrate your preferred TTS here (ElevenLabs, Google TTS, OpenAI TTS etc.)
    # Example: call provider, store audio file on S3 or return base64 audio.
    return jsonify({"error":"tts not implemented - plug your TTS provider here"}), 501

# --- Placeholder: generate image (text -> image) ---
@app.route("/generate-image", methods=["POST"])
def generate_image():
    data = request.get_json() or {}
    prompt = data.get("prompt")
    if not prompt:
        return jsonify({"error":"missing prompt"}), 400

    # Integrate image creation provider (OpenAI image API, Stable Diffusion, etc.)
    return jsonify({"error":"image generation not implemented - plug provider"}), 501

# --- Provide upload URL for video/file uploads (S3 presigned example) ---
@app.route("/upload-url", methods=["POST"])
def upload_url():
    # You would implement S3 presigned URL generation here.
    # Client requests upload URL, server returns signed PUT URL and a public GET URL after upload.
    return jsonify({"error":"upload endpoint not implemented - implement using S3/MinIO/GCS"}), 501

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
