import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

WHOP_API_KEY = os.getenv("WHOP_API_KEY")
WHOP_BASE_URL = "https://api.whop.com/api/v2"   # adjust if the version/path differs

def has_active_whop_subscription(user_whop_id: str) -> bool:
    """Check via Whop API whether this user has an active subscription."""
    if not user_whop_id:
        return False
    url = f"{WHOP_BASE_URL}/members/{user_whop_id}"
    headers = {
        "Authorization": f"Bearer {WHOP_API_KEY}",
        "Accept": "application/json"
    }
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        # optionally log error
        return False
    data = resp.json()
    # inspect what the status field is in Whop's response:
    # Could be data["status"] or data["membership"]["status"] etc.
    status = data.get("status") or data.get("membership", {}).get("status")
    # Whop may have multiple states: "active", "cancelled", "expired" etc.
    return status == "active"

def get_user_whop_id_from_request(req):
    """Extract user whop ID. Could be from JWT, session, header etc."""
    # Example: from a header
    return req.headers.get("X-Whop-User-Id")
    # or if using auth tokens: decode token to get whop_id

@app.route('/ask', methods=['POST'])
def ask():
    # Step 1: authenticate user
    # (Assume you already have some auth mechanism)
    
    # Step 2: check subscription
    whop_id = get_user_whop_id_from_request(request)
    if not whop_id:
        return jsonify({"error": "Missing Whop user ID"}), 401
    
    if not has_active_whop_subscription(whop_id):
        return jsonify({"error": "No active subscription"}), 403
    
    # Step 3: process /ask logic
    # e.g. get prompt from request body, send to OpenAI etc.
    prompt = request.json.get("prompt")
    if not prompt:
        return jsonify({"error": "Missing prompt"}), 400
    
    # … your existing logic to handle ask
    answer = do_ai_respond(prompt)
    return jsonify({"answer": answer})

if __name__ == "__main__":
    app.run()
