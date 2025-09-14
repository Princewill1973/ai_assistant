import os
import openai
import requests
from flask import Flask, request, jsonify

# Accessing environment variables
openai_api_key = os.getenv("OPENAI_API_KEY")
anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
db_host = os.getenv("DB_HOST")

# Load environment variables (e.g., WHOP_API_KEY and OPENAI_API_KEY)
openai.api_key = os.getenv("OPENAI_API_KEY")
WHOP_API_KEY = os.getenv("WHOP_API_KEY")

app = Flask(__name__)

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

@app.route("/ask", methods=["POST"])
def ask():
    data = request.get_json()
    user_input = data.get("message")
    license_key = data.get("license_key")
    
    
@app.route("/", methods=["GET"])
def home():
    return "✅ Flask is running on Render! Use POST /ask with JSON { 'message': '...', 'license_key': '.}

    if not user_input or not license_key:
        return jsonify({"error": "Missing 'message' or 'license_key'"}), 400

    # Verify Whop license key
    license_info = verify_whop_license(license_key)

    if not license_info or not license_info.get("valid"):
        return jsonify({"error": "Invalid or expired license key"}), 403

    try:
        # Proceed to OpenAI if license is valid
        response = openai.Completion.create(
            engine="text-davinci-003",  # Or use gpt-3.5-turbo with openai.ChatCompletion
            prompt=user_input,
            max_tokens=150,
            n=1,
            stop=None,
            temperature=0.7
        )

        answer = response.choices[0].text.strip()
        return jsonify({"response": answer})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Optional: allow quick GET test for /ask in the browser
@app.route("/ask", methods=["GET"])
def ask_get():
    return jsonify({
        "info": "This endpoint expects POST with JSON: { 'message': '...', 'license_key': '...' }"
    })

if __name__ == "__main__":
    app.run(debug=True)
