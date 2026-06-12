"""
Run the full Turtle Lite AI demo workflow.

This script:
1. Downloads market data
2. Runs the Turtle Lite backtest
3. Generates the AI-style explanation
"""

import subprocess
import sys


def run_step(name, command):
    print("\n==============================")
    print(f"RUNNING: {name}")
    print("==============================\n")

    result = subprocess.run(command, shell=True)

    if result.returncode != 0:
        raise RuntimeError(f"Step failed: {name}")

    print(f"\nCompleted: {name}")


def main():
    symbol = "SPY"

    if len(sys.argv) > 1:
        symbol = sys.argv[1].upper()

    run_step(f"Download {symbol} data", f"python download_data.py {symbol}")
    run_step(f"Run Turtle Lite backtest for {symbol}", f"python run_backtest.py {symbol}")
    run_step("Generate AI explanation", "python generate_ai_explanation.py")

    print("\n==============================")
    print("TURTLE LITE AI DEMO COMPLETE")
    print("==============================")
    print("\nGenerated files:")
    print(f"- data/{symbol}.csv")
    print("- reports/backtest_report.json")
    print("- reports/ai_explanation.md")


if __name__ == "__main__":
    main()