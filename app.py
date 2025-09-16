import os
import json
import uuid
import requests
import subprocess
import openai
import cloudinary
import cloudinary.uploader
from flask import Flask, request, jsonify

# -------------------------
# Load Config
# -------------------------
with open("config.json") as f:
    config = json.load(f)

# Environment variables
openai.api_key = os.getenv("OPENAI_API_KEY")
WHOP_API_KEY = os.getenv("WHOP_API_KEY")

# Cloudinary setup
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

# Flask app
app = Flask(__name__)

# -------------------------
# In-Memory "DB"
# -------------------------
licenses_db = {}   # { license_key: {status: "active", user_id: "..."} }
sessions = {}      # { license_key: [messages] }

# -------------------------
# Helpers
# -------------------------
def upload_to_cloudinary(file_path, resource_type="auto"):
    try:
        result = cloudinary.uploader.upload(
            file_path,
            resource_type=resource_type,
            folder="ai_assistant_outputs"
        )
        return result.get("secure_url")
    except Exception as e:
        print("Cloudinary upload error:", e)
        return None

def verify_whop_license(license_key):
    # First check local DB
    if license_key in licenses_db and licenses_db[license_key]["status"] == "active":
        return licenses_db[license_key]

    # Else call Whop API
    url = "https://api.whop.com/api/v2/licenses/verify"
    headers = {"Authorization": f"Bearer {WHOP_API_KEY}", "Content-Type": "application/json"}
    data = {"key": license_key}

    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        info = response.json()
        if info.get("valid"):
            licenses_db[license_key] = {"status": "active", "user_id": info.get("user", {}).get("id")}
            return licenses_db[license_key]

    return None

def generate_video(audio_file, output_file="output.mp4"):
    intro = config["ffmpeg_templates"]["intro"]
    outro = config["ffmpeg_templates"]["outro"]

    cmd = [
        "ffmpeg", "-y",
        "-i", intro,
        "-i", audio_file,
        "-i", outro,
        "-filter_complex",
        "[0:v][0:a][1:a][2:v][2:a]concat=n=3:v=1:a=1[outv][outa]",
        "-map", "[outv]", "-map", "[outa]",
        output_file
    ]
    subprocess.run(cmd, check=True)
    return output_file

# -------------------------
# Routes
# -------------------------

@app.route("/", methods=["GET"])
def home():
    return "✅ AI Personal Assistant API is live with Cloudinary!"

# Webhook to update license status
@app.route("/whop/webhook", methods=["POST"])
def whop_webhook():
    data = request.json
    event_type = data.get("type")
    license_key = data.get("data", {}).get("license_key")

    if not license_key:
        return jsonify({"error": "no license key"}), 400

    if event_type == "license.activated":
        licenses_db[license_key] = {"status": "active", "user_id": data["data"]["user_id"]}
    elif event_type == "license.deactivated":
        licenses_db[license_key] = {"status": "inactive", "user_id": data["data"]["user_id"]}

    return jsonify({"success": True})

# Chat
@app.route("/ask", methods=["POST"])
def ask():
    data = request.json
    user_input = data.get("message")
    license_key = data.get("license_key")

    if not user_input or not license_key:
        return jsonify({"error": "Missing 'message' or 'license_key'"}), 400

    # Verify license
    license_info = verify_whop_license(license_key)
    if not license_info:
        return jsonify({"error": "Invalid or expired license key"}), 403

    # Session memory
    if license_key not in sessions:
        sessions[license_key] = []
    sessions[license_key].append({"role": "user", "content": user_input})

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=sessions[license_key],
            max_tokens=200
        )
        answer = response.choices[0].message["content"].strip()
        sessions[license_key].append({"role": "assistant", "content": answer})

        return jsonify({"response": answer})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Text-to-Speech
@app.route("/tts", methods=["POST"])
def tts():
    data = request.json
    text = data.get("text")
    license_key = data.get("license_key")

    if not text or not license_key:
        return jsonify({"error": "Missing 'text' or 'license_key'"}), 400

    if not verify_whop_license(license_key):
        return jsonify({"error": "Invalid license"}), 403

    try:
        audio_file = f"tts_{uuid.uuid4().hex}.mp3"
        with openai.audio.speech.with_streaming_response.create(
            model="gpt-4o-mini-tts",
            voice="alloy",
            input=text,
        ) as response:
            response.stream_to_file(audio_file)

        url = upload_to_cloudinary(audio_file, resource_type="video")
        return jsonify({"audio_url": url})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Text-to-Image
@app.route("/image", methods=["POST"])
def image():
    data = request.json
    prompt = data.get("prompt")
    license_key = data.get("license_key")

    if not prompt or not license_key:
        return jsonify({"error": "Missing 'prompt' or 'license_key'"}), 400

    if not verify_whop_license(license_key):
        return jsonify({"error": "Invalid license"}), 403

    try:
        result = openai.Image.create(prompt=prompt, n=1, size="512x512")
        url = result["data"][0]["url"]
        return jsonify({"image_url": url})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Text-to-Video (using FFmpeg)
@app.route("/video", methods=["POST"])
def video():
    data = request.json
    text = data.get("text")
    license_key = data.get("license_key")

    if not text or not license_key:
        return jsonify({"error": "Missing 'text' or 'license_key'"}), 400

    if not verify_whop_license(license_key):
        return jsonify({"error": "Invalid license"}), 403

    try:
        # Generate TTS
        audio_file = f"tts_{uuid.uuid4().hex}.mp3"
        with openai.audio.speech.with_streaming_response.create(
            model="gpt-4o-mini-tts",
            voice="alloy",
            input=text,
        ) as response:
            response.stream_to_file(audio_file)

        # Generate video
        output_file = f"video_{uuid.uuid4().hex}.mp4"
        generate_video(audio_file, output_file)

        url = upload_to_cloudinary(output_file, resource_type="video")
        return jsonify({"video_url": url})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -------------------------
# Run
# -------------------------
if __name__ == "__main__":
    app.run(debug=True)
