import os
import json
import requests
import datetime
import time
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

JUDGE_PROMPT_TEMPLATE = f"""
You are a deterministic code auditor. Your task is to audit the provided HTML/JS code for an analog clock based on the following specification:

{JUDGE_SPEC}

Analyze the code and return ONLY a valid JSON object following the "Audit JSON" schema defined in the specification. 
Do not include any markdown formatting, preamble, or explanation. Just the raw JSON.

CODE TO AUDIT:
{{code}}
"""

def call_openrouter(model, messages, stream=False):
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
    response = requests.post(OPENROUTER_URL, headers=headers, data=json.dumps(data))
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

def evaluate_clock(judge_model, clock_code):
    if not clock_code:
        return None
    print(f"Evaluating clock with judge {judge_model}...")
    prompt = JUDGE_PROMPT_TEMPLATE.format(code=clock_code)
    messages = [{"role": "user", "content": prompt}]
    response = call_openrouter(judge_model, messages)
    content = response['choices'][0]['message']['content'].strip()
    
    # Strip markdown if present
    if content.startswith("```json"):
        content = content[7:-3].strip()
    elif content.startswith("```"):
        content = content[3:-3].strip()
        
    try:
        return json.loads(content)
    except Exception as e:
        print(f"Error parsing judge response: {e}")
        print(f"Raw response: {content}")
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
    # This will be a simplified version of the main dashboard
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
        
        # Adjust path for iframe if the report is in the same dir
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
    # Example usage - would be driven by a config or CLI args
    # For now, I'll just leave the structure.
    pass
