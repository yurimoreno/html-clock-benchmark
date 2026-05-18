import os
import json
import requests
import datetime
import time
import re
import statistics as _stats
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

def static_precheck(html_code):
    """Deterministically verify criteria that regex can reliably check,
    reducing reliance on LLM judgment for objective facts."""
    code_lower = html_code.lower()

    # Update method detection
    if 'requestanimationframe' in code_lower:
        method = "rAF"
    else:
        intervals = re.findall(r'setinterval\s*\([^,]+,\s*(\d+)', code_lower)
        if intervals:
            min_interval = min(int(x) for x in intervals)
            method = "high_freq" if min_interval < 100 else "low_freq"
        else:
            method = "low_freq"

    # External script/CDN dependencies
    has_external_script = bool(re.search(r'<script[^>]+src\s*=', html_code, re.IGNORECASE))
    has_cdn = bool(re.search(
        r'(cdn\.|googleapis\.com|unpkg\.com|jsdelivr\.net|cloudflare\.com)',
        html_code, re.IGNORECASE
    ))
    zero_dependencies = not has_external_script and not has_cdn

    # Millisecond precision — only confirm True; LLM catches performance.now() etc.
    second_ms_precision = bool(re.search(r'getmilliseconds\(\)', code_lower))

    return {
        "method": method,
        "zero_dependencies": zero_dependencies,
        "second_ms_precision": second_ms_precision,
    }


def fetch_model_pricing(model_id):
    """Return {"input_per_m": float|None, "output_per_m": float|None} in $/M tokens."""
    if not OPENROUTER_API_KEY:
        return {"input_per_m": None, "output_per_m": None}
    try:
        response = requests.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
            timeout=15
        )
        response.raise_for_status()
        for m in response.json().get("data", []):
            if m["id"] == model_id:
                pricing = m.get("pricing", {})
                return {
                    "input_per_m": round(float(pricing.get("prompt", 0)) * 1_000_000, 4),
                    "output_per_m": round(float(pricing.get("completion", 0)) * 1_000_000, 4),
                }
    except Exception as e:
        print(f"Warning: Could not fetch pricing for {model_id}: {e}")
    return {"input_per_m": None, "output_per_m": None}


def generate_clock(model):
    print(f"Generating clock with {model}...")
    try:
        messages = [{"role": "user", "content": PROMPT}]
        start = time.time()
        response = call_openrouter(model, messages)
        latency_s = round(time.time() - start, 1)
        usage = response.get('usage', {})
        content = response['choices'][0]['message']['content']

        if "```html" in content:
            content = content.split("```html")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        return content, latency_s, usage
    except Exception as e:
        print(f"Error generating clock with {model}: {e}")
        return None, None, {}

def evaluate_clock(judge_model, clock_code, max_tokens=30000):
    if not clock_code:
        return None
    print(f"Evaluating clock with judge {judge_model}...")

    precheck = static_precheck(clock_code)

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
            audit_data = json.loads(json_str)
        except json.JSONDecodeError:
            # Fallback: try to strip common markdown/preamble if regex was too broad
            clean_json = json_str.strip()
            if "```json" in clean_json:
                clean_json = clean_json.split("```json")[1].split("```")[0].strip()
            elif "```" in clean_json:
                clean_json = clean_json.split("```")[1].split("```")[0].strip()
            audit_data = json.loads(clean_json)

        # Override with deterministic pre-check results
        audit_data.setdefault("smoothness", {})["method"] = precheck["method"]
        audit_data.setdefault("code", {})["zero_dependencies"] = precheck["zero_dependencies"]
        # Only upgrade to True; LLM may catch performance.now() and similar patterns regex misses
        if precheck["second_ms_precision"]:
            audit_data.setdefault("time", {})["second_ms_precision"] = True

        return audit_data

    except Exception as e:
        print(f"Error during evaluation with {judge_model}: {e}")
        return None

def _fmt_run_date(timestamp_str):
    """Convert '20260428_230837' -> 'Apr 28'."""
    try:
        dt = datetime.datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
        return dt.strftime("%b %-d")
    except Exception:
        return "—"


def _aggregate_audits(audits):
    """Merge N audit JSONs: majority vote for booleans, median for ints, mode for strings."""
    sections = set()
    for a in audits:
        sections.update(a.keys())

    result = {}
    for sec in sections:
        fields = set()
        for a in audits:
            fields.update(a.get(sec, {}).keys())
        result[sec] = {}
        for field in fields:
            vals = [a[sec][field] for a in audits if sec in a and field in a[sec]]
            if not vals:
                continue
            v = vals[0]
            if isinstance(v, bool):
                result[sec][field] = sum(bool(x) for x in vals) > len(vals) / 2
            elif isinstance(v, int):
                result[sec][field] = int(_stats.median(vals))
            elif isinstance(v, str):
                result[sec][field] = max(set(vals), key=vals.count)
            else:
                result[sec][field] = v
    return result


