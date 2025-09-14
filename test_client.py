import requests

# Replace this with your actual Render URL (should end with /ask)
BASE_URL = "https://ai-personal-assistant-i0rr.onrender.com//ask"

# Replace with your valid Whop license key
LICENSE_KEY = "RkTbUslM41JIVWaJkmjGtH6pIEVokzkfrK2vGtO1XkA"

def ask_ai(message):
    payload = {
        "message": message,
        "license_key": LICENSE_KEY
    }
    try:
        response = requests.post(BASE_URL, json=payload) # ✅ POST
        response.raise_for_status()  # Raise error for HTTP issues
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"error": str(e)}

if __name__ == "__main__":
    while True:
        user_message = input("Ask something (or type 'exit' to quit): ")
        if user_message.lower() == "exit":
            break
        result = ask_ai(user_message)
        print(result)
