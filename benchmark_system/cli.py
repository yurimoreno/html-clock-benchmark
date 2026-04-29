import inquirer
import os
import requests
import sys
from runner import run_benchmark, OPENROUTER_URL

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
        # Sort by ID and filter for common providers to keep the list manageable but accurate
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

    models_options = fetch_openrouter_models()
    if not models_options:
        print("Failed to load models. Check your API key.")
        return
    
    # Filter for a subset of common "frontier" models for the default view, 
    # but allow searching the full list.
    frontier_defaults = [m for m in models_options if any(brand in m for brand in ["claude-3.5", "gpt-4o", "gemini-1.5-pro", "llama-3.1-405b"])]

    questions = [
        inquirer.Checkbox(
            "models",
            message="Select models to test (Space to select, Enter to confirm)",
            choices=models_options,
            default=[]
        ),
        inquirer.List(
            "judge",
            message="Select the judge model",
            choices=models_options,
            default="anthropic/claude-3.5-sonnet"
        )
    ]

    answers = inquirer.prompt(questions)
    
    if not answers or not answers["models"]:
        print("No models selected. Exiting.")
        return

    print(f"\nStarting benchmark with {len(answers['models'])} models...")
    print(f"Using {answers['judge']} as the judge.\n")
    
    try:
        run_benchmark(answers["models"], answers["judge"])
    except KeyboardInterrupt:
        print("\nBenchmark cancelled by user.")
    except Exception as e:
        print(f"\nCritical Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
