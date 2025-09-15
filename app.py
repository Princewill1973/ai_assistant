import os
import hmac
import hashlib
import openai
import requests
from flask import Flask, request, jsonify, abort, session, render_template_string

# Flask setup
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "super-secret-key")  # needed for session

# Environment variables
openai.api_key = os.getenv("OPENAI_API_KEY")
WHOP_API_KEY = os.getenv("WHOP_API_KEY")
WHOP_WEBHOOK_SECRET = os.getenv("WHOP_WEBHOOK_SECRET")

# -------------------------------
# HTML template for web chat
# -------------------------------
chat_html = """
<!DOCTYPE html>
<html>
<head>
  <title>AI Personal Assistant</title>
  <style>
    body { font-family: Arial, sans-serif; background: #f4f4f9; padding: 20px; }
    #chatbox { width: 100%; max-width: 600px; margin: auto; background: white; border-radius: 10px; padding: 20px; box-shadow: 0 0 10px rgba(0,0,0,0.1);}
    .message { margin: 10px 0; }
    .user { text-align: right; color: blue; }
    .assistant { text-align: left; color: green; }
    input, button { padding: 10px; margin: 5px; }
  </style>
</head>
<body>
  <div id="chatbox">
    <h2>🤖 AI Personal Assistant</h2>
    <div id="messages"></div>
    <input id="license" type="text" placeholder="Enter your license key" style="width:100%; margin-bottom:10px;" />
    <input id="message" type="text" placeholder="Type a message..." style="width:80%;" />
    <button onclick="sendMessage()">Send</button>
  </div>

<script>
async function sendMessage() {
  const licenseKey = document.getElementById("license").value;
  const message = document.getElementById("message").value;
  if (!licenseKey || !message) {
    alert("Enter both license key and message!");
    return;
  }
  document.getElementById("messages").innerHTML += "<div class='message user'><b>You:</b> " + message + "</div>";
  document.getElementById("message").value = "";

  const res = await fetch("/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ license_key: licenseKey, message: message })
  });

  const data = await res.json();
  if (data.response) {
    document.getElementById("messages").innerHTML += "<div class='message assistant'><b>AI:</b> " + data.response + "</div>";
  } else {
    document.getElementById("messages").innerHTML += "<div class='message assistant'><b>Error:</b> " + (data.error || "Unknown error") + "</div>";
  }
}
</script>
</body>
</html>
"""

# -------------------------------
# 1️⃣ Homepage with web UI
# -------------------------------
@app.route("/", methods=["GET"])
def home():
    return render_template_string(chat_html)

# -------------------------------
# Verify license via Whop API
# -------------------------------
def verify_whop_license(license_key):
    url = "https://api.whop.com/api/v2/licenses/verify"
    headers = {
        "Authorization": f"Bearer {WHOP_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {"key": license_key}

    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        return response.json()
    return None

# -------------------------------
# 2️⃣ AI Assistant route with memory
# -------------------------------
@app.route("/ask", methods=["POST"])
def ask():
    data = request.get_json()
    user_input = data.get("message")
    license_key = data.get("license_key")

    if not user_input or not license_key:
        return jsonify({"error": "Missing 'message' or 'license_key'"}), 400

    # Verify Whop license
    license_info = verify_whop_license(license_key)
    if not license_info or not license_info.get("valid"):
        return jsonify({"error": "Invalid or expired license key"}), 403

    # Init chat history in session
    if "history" not in session:
        session["history"] = []

    # Append user input
    session["history"].append({"role": "user", "content": user_input})

    try:
        # Generate response from OpenAI Chat API
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "You are a helpful AI personal assistant."}] + session["history"],
            max_tokens=300,
            temperature=0.7
        )
        answer = response["choices"][0]["message"]["content"].strip()

        # Append assistant response
        session["history"].append({"role": "assistant", "content": answer})

        return jsonify({"response": answer})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -------------------------------
# 4️⃣ Whop Webhook verification
# -------------------------------
@app.route("/webhook/whop", methods=["POST"])
def whop_webhook():
    payload = request.data
    signature = request.headers.get("X-Whop-Signature")

    if not WHOP_WEBHOOK_SECRET:
        return abort(500, "Webhook secret not configured")

    # Compute expected signature
    expected_signature = hmac.new(
        WHOP_WEBHOOK_SECRET.encode(),
        msg=payload,
        digestmod=hashlib.sha256
    ).hexdigest()

    # Validate
    if not hmac.compare_digest(expected_signature, signature or ""):
        return abort(400, "Invalid signature")

    event = request.get_json()
    event_type = event.get("type")

    # Handle events
    if event_type == "license.activated":
        print("✅ License activated:", event)
    elif event_type == "license.revoked":
        print("❌ License revoked:", event)

    return jsonify({"status": "success"})

# -------------------------------
# Run app
# -------------------------------
if __name__ == "__main__":
    app.run(debug=True)
