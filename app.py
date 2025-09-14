import os
import openai
import requests
from flask import Flask, request, jsonify, render_template

# Accessing environment variables
openai_api_key = os.getenv("OPENAI_API_KEY")
anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
db_host = os.getenv("DB_HOST")

# Load environment variables (e.g., WHOP_API_KEY and OPENAI_API_KEY)
openai.api_key = openai_api_key
WHOP_API_KEY = os.getenv("WHOP_API_KEY")

app = Flask(__name__, template_folder="templates")

# Verify license via Whop API
def verify_whop_license(license_key):
    url = "https://api.whop.com/api/v2/licenses/verify"
    headers = {
        "Authorization": f"Bearer {WHOP_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "key": license_key
    }

    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        return response.json()  # License is valid
    else:
        return None  # Invalid or error


# ✅ Homepage (so browser GET / works)
@app.route("/", methods=["GET"])
def home():
    return "✅ Flask is running on Render! Use POST /ask with JSON { 'message': '...', 'license_key': '...' }"


# ✅ Serve Web Chat UI
@app.route("/chat", methods=["GET"])
def chat_ui():
    return render_template("chat.html")


# ✅ Extra GET for /ask (browser test only)
@app.route("/ask", methods=["GET"])
def ask_get():
    return jsonify({
        "info": "This endpoint expects POST with JSON: { 'message': '...', 'license_key': '...' }"
    })


# ✅ Main AI route
@app.route("/ask", methods=["POST"])
def ask():
    data = request.get_json()
    user_input = data.get("message")
    license_key = data.get("license_key")

    if not user_input or not license_key:
        return jsonify({"error": "Missing 'message' or 'license_key'"}), 400

    # Verify Whop license key
    license_info = verify_whop_license(license_key)

    if not license_info or not license_info.get("valid"):
        return jsonify({"error": "Invalid or expired license key"}), 403

    try:
        # ✅ Use Chat API (better than Completions)
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful AI personal assistant."},
                {"role": "user", "content": user_input}
            ],
            max_tokens=300,
            temperature=0.7
        )

        answer = response["choices"][0]["message"]["content"].strip()
        return jsonify({"response": answer})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)
￼Enter
