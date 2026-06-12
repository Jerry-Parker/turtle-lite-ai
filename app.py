import json
import subprocess
from pathlib import Path

import streamlit as st


REPORT_PATH = Path("reports/backtest_report.json")
EXPLANATION_PATH = Path("reports/ai_explanation.md")


st.set_page_config(
    page_title="Turtle Lite AI",
    page_icon="🐢",
    layout="wide",
)


st.title("🐢 Turtle Lite AI")
st.subheader("Educational AI paper-trading strategy demo")

st.warning(
    "This is an educational backtest only. It is not financial advice. "
    "Past performance does not guarantee future results."
)


def run_command(command):
    result = subprocess.run(command, shell=True, capture_output=True, text=True)

    if result.returncode != 0:
        st.error("Something went wrong.")
        st.code(result.stderr)
        return False

    return True


def load_json_report():
    if not REPORT_PATH.exists():
        return None

    with open(REPORT_PATH, "r") as file:
        return json.load(file)


def load_ai_explanation():
    if not EXPLANATION_PATH.exists():
        return None

    with open(EXPLANATION_PATH, "r") as file:
        return file.read()


if st.button("Run Turtle Lite Demo"):
    with st.spinner("Downloading data..."):
        if not run_command("python download_data.py"):
            st.stop()

    with st.spinner("Running backtest..."):
        if not run_command("python run_backtest.py"):
            st.stop()

    with st.spinner("Generating AI explanation..."):
        if not run_command("python generate_ai_explanation.py"):
            st.stop()

    st.success("Demo complete.")


report = load_json_report()
explanation = load_ai_explanation()

if report:
    st.divider()
    st.header("Backtest Results")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Starting Portfolio", f"${report['starting_portfolio']:,.2f}")
    col2.metric("Final Portfolio", f"${report['final_portfolio']:,.2f}")
    col3.metric("Return", f"{report['return_percent']}%")
    col4.metric("Net Profit/Loss", f"${report['net_profit_loss']:,.2f}")

    col5, col6, col7, col8 = st.columns(4)

    col5.metric("Total Trades", report["total_closed_trades"])
    col6.metric("Win Rate", f"{report['win_rate_percent']}%")
    col7.metric("Profit Factor", report["profit_factor"])
    col8.metric("Max Drawdown", f"{report['max_drawdown_percent']}%")

    st.subheader("Raw JSON Report")
    st.json(report)

if explanation:
    st.divider()
    st.header("AI Coach Explanation")
    st.markdown(explanation)
else:
    st.info("Click 'Run Turtle Lite Demo' to generate the first report.")