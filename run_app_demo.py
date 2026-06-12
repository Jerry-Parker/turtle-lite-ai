"""
Run the full Turtle Lite AI demo workflow.

This script:
1. Downloads SPY data
2. Runs the Turtle Lite backtest
3. Generates the AI-style explanation
"""

import subprocess


def run_step(name, command):
    print("\n==============================")
    print(f"RUNNING: {name}")
    print("==============================\n")

    result = subprocess.run(command, shell=True)

    if result.returncode != 0:
        raise RuntimeError(f"Step failed: {name}")

    print(f"\nCompleted: {name}")


def main():
    run_step("Download SPY data", "python download_data.py")
    run_step("Run Turtle Lite backtest", "python run_backtest.py")
    run_step("Generate AI explanation", "python generate_ai_explanation.py")

    print("\n==============================")
    print("TURTLE LITE AI DEMO COMPLETE")
    print("==============================")
    print("\nGenerated files:")
    print("- data/SPY.csv")
    print("- reports/backtest_report.json")
    print("- reports/ai_explanation.md")


if __name__ == "__main__":
    main()