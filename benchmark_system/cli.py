import inquirer
import os
import requests
import sys
from pathlib import Path
from runner import run_benchmark, evaluate_directory, RUNS_DIR

def fetch_openrouter_models():
    print("Fetching available models from OpenRouter...")
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return []
    
    try:
        response = requests.get("https://openrouter.ai/api/v1/models", headers={
            "Authorization": f"Bearer {api_key}"
        })
        response.raise_for_status()
        models = response.json()["data"]
        return sorted([m["id"] for m in models])
    except Exception as e:
        print(f"Warning: Could not fetch dynamic model list: {e}")
        return ["anthropic/claude-3.5-sonnet", "openai/gpt-4o", "google/gemini-pro-1.5"]

def main():
    print("--- HTML Clock Benchmark System ---")
    
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        api_key = input("Enter your OpenRouter API Key: ").strip()
        if api_key:
            os.environ["OPENROUTER_API_KEY"] = api_key
        else:
            print("API Key required to run.")
            return

    all_models = fetch_openrouter_models()
    if not all_models:
        print("Could not fetch models. Check your API key and connection.")
        return
    
    mode_question = [
        inquirer.List(
            "mode",
            message="What would you like to do?",
            choices=[
                ("Run Full Benchmark (Generate + Audit)", "full"),
                ("Run Evaluation Only (Audit existing folder)", "eval")
            ]
        )
    ]
    mode_answer = inquirer.prompt(mode_question)
    if not mode_answer: return

    if mode_answer["mode"] == "full":
        # Search/Filter step
        search_query = input("\nSearch/Filter models to test (e.g. 'claude'): ").strip().lower()
        filtered_models = [m for m in all_models if search_query in m.lower()]
        
        if not filtered_models:
            print(f"No models found matching '{search_query}'.")
            return

        questions = [
            inquirer.Checkbox(
                "models",
                message=f"Select models to test from {len(filtered_models)} results",
                choices=filtered_models,
                default=[]
            ),
            inquirer.List(
                "judge",
                message="Select the judge model",
                choices=all_models,
                default="anthropic/claude-3.5-sonnet"
            )
        ]
        answers = inquirer.prompt(questions)
        if answers and answers["models"]:
            print(f"\nStarting benchmark with {len(answers['models'])} models...")
            run_benchmark(answers["models"], answers["judge"])

    elif mode_answer["mode"] == "eval":
        if not RUNS_DIR.exists():
            print(f"Runs directory {RUNS_DIR} not found.")
            return

        runs = sorted([d.name for d in RUNS_DIR.iterdir() if d.is_dir()], reverse=True)
        if not runs:
            print("No previous runs found.")
            return

        eval_questions = [
            inquirer.List(
                "folder",
                message="Select a folder to evaluate",
                choices=runs
            ),
            inquirer.List(
                "judge",
                message="Select the judge model",
                choices=all_models,
                default="anthropic/claude-3.5-sonnet"
            )
        ]
        eval_answers = inquirer.prompt(eval_questions)
        if eval_answers:
            print(f"\nStarting evaluation of {eval_answers['folder']}...")
            evaluate_directory(RUNS_DIR / eval_answers["folder"], eval_answers["judge"])

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\nAn error occurred: {e}")
        sys.exit(1)
