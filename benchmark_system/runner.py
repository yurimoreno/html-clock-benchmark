import os
import json
import requests
import datetime
import time
import re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

PROMPT = "Generate a single HTML file that displays a working analog clock showing the current time with hour, minute, and second hands."

# Setup paths relative to this script
SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent
JUDGE_SPEC_PATH = SCRIPT_DIR / "JUDGE_V1.md"
RUNS_DIR = BASE_DIR / "runs"

# Judge Prompt based on JUDGE_V1.md
if not JUDGE_SPEC_PATH.exists():
    raise FileNotFoundError(f"Could not find judge specification at {JUDGE_SPEC_PATH}")

with open(JUDGE_SPEC_PATH, "r") as f:
    JUDGE_SPEC = f.read()

JUDGE_PROMPT_TEMPLATE = (
    "You are a deterministic code auditor. Your task is to audit the provided HTML/JS code for an analog clock based on the following specification:\n\n"
    + JUDGE_SPEC +
    "\nAnalyze the code and return ONLY a valid JSON object following the \"Audit JSON\" schema defined in the specification. "
    "Do not include any markdown formatting, preamble, or explanation. Just the raw JSON.\n\n"
    "CODE TO AUDIT:\n"
)

def call_openrouter(model, messages, stream=False, timeout=120, max_tokens=None):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/yurimoreno/html-clock-benchmark",
        "X-Title": "HTML Clock Benchmark",
    }
    data = {
        "model": model,
        "messages": messages,
    }
    if max_tokens:
        data["max_tokens"] = max_tokens
    response = requests.post(OPENROUTER_URL, headers=headers, data=json.dumps(data), timeout=timeout)
    if response.status_code != 200:
        print(f"API Error {response.status_code}: {response.text}")
    response.raise_for_status()
    return response.json()

def generate_clock(model):
    print(f"Generating clock with {model}...")
    try:
        messages = [{"role": "user", "content": PROMPT}]
        response = call_openrouter(model, messages)
        content = response['choices'][0]['message']['content']

        # Simple extraction of HTML if the model wrapped it in markdown
        if "```html" in content:
            content = content.split("```html")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        return content
    except Exception as e:
        print(f"Error generating clock with {model}: {e}")
        return None

def evaluate_clock(judge_model, clock_code, max_tokens=30000):
    if not clock_code:
        return None
    print(f"Evaluating clock with judge {judge_model}...")
    prompt = JUDGE_PROMPT_TEMPLATE + clock_code
    messages = [{"role": "user", "content": prompt}]

    try:
        response = call_openrouter(judge_model, messages, max_tokens=max_tokens)
        content = response['choices'][0]['message']['content'].strip()

        # Robust JSON extraction: Find the first '{' and last '}'
        match = re.search(r"(\{.*\})", content, re.DOTALL)
        if match:
            json_str = match.group(1)
        else:
            json_str = content

        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # Fallback: try to strip common markdown/preamble if regex was too broad
            clean_json = json_str.strip()
            if "```json" in clean_json:
                clean_json = clean_json.split("```json")[1].split("```")[0].strip()
            elif "```" in clean_json:
                clean_json = clean_json.split("```")[1].split("```")[0].strip()
            return json.loads(clean_json)

    except Exception as e:
        print(f"Error during evaluation with {judge_model}: {e}")
        return None

