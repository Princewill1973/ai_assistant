import os
import json
import uuid
import requests
import subprocess
import openai
import cloudinary
import cloudinary.uploader
from flask import Flask, request, jsonify, render_template_string

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
licenses_db = {}
sessions = {}

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
    if license_key in licenses_db and licenses_db[license_key]["status"] == "active":
        return licenses_db[license_key]

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

@app.route("/ask", methods=["POST"])
def ask():
    data = request.json
    user_input = data.get("message")
    license_key = data.get("license_key")

    if not user_input or not license_key:
        return jsonify({"error": "Missing 'message' or 'license_key'"}), 400

    license_info = verify_whop_license(license_key)
    if not license_info:
        return jsonify({"error": "Invalid or expired license key"}), 403

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
        audio_file = f"tts_{uuid.uuid4().hex}.mp3"
        with openai.audio.speech.with_streaming_response.create(
            model="gpt-4o-mini-tts",
            voice="alloy",
            input=text,
        ) as response:
            response.stream_to_file(audio_file)

        output_file = f"video_{uuid.uuid4().hex}.mp4"
        generate_video(audio_file, output_file)

        url = upload_to_cloudinary(output_file, resource_type="video")
        return jsonify({"video_url": url})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -------------------------
# Experience Page (Floating Share Bar)
# -------------------------
@app.route("/experiences/<exp_id>", methods=["GET"])
def get_experience(exp_id):
    try:
        url = f"https://api.whop.com/api/v2/experiences/{exp_id}"
        headers = {"Authorization": f"Bearer {WHOP_API_KEY}"}
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            data = response.json()
            plans = data.get("plans", [])
            page_url = f"https://{request.host}/experiences/{exp_id}"

            html_template = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>{{ exp['name'] }}</title>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
                <style>
                    body { font-family: Arial, sans-serif; margin: 20px; background: #f9f9f9; }
                    .card { background: #fff; padding: 20px; border-radius: 12px; box-shadow: 0 2px 6px rgba(0,0,0,0.1); max-width: 700px; margin: auto; }
                    h1 { color: #333; font-size: 24px; }
                    .desc { margin-top: 10px; line-height: 1.5; color: #555; }
                    .plan { margin-top: 20px; padding: 15px; border: 1px solid #ddd; border-radius: 10px; background: #fafafa; }
                    .btn {
                        display: inline-block;
                        margin-top: 10px;
                        padding: 10px 16px;
                        font-size: 15px;
                        color: #fff;
                        background-color: #4CAF50;
                        border: none;
                        border-radius: 6px;
                        text-decoration: none;
                        transition: background 0.3s;
                    }
                    .btn:hover { background-color: #45a049; }

                    /* Floating Share Bar */
                    .share-bar {
                        position: fixed;
                        top: 50%;
                        left: 10px;
                        transform: translateY(-50%);
                        display: flex;
                        flex-direction: column;
                        gap: 10px;
                        z-index: 1000;
                    }
                    .share-bar a {
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        width: 40px;
                        height: 40px;
                        border-radius: 50%;
                        color: #fff;
                        font-size: 18px;
                        text-decoration: none;
                        transition: transform 0.2s;
                    }
                    .share-bar a:hover { transform: scale(1.1); }
                    .wa { background: #25D366; }
                    .fb { background: #4267B2; }
                    .li { background: #0077B5; }
                    .tw { background: #000; }
                    .em { background: #444; }
                </style>
            </head>
            <body>
                <div class="card">
                    <h1>{{ exp['name'] }}</h1>
                    <p class="desc">{{ exp.get('description', 'No description available') }}</p>
                    
                    {% if plans and plans|length > 0 %}
                        <h2>Available Plans</h2>
                        {% for plan in plans %}
                            <div class="plan">
                                <p><b>{{ plan.get('name', 'Plan') }}</b></p>
                                <p>Price: {{ plan.get('price', 'N/A') }}</p>
                                <a class="btn" href="{{ plan.get('checkout_url', '#') }}" target="_blank">💳 Buy {{ plan.get('name', '') }}</a>
                            </div>
                        {% endfor %}
                    {% else %}
                        <p><b>Price:</b> {{ exp.get('price', 'N/A') }}</p>
                        <a class="btn" href="{{ exp.get('checkout_url', '#') }}" target="_blank">💳 Buy Now</a>
                    {% endif %}
                </div>

                <!-- Floating Share Bar -->
                <div class="share-bar">
                    <a class="wa" href="https://wa.me/?text={{ page_url }}" target="_blank"><i class="fab fa-whatsapp"></i></a>
                    <a class="fb" href="https://www.facebook.com/sharer/sharer.php?u={{ page_url }}" target="_blank"><i class="fab fa-facebook"></i></a>
                    <a class="li" href="https://www.linkedin.com/sharing/share-offsite/?url={{ page_url }}" target="_blank"><i class="fab fa-linkedin"></i></a>
                    <a class="tw" href="https://twitter.com/intent/tweet?url={{ page_url }}&text=Check this experience!" target="_blank"><i class="fab fa-x-twitter"></i></a>
                    <a class="em" href="mailto:?subject=Check this experience&body={{ page_url }}" target="_blank"><i class="fas fa-envelope"></i></a>
                </div>
            </body>
            </html>
            """
            return render_template_string(html_template, exp=data, plans=plans, page_url=page_url)

        elif response.status_code == 404:
            return "<h1>❌ Experience not found</h1>", 404
        else:
            return f"<h1>⚠️ Whop API error: {response.status_code}</h1>", 500

    except Exception as e:
        return f"<h1>⚠️ Error: {str(e)}</h1>", 500

# -------------------------
# Run
# -------------------------
if __name__ == "__main__":
    app.run(debug=True)
    
