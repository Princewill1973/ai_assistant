import openai
from flask import Flask, request, jsonify

# Set your OpenAI API key here
openai.api_key = 'your-openai-api-key'

app = Flask(__name__)

@app.route("/ask", methods=["POST"])
def ask():
    user_input = request.json.get("message")

    if not user_input:
        return jsonify({"error": "No input message provided"}), 400

    try:
        # Send the request to OpenAI GPT
        response = openai.Completion.create(
            engine="text-davinci-003",  # You can change to a different engine like gpt-3.5-turbo if needed
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


if __name__ == "__main__":
    app.run(debug=True)