def calculate_score(audit_data):
    if not audit_data:
        return 0, {k: 0 for k in ["time", "visual", "dial", "code", "motion"]}

    # Weights and Logic based on JUDGE_V1.md
    time_score = (
        (2.5 if audit_data.get('time', {}).get('hour_continuous') else 0) +
        (2.5 if audit_data.get('time', {}).get('minute_continuous') else 0) +
        (2.5 if audit_data.get('time', {}).get('second_ms_precision') else 0) +
        (2.5 if audit_data.get('time', {}).get('correct_12_top') else 0)
    )

    visual_score = (
        (2.0 if audit_data.get('visual', {}).get('has_shadows') else 0) +
        (2.0 if audit_data.get('visual', {}).get('has_gradients') else 0) +
        (2.0 if audit_data.get('visual', {}).get('has_hand_tails') else 0) +
        (2.0 if audit_data.get('visual', {}).get('has_center_cap') else 0) +
        (2.0 if audit_data.get('visual', {}).get('has_bezel') else 0)
    )

    dial_score = (
        (2.0 if audit_data.get('dial', {}).get('hour_ticks_count', 0) >= 12 else 0) +
        (2.0 if audit_data.get('dial', {}).get('minute_ticks_count', 0) >= 48 else 0) +
        (2.0 if audit_data.get('dial', {}).get('numerals_count', 0) >= 12 else 0) +
        (2.0 if audit_data.get('dial', {}).get('automated_marker_generation') else 0) +
        (2.0 if audit_data.get('dial', {}).get('skips_minute_at_hour') else 0)
    )

    code_score = (
        (3.0 if audit_data.get('code', {}).get('globals_count', 99) <= 2 else 0) +
        (3.0 if audit_data.get('code', {}).get('is_responsive') else 0) +
        (2.0 if audit_data.get('code', {}).get('uses_helpers') else 0) +
        (2.0 if audit_data.get('code', {}).get('zero_dependencies') else 0)
    )

    smoothness = audit_data.get('smoothness', {})
    motion_val = 10 if smoothness.get('method') == "rAF" else (7 if smoothness.get('method') == "high_freq" else 2)
    bonus = 1 if smoothness.get('zero_latency_init') else 0

    total = (time_score * 0.3) + (visual_score * 0.2) + (dial_score * 0.15) + (code_score * 0.15) + (motion_val * 0.1) + (bonus * 0.1 * 10)
    return round(total, 2), {
        "time": time_score,
        "visual": visual_score,
        "dial": dial_score,
        "code": code_score,
        "motion": motion_val
    }

