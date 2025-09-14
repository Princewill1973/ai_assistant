import requests

# Replace this with your actual Render URL
BASE_URL = "https://ai-personal-assistant-i0rr.onrender.com//ask"

# Replace this with your real Whop license key
LICENSE_KEY = "RkTbUslM41JIVWaJkmjGtH6pIEVokzkfrK2vGtO1XkA"

def ask_ai(message):
    payload = {
        "message": message,
        "license_key": LICENSE_KEY
    }

    try:
        response = requests.post(BASE_URL, json=payload)
        response.raise_for_status()  # Raise an error for bad HTTP status codes
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"error": str(e)}

if __name__ == "__main__":
    # Example usage
    user_message = input("Ask something: ")
    result = ask
