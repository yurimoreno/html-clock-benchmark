from flask import Flask, jsonify, request, send_from_directory
import os
import sys
import datetime
import traceback
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from benchmark_system.runner import (
    generate_clock,
    evaluate_clock,
    calculate_score,
    call_openrouter,
    JUDGE_PROMPT_TEMPLATE,
    JUDGE_SPEC,
    PROMPT
)

app = Flask(__name__, static_folder=None)

LOG_FILE = "log.txt"

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

def fetch_openrouter_models():
    if not OPENROUTER_API_KEY:
        return []
    try:
        response = requests.get("https://openrouter.ai/api/v1/models", headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}"
        })
        response.raise_for_status()
        models = response.json()["data"]
        return sorted([m["id"] for m in models])
    except Exception as e:
        print(f"Warning: Could not fetch dynamic model list: {e}")
        return [
            "anthropic/claude-3.5-sonnet",
            "google/gemini-pro-1.5",
            "openai/gpt-4o",
            "meta-llama/llama-3.1-405b-instruct",
            "deepseek/deepseek-chat"
        ]

def log(message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] {message}"
    print(entry)
    with open(LOG_FILE, "a") as f:
        f.write(entry + "\n")

@app.route("/api/models", methods=["GET"])
def get_models():
    try:
        models = fetch_openrouter_models()
        return jsonify({"models": models})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/benchmark", methods=["POST"])
def run_single_benchmark():
    data = request.get_json()
    model = data.get("model")
    judge_model = data.get("judge_model")

    if not model:
        return jsonify({"error": "model is required"}), 400
    if not judge_model:
        return jsonify({"error": "judge_model is required"}), 400

    log(f"Adding model: {model}")

    try:
        log("Generating clock...")
        html_content = generate_clock(model)

        if not html_content:
            log("ERROR: Clock generation failed")
            return jsonify({"error": "Clock generation failed"}), 500

        safe_model_name = model.replace("/", "_").replace(":", "_")
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = os.path.join("runs", timestamp)
        os.makedirs(run_dir, exist_ok=True)

        file_path = os.path.join(run_dir, f"{safe_model_name}.html")
        with open(file_path, "w") as f:
            f.write(html_content)
        log(f"Clock saved to {file_path}")

        log(f"Evaluating with judge: {judge_model}")
        audit_data = evaluate_clock(judge_model, html_content)

        if not audit_data:
            log("ERROR: Evaluation failed - see judge_response.txt for details")
            judge_prompt = f"""You are a deterministic code auditor. Your task is to audit the provided HTML/JS code for an analog clock based on the following specification:

{JUDGE_SPEC}

Analyze the code and return ONLY a valid JSON object following the "Audit JSON" schema defined in the specification.
Do not include any markdown formatting, preamble, or explanation. Just the raw JSON.

CODE TO AUDIT:
{html_content}
"""
            messages = [{"role": "user", "content": judge_prompt}]
            response = call_openrouter(judge_model, messages)
            content = response['choices'][0]['message']['content'].strip()
            with open("judge_response.txt", "w") as f:
                f.write(f"MODEL: {model}\n")
                f.write(f"JUDGE: {judge_model}\n\n")
                f.write("RESPONSE:\n")
                f.write(content)
            return jsonify({"error": "Evaluation failed"}), 500

        final_score, breakdown = calculate_score(audit_data)

        log(f"Score: {final_score} | Time:{breakdown['time']} Visual:{breakdown['visual']} Dial:{breakdown['dial']} Code:{breakdown['code']} Motion:{breakdown['motion']}")

        result = {
            "model": model,
            "judge_model": judge_model,
            "timestamp": timestamp,
            "file": file_path,
            "score": final_score,
            "breakdown": breakdown,
            "audit": audit_data
        }

        summary_path = os.path.join(run_dir, "summary.json")
        with open(summary_path, "w") as f:
            import json
            json.dump(result, f, indent=2)

        return jsonify(result)

    except Exception as e:
        log(f"ERROR: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/")
def index():
    return send_from_directory(".", "index.html")

@app.route("/cloud/<path:filename>")
def cloud_static(filename):
    return send_from_directory("cloud", filename)

@app.route("/local%20/<path:filename>")
def local_static(filename):
    return send_from_directory("local ", filename)

@app.route("/runs/<path:filename>")
def runs_static(filename):
    return send_from_directory("runs", filename)

if __name__ == "__main__":
    log("Server started")
    app.run(host="0.0.0.0", port=5000, debug=False)