def evaluate_directory(directory_path, judge_model):
    run_dir = Path(directory_path)
    if not run_dir.exists():
        print(f"Directory {run_dir} does not exist.")
        return

    summary_path = run_dir / "summary.json"
    if summary_path.exists():
        with open(summary_path, "r") as f:
            summary = json.load(f)
            prompt = summary.get("prompt", PROMPT)
    else:
        prompt = PROMPT

    html_files = list(run_dir.glob("*.html"))
    html_files = [f for f in html_files if f.name != "index.html"]

    results = []
    for file_path in html_files:
        print(f"Processing {file_path.name}...")
        with open(file_path, "r") as f:
            html_content = f.read()

        model_name = file_path.stem.replace("_", "/").replace("__", ":")

        audit_data = evaluate_clock(judge_model, html_content)
        if not audit_data:
            print(f"Skipping {model_name} due to evaluation failure.")
            continue

        final_score, breakdown = calculate_score(audit_data)
        results.append({
            "model": model_name,
            "file": str(file_path),
            "score": final_score,
            "breakdown": breakdown,
            "audit": audit_data
        })

    results.sort(key=lambda x: x['score'], reverse=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    new_summary = {
        "timestamp": timestamp,
        "reevaluation": True,
        "original_dir": str(run_dir),
        "judge_model": judge_model,
        "prompt": prompt,
        "results": results
    }

    with open(run_dir / f"summary_eval_{timestamp}.json", "w") as f:
        json.dump(new_summary, f, indent=2)

    generate_report(run_dir, new_summary)
    print(f"Evaluation complete! New report generated in {run_dir}/index.html")

def run_benchmark(models, judge_model):
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = RUNS_DIR / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    results = []

    for model in models:
        try:
            html_content = generate_clock(model)
            if not html_content:
                print(f"Skipping evaluation for {model} due to generation failure.")
                continue

            safe_model_name = model.replace("/", "_").replace(":", "_")
            file_path = run_dir / f"{safe_model_name}.html"
            with open(file_path, "w") as f:
                f.write(html_content)

            audit_data = evaluate_clock(judge_model, html_content)
            if not audit_data:
                print(f"Skipping score calculation for {model} due to judge failure.")
                continue

            final_score, breakdown = calculate_score(audit_data)

            results.append({
                "model": model,
                "file": str(file_path),
                "score": final_score,
                "breakdown": breakdown,
                "audit": audit_data
            })

        except Exception as e:
            print(f"Failed benchmark for {model}: {e}")

    # Sort results
    results.sort(key=lambda x: x['score'], reverse=True)

    # Save results summary
    summary = {
        "timestamp": timestamp,
        "judge_model": judge_model,
        "prompt": PROMPT,
        "results": results
    }
    with open(run_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    generate_report(run_dir, summary)
    print(f"Benchmark complete! Report generated in {run_dir}/index.html")

def generate_report(run_dir, summary):
    template = """
<!DOCTYPE html>
<html>
<head>
    <title>Benchmark Results - {timestamp}</title>
    <style>
        body {{ font-family: sans-serif; background: #111; color: #eee; padding: 20px; }}
        .header {{ margin-bottom: 30px; border-bottom: 1px solid #333; padding-bottom: 10px; }}
        .meta {{ color: #888; font-size: 0.9em; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 20px; }}
        .card {{ background: #222; border: 1px solid #333; border-radius: 8px; overflow: hidden; }}
        .card header {{ padding: 10px; background: #2a2a2a; display: flex; justify-content: space-between; }}
        .score {{ font-weight: bold; color: #d6f5d6; }}
        iframe {{ width: 100%; height: 400px; border: 0; background: white; }}
        .details {{ padding: 10px; font-size: 0.85em; }}
        table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
        th, td {{ text-align: left; padding: 8px; border-bottom: 1px solid #333; }}
        th {{ background: #2a2a2a; font-size: 0.8em; text-transform: uppercase; color: #666; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Clock Benchmark Results</h1>
        <div class="meta">
            Run ID: {timestamp} | Judge: {judge_model}<br>
            Prompt: "{prompt}"
        </div>
    </div>

    <table>
        <thead>
            <tr>
                <th>Model</th>
                <th>Overall Score</th>
                <th>Time (30%)</th>
                <th>Visual (20%)</th>
                <th>Dial (15%)</th>
                <th>Code (15%)</th>
                <th>Motion (10%)</th>
            </tr>
        </thead>
        <tbody>
            {table_rows}
        </tbody>
    </table>

    <div class="grid">
        {cards}
    </div>
</body>
</html>
    """

    table_rows = ""
    cards = ""

    for res in summary['results']:
        row = f"""
        <tr>
            <td>{res['model']}</td>
            <td><strong>{res['score']}</strong></td>
            <td>{res['breakdown']['time']}</td>
            <td>{res['breakdown']['visual']}</td>
            <td>{res['breakdown']['dial']}</td>
            <td>{res['breakdown']['code']}</td>
            <td>{res['breakdown']['motion']}</td>
        </tr>
        """
        table_rows += row

        iframe_src = os.path.basename(res['file'])

        card = f"""
        <div class="card">
            <header>
                <span>{res['model']}</span>
                <span class="score">{res['score']}</span>
            </header>
            <iframe src="{iframe_src}"></iframe>
            <div class="details">
                <pre style="font-size: 10px; color: #666;">{json.dumps(res['audit'], indent=2)}</pre>
            </div>
        </div>
        """
        cards += card

    html = template.format(
        timestamp=summary['timestamp'],
        judge_model=summary['judge_model'],
        prompt=summary['prompt'],
        table_rows=table_rows,
        cards=cards
    )

    with open(run_dir / "index.html", "w") as f:
        f.write(html)

if __name__ == "__main__":
    pass