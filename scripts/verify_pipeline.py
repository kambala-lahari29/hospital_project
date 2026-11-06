"""
Automated Verification & End-to-End Testing Script
Validates Data Pipeline, Warehouse Schemas, and UI Components
"""

import os
import sys
import pandas as pd
import plotly.graph_objects as go

PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_PATH = os.path.join(PROJECT_DIR, "data", "hospital_admission_logs.csv")
WAREHOUSE_DIR = os.path.join(PROJECT_DIR, "warehouse")


def verify_raw_data():
    print("\n--- [TASK 1] Raw Data Verification ---")
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(f"Missing {DATA_PATH}")

    df = pd.read_csv(DATA_PATH)
    row_count = len(df)
    print(f"[PASS] File exists: {DATA_PATH} ({os.path.getsize(DATA_PATH) / 1024:.1f} KB)")
    print(f"[PASS] Total Records: {row_count:,} (Required: >= 2,500)")
    assert row_count >= 2500, f"Expected >= 2500 records, got {row_count}"

    expected_cols = [
        "admission_id", "patient_id", "department",
        "admission_timestamp", "discharge_timestamp",
        "age", "acuity_score", "discharge_disposition"
    ]
    for col in expected_cols:
        assert col in df.columns, f"Missing required raw column: {col}"
    print(f"[PASS] All {len(expected_cols)} raw schema columns present and valid.")
    return row_count


def verify_warehouse():
    print("\n--- [TASK 2] Analytical Warehouse Verification ---")
    required_artifacts = {
        "dept_metrics.csv": ["department", "total_admissions", "avg_los_hours", "median_los_hours", "avg_acuity"],
        "hourly_flow.csv": ["adm_day_name", "adm_hour", "admission_count", "avg_acuity"],
        "daily_dept_flow.csv": ["adm_date", "department", "daily_admissions", "avg_los_hours"],
        "patient_flow_facts.csv": ["admission_id", "department", "los_hours", "adm_hour", "acuity_label"],
    }

    # Verify patient_flow_facts folder or file
    pff_path = os.path.join(WAREHOUSE_DIR, "patient_flow_facts")
    assert os.path.exists(pff_path), f"Missing patient_flow_facts artifact at {pff_path}"
    print(f"[PASS] Validated patient_flow_facts storage at: {pff_path}")

    for filename, required_cols in required_artifacts.items():
        filepath = os.path.join(WAREHOUSE_DIR, filename)
        assert os.path.exists(filepath), f"Missing warehouse file: {filepath}"
        assert os.path.getsize(filepath) > 0, f"File is empty: {filepath}"

        df = pd.read_csv(filepath)
        assert len(df) > 0, f"No records in {filepath}"
        for col in required_cols:
            assert col in df.columns, f"Missing required column '{col}' in {filename}"
        print(f"[PASS] {filename}: {len(df):,} rows, {len(df.columns)} columns (Verified cols: {', '.join(required_cols)})")


def verify_ui_components():
    print("\n--- [TASK 3] UI & Visualizations Smoke Test ---")
    sys.path.insert(0, PROJECT_DIR)
    import app

    # 1. Test dataset loading
    enriched_df, dept_df, heatmap_df, daily_df = app.load_data()
    assert enriched_df is not None and len(enriched_df) > 0, "Failed to load enriched_df"
    assert dept_df is not None and len(dept_df) > 0, "Failed to load dept_df"
    assert heatmap_df is not None and len(heatmap_df) > 0, "Failed to load heatmap_df"
    assert daily_df is not None and len(daily_df) > 0, "Failed to load daily_df"
    print("[PASS] app.load_data() loaded all analytical datasets cleanly without exceptions.")

    # 2. Test Plotly Visualizations
    fig1 = app.plot_dept_volume_los(dept_df)
    assert isinstance(fig1, go.Figure), "plot_dept_volume_los did not return a go.Figure"
    assert len(fig1.data) >= 2, "plot_dept_volume_los must contain bar and line traces"
    print("[PASS] plot_dept_volume_los rendered successfully with dual-axis traces.")

    fig2 = app.plot_intake_heatmap(heatmap_df)
    assert isinstance(fig2, go.Figure), "plot_intake_heatmap did not return a go.Figure"
    print("[PASS] plot_intake_heatmap rendered successfully.")

    selected_depts = list(dept_df["department"].unique())
    fig3 = app.plot_daily_timeline(daily_df, selected_depts)
    assert isinstance(fig3, go.Figure), "plot_daily_timeline did not return a go.Figure"
    print("[PASS] plot_daily_timeline rendered successfully.")


def main():
    print("================================================================")
    print("  HOSPITAL PATIENT-FLOW PIPELINE AUTOMATED VERIFICATION SUITE   ")
    print("================================================================")

    row_count = verify_raw_data()
    verify_warehouse()
    verify_ui_components()

    print("\n================================================================")
    print("                 ALL VERIFICATION TESTS PASSED                   ")
    print("================================================================")


if __name__ == "__main__":
    main()
