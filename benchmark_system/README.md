# HTML Analog Clock Benchmark System

Automated system for generating and evaluating HTML analog clocks across different LLMs using OpenRouter.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Set your OpenRouter API Key in a `.env` file or export it:
   ```bash
   export OPENROUTER_API_KEY='your_key_here'
   ```

## Usage

Run the interactive CLI:
```bash
python cli.py
```

## How it works

1. **Generation**: It sends the prompt "Generate a single HTML file that displays a working analog clock showing the current time with hour, minute, and second hands." to each selected model.
2. **Storage**: Responses are saved as `.html` files in a timestamped folder under `runs/`.
3. **Evaluation**: The selected "Judge" model audits each file using the deterministic criteria defined in `JUDGE_V1.md`.
4. **Reporting**: A local `index.html` report is generated in the run folder with a scoreboard, execution metadata, and live previews.

## Scoring Rubric (v1)

- **Time Accuracy (30%)**: Continuous motion and correct offsets.
- **Visual Depth (20%)**: Shadows, gradients, and polished geometry.
- **Dial Completeness (15%)**: Proper markers and numerals.
- **Code Architecture (15%)**: Scope hygiene and responsiveness.
- **Motion Smoothness (10%)**: Update frequency and logic.
- **One-Shot Bonus (10%)**: Accurate initial frame.