def evaluate_clock_reliable(judge_model, clock_code, n_runs=3, max_tokens=30000):
    """Run judge n_runs times, return (aggregated_audit, runs_completed)."""
    results = []
    for i in range(n_runs):
        print(f"  Judge run {i + 1}/{n_runs}...")
        r = evaluate_clock(judge_model, clock_code, max_tokens)
        if r is not None:
            results.append(r)
        else:
            print(f"  Judge run {i + 1} failed, continuing...")
    if not results:
        return None, 0
    if len(results) == 1:
        return results[0], 1
    return _aggregate_audits(results), len(results)


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

        pricing = fetch_model_pricing(model_name)
        audit_data, runs_completed = evaluate_clock_reliable(judge_model, html_content, n_runs=3)
        if not audit_data:
            print(f"Skipping {model_name} due to evaluation failure.")
            continue

        final_score, breakdown = calculate_score(audit_data)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        results.append({
            "model": model_name,
            "model_id": model_name,
            "file": str(file_path),
            "score": final_score,
            "breakdown": breakdown,
            "audit": audit_data,
            "latency_s": None,
            "pricing": pricing,
            "actual_cost": None,
            "token_usage": {},
            "judge_runs": runs_completed,
            "judge_runs_attempted": 3,
            "run_date": timestamp,
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

def run_benchmark(models, judge_model, judge_runs=3):
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = RUNS_DIR / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    results = []

    for model in models:
        try:
            html_content, latency_s, usage = generate_clock(model)
            if not html_content:
                print(f"Skipping evaluation for {model} due to generation failure.")
                continue

            safe_model_name = model.replace("/", "_").replace(":", "_")
            file_path = run_dir / f"{safe_model_name}.html"
            with open(file_path, "w") as f:
                f.write(html_content)

            pricing = fetch_model_pricing(model)
            actual_cost = None
            if usage and pricing.get('input_per_m') is not None:
                inp = usage.get('prompt_tokens', 0) * pricing['input_per_m'] / 1_000_000
                out = usage.get('completion_tokens', 0) * pricing.get('output_per_m', 0) / 1_000_000
                actual_cost = round(inp + out, 6)

            audit_data, runs_completed = evaluate_clock_reliable(judge_model, html_content, n_runs=judge_runs)
            if not audit_data:
                print(f"Skipping score calculation for {model} due to judge failure.")
                continue

            final_score, breakdown = calculate_score(audit_data)

            results.append({
                "model": model,
                "model_id": model,
                "file": str(file_path),
                "score": final_score,
                "breakdown": breakdown,
                "audit": audit_data,
                "latency_s": latency_s,
                "pricing": pricing,
                "actual_cost": actual_cost,
                "token_usage": usage,
                "judge_runs": runs_completed,
                "judge_runs_attempted": judge_runs,
                "run_date": timestamp,
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
                <th>Run Date</th>
                <th>Overall Score</th>
                <th>Time (30%)</th>
                <th>Visual (20%)</th>
                <th>Dial (15%)</th>
                <th>Code (15%)</th>
                <th>Motion (10%)</th>
                <th>Runs</th>
                <th>Act. Cost</th>
                <th>Gen. Latency</th>
                <th>Input $/M</th>
                <th>Output $/M</th>
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
        latency_str = f"{res.get('latency_s')}s" if res.get('latency_s') is not None else "—"
        pricing = res.get('pricing') or {}
        inp = pricing.get('input_per_m')
        out = pricing.get('output_per_m')
        input_str = f"${inp}/M" if inp is not None else "—"
        output_str = f"${out}/M" if out is not None else "—"
        run_date_str = _fmt_run_date(res.get('run_date', ''))
        runs = res.get('judge_runs', '—')
        runs_att = res.get('judge_runs_attempted', runs)
        runs_str = f"{runs}/{runs_att}" if runs != '—' else '—'
        actual_cost = res.get('actual_cost')
        cost_str = f"${actual_cost:.4f}" if actual_cost is not None else "—"

        row = f"""
        <tr>
            <td>{res['model']}</td>
            <td>{run_date_str}</td>
            <td><strong>{res['score']}</strong></td>
            <td>{res['breakdown']['time']}</td>
            <td>{res['breakdown']['visual']}</td>
            <td>{res['breakdown']['dial']}</td>
            <td>{res['breakdown']['code']}</td>
            <td>{res['breakdown']['motion']}</td>
            <td>{runs_str}</td>
            <td>{cost_str}</td>
            <td>{latency_str}</td>
            <td>{input_str}</td>
            <td>{output_str}</td>
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