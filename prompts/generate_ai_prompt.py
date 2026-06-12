import json


REPORT_PATH = "reports/backtest_report.json"
PROMPT_PATH = "prompts/ai_coach_prompt.md"


def main():
    with open(PROMPT_PATH, "r") as prompt_file:
        coach_prompt = prompt_file.read()

    with open(REPORT_PATH, "r") as report_file:
        report = json.load(report_file)

    print("\n==============================")
    print("AI COACH PROMPT")
    print("==============================\n")

    print(coach_prompt)

    print("\n==============================")
    print("BACKTEST JSON REPORT")
    print("==============================\n")

    print(json.dumps(report, indent=2))

    print("\n==============================")
    print("INSTRUCTION TO AI MODEL")
    print("==============================\n")

    print(
        "Using the Turtle Lite AI Coach Prompt and the JSON backtest report above, "
        "write a plain-English explanation for a beginner user."
    )


if __name__ == "__main__":
    main()