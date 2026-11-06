"""
Hospital Patient-Flow Analytics & Administrator Operations Dashboard
Built with Streamlit and Plotly
"""

import os
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Hospital Operations & Flow Command Center",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- CUSTOM STYLING ---
st.markdown("""
<style>
    .main-header {
        font-size: 2.1rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 0px;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #4B5563;
        margin-bottom: 20px;
    }
    .kpi-card {
        background: linear-gradient(135deg, #F8FAFC 0%, #EFF6FF 100%);
        border: 1px solid #DBEAFE;
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.04);
    }
    .kpi-title {
        font-size: 0.85rem;
        text-transform: uppercase;
        font-weight: 600;
        color: #64748B;
        letter-spacing: 0.5px;
    }
    .kpi-value {
        font-size: 1.85rem;
        font-weight: 700;
        color: #0F172A;
        margin: 4px 0;
    }
    .kpi-subtitle {
        font-size: 0.8rem;
        color: #2563EB;
        font-weight: 500;
    }
    .status-badge-green {
        background-color: #DEF7EC;
        color: #03543F;
        padding: 4px 10px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.8rem;
    }
    .status-badge-yellow {
        background-color: #FEF08A;
        color: #713F12;
        padding: 4px 10px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.8rem;
    }
    .status-badge-red {
        background-color: #FDE8E8;
        color: #9B1C1C;
        padding: 4px 10px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.8rem;
    }
</style>
""", unsafe_allow_html=True)

WAREHOUSE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "warehouse"))

# Baseline Bed Capacities by Department
DEFAULT_BED_CAPACITIES = {
    "Emergency": 65,
    "ICU": 35,
    "Cardiology": 50,
    "General Medicine": 80,
    "Orthopedics": 45,
    "Pediatrics": 35,
}


@st.cache_data(ttl=600)
def load_data():
    """
    Loads analytical datasets from warehouse/. Prefers Parquet, falls back to CSV.
    Supports both naming conventions (patient_flow_facts / enriched_admissions, etc.).
    """
    enriched_df = None
    dept_df = None
    heatmap_df = None
    daily_df = None

    def read_dataset(candidates):
        for path in candidates:
            if os.path.exists(path):
                try:
                    if path.endswith(".parquet") or os.path.isdir(path):
                        return pd.read_parquet(path)
                    elif path.endswith(".csv"):
                        return pd.read_csv(path)
                except Exception:
                    continue
        return None

    # Load Patient Flow Facts / Enriched Records
    enriched_df = read_dataset([
        os.path.join(WAREHOUSE_DIR, "patient_flow_facts.parquet"),
        os.path.join(WAREHOUSE_DIR, "patient_flow_facts"),
        os.path.join(WAREHOUSE_DIR, "enriched_admissions.parquet"),
        os.path.join(WAREHOUSE_DIR, "patient_flow_facts.csv"),
        os.path.join(WAREHOUSE_DIR, "enriched_admissions.csv"),
    ])

    # Load Department Metrics
    dept_df = read_dataset([
        os.path.join(WAREHOUSE_DIR, "dept_metrics.parquet"),
        os.path.join(WAREHOUSE_DIR, "department_metrics.parquet"),
        os.path.join(WAREHOUSE_DIR, "dept_metrics.csv"),
        os.path.join(WAREHOUSE_DIR, "department_metrics.csv"),
    ])

    # Load Heatmap / Hourly Flow Metrics
    heatmap_df = read_dataset([
        os.path.join(WAREHOUSE_DIR, "hourly_flow.parquet"),
        os.path.join(WAREHOUSE_DIR, "hourly_heatmap_metrics.parquet"),
        os.path.join(WAREHOUSE_DIR, "hourly_flow.csv"),
        os.path.join(WAREHOUSE_DIR, "hourly_heatmap_metrics.csv"),
    ])

    # Load Daily Flow Metrics
    daily_df = read_dataset([
        os.path.join(WAREHOUSE_DIR, "daily_dept_flow.parquet"),
        os.path.join(WAREHOUSE_DIR, "daily_flow_metrics.parquet"),
        os.path.join(WAREHOUSE_DIR, "daily_dept_flow.csv"),
        os.path.join(WAREHOUSE_DIR, "daily_flow_metrics.csv"),
    ])

    if enriched_df is not None:
        enriched_df["admission_timestamp"] = pd.to_datetime(enriched_df["admission_timestamp"])
        enriched_df["discharge_timestamp"] = pd.to_datetime(enriched_df["discharge_timestamp"])

    return enriched_df, dept_df, heatmap_df, daily_df


def render_header():
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown('<div class="main-header">🏥 Hospital Patient-Flow Analytics</div>', unsafe_allow_html=True)
        st.markdown('<div class="sub-header">Executive Clinical Operations & Inpatient Capacity Command Center</div>', unsafe_allow_html=True)
    with col2:
        st.markdown(
            '<div style="text-align: right; padding-top: 10px;">'
            '<span class="status-badge-green">● SYSTEM ONLINE</span><br>'
            '<small style="color: #64748B;">Data Engine: PySpark/Parquet</small>'
            '</div>',
            unsafe_allow_html=True,
        )


def render_kpi_cards(df, dept_df):
    total_admissions = len(df)
    avg_los_hours = df["los_hours"].mean()
    avg_los_days = avg_los_hours / 24.0

    # Highest utilization ward (highest volume)
    top_dept_row = dept_df.sort_values(by="total_admissions", ascending=False).iloc[0]
    highest_vol_dept = top_dept_row["department"]
    highest_vol_count = int(top_dept_row["total_admissions"])

    avg_acuity = df["acuity_score"].mean()
    crit_count = (df["acuity_score"] <= 2).sum()
    crit_pct = (crit_count / total_admissions) * 100

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-title">Total Ingested Admissions</div>
            <div class="kpi-value">{total_admissions:,}</div>
            <div class="kpi-subtitle">Across 6 Clinical Units</div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-title">System Avg LOS</div>
            <div class="kpi-value">{avg_los_hours:.1f} <span style="font-size: 1rem; color: #64748B;">hrs</span></div>
            <div class="kpi-subtitle">~{avg_los_days:.1f} Days / Patient</div>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-title">Highest Volume Ward</div>
            <div class="kpi-value" style="font-size: 1.45rem;">{highest_vol_dept}</div>
            <div class="kpi-subtitle">{highest_vol_count:,} Cases ({highest_vol_count/total_admissions*100:.1f}%)</div>
        </div>
        """, unsafe_allow_html=True)

    with col4:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-title">System Acuity Score</div>
            <div class="kpi-value">{avg_acuity:.2f} <span style="font-size: 1rem; color: #64748B;">/ 5.0</span></div>
            <div class="kpi-subtitle">{crit_pct:.1f}% Critical/Emergent (ESI 1-2)</div>
        </div>
        """, unsafe_allow_html=True)

    with col5:
        overall_mortality = (df["discharge_disposition"] == "Deceased").mean() * 100
        overall_home = (df["discharge_disposition"] == "Home").mean() * 100
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-title">Discharge to Home</div>
            <div class="kpi-value">{overall_home:.1f}%</div>
            <div class="kpi-subtitle">Mortality: {overall_mortality:.2f}%</div>
        </div>
        """, unsafe_allow_html=True)


def plot_dept_volume_los(dept_df):
    """
    Plotly interactive dual-axis chart: Volume (bars) and Average LOS (line/points).
    """
    sorted_df = dept_df.sort_values(by="total_admissions", ascending=False)

    fig = go.Figure()

    # Bar chart for Volume
    fig.add_trace(
        go.Bar(
            x=sorted_df["department"],
            y=sorted_df["total_admissions"],
            name="Total Admissions",
            marker=dict(
                color=sorted_df["total_admissions"],
                colorscale="Blues",
                showscale=False,
                line=dict(color="#1E3A8A", width=1.5)
            ),
            yaxis="y1",
            hovertemplate="<b>%{x}</b><br>Admissions: %{y:,}<extra></extra>"
        )
    )

    # Line chart for Avg LOS
    fig.add_trace(
        go.Scatter(
            x=sorted_df["department"],
            y=sorted_df["avg_los_hours"],
            name="Avg LOS (Hours)",
            mode="lines+markers+text",
            text=[f"{v:.1f}h" for v in sorted_df["avg_los_hours"]],
            textposition="top center",
            line=dict(color="#DC2626", width=3),
            marker=dict(size=9, color="#991B1B"),
            yaxis="y2",
            hovertemplate="<b>%{x}</b><br>Avg LOS: %{y:.1f} hrs<extra></extra>"
        )
    )

    fig.update_layout(
        title="<b>Department Throughput Volume vs. Average Length of Stay (LOS)</b>",
        xaxis=dict(title="Clinical Department", tickangle=-15),
        yaxis=dict(
            title="Total Admissions (Volume)",
            title_font=dict(color="#1E3A8A"),
            tickfont=dict(color="#1E3A8A"),
            showgrid=True,
            gridcolor="#E2E8F0"
        ),
        yaxis2=dict(
            title="Avg Length of Stay (Hours)",
            title_font=dict(color="#DC2626"),
            tickfont=dict(color="#DC2626"),
            overlaying="y",
            side="right",
            showgrid=False
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.04, xanchor="right", x=1),
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=420,
        margin=dict(l=50, r=50, t=60, b=40)
    )
    return fig


def plot_intake_heatmap(heatmap_df):
    """
    Plotly 24-hour intake heatmap (Day of Week vs. Hour of Day).
    """
    # Create pivot table: Rows = Day of Week, Cols = Hour (0-23)
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    pivot = heatmap_df.pivot(index="adm_day_name", columns="adm_hour", values="admission_count").fillna(0)

    # Reindex to ensure standard chronological days
    pivot = pivot.reindex([d for d in day_order if d in pivot.index])

    fig = px.imshow(
        pivot,
        labels=dict(x="Hour of Day (24-Hour Military Time)", y="Day of Week", color="Admissions"),
        x=[f"{h:02d}:00" for h in pivot.columns],
        y=pivot.index,
        color_continuous_scale="Viridis",
        aspect="auto"
    )

    fig.update_layout(
        title="<b>Patient Arrival Heatmap (Day of Week vs. Hour of Arrival)</b>",
        xaxis=dict(tickangle=-45, gridcolor="#E2E8F0"),
        yaxis=dict(gridcolor="#E2E8F0"),
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=380,
        margin=dict(l=40, r=40, t=50, b=50)
    )
    return fig


def plot_daily_timeline(daily_df, selected_departments):
    """
    Interactive daily timeline flow with department filter.
    """
    filtered = daily_df[daily_df["department"].isin(selected_departments)]

    fig = px.line(
        filtered,
        x="adm_date",
        y="daily_admissions",
        color="department",
        markers=True,
        title="<b>Daily Patient Flow & Admission Trends Over Time</b>",
        labels={"adm_date": "Admission Date", "daily_admissions": "Daily Intake Volume", "department": "Department"},
        color_discrete_sequence=px.colors.qualitative.Bold
    )

    fig.update_layout(
        plot_bgcolor="white",
        paper_bgcolor="white",
        hovermode="x unified",
        xaxis=dict(showgrid=True, gridcolor="#E2E8F0", title="Admission Date"),
        yaxis=dict(showgrid=True, gridcolor="#E2E8F0", title="Daily Admissions"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=380,
        margin=dict(l=40, r=40, t=50, b=40)
    )
    return fig


def render_bed_surge_simulator(df, dept_df, surge_pct):
    """
    Dynamic Bed Capacity & Surge Simulator:
    Simulates increased hospital volume (+0% to +100%) and identifies bed bottlenecks.
    """
    st.markdown("### 🛏️ Dynamic Bed Capacity & Surge Bottleneck Simulator")

    multiplier = 1.0 + (surge_pct / 100.0)

    # Calculate average active census per department using Little's Law:
    # L = λ * W (Active Concurrent Patients ≈ Daily Arrival Rate * Average Stay in Days)
    # Total observation span in days:
    total_days = max(1, (pd.to_datetime(df["adm_date"].max()) - pd.to_datetime(df["adm_date"].min())).days)

    sim_rows = []
    for _, row in dept_df.iterrows():
        dept = row["department"]
        baseline_bed = DEFAULT_BED_CAPACITIES.get(dept, 50)
        daily_arrival_rate = (row["total_admissions"] / total_days)
        avg_stay_days = row["avg_los_hours"] / 24.0

        baseline_active_patients = daily_arrival_rate * avg_stay_days
        projected_active = baseline_active_patients * multiplier

        occupancy_rate = (projected_active / baseline_bed) * 100.0
        overflow = max(0.0, projected_active - baseline_bed)

        if occupancy_rate > 100.0:
            status = "🚨 OVER CAPACITY"
            status_color = "#DC2626"
        elif occupancy_rate >= 85.0:
            status = "⚠️ STRAINED (≥85%)"
            status_color = "#D97706"
        else:
            status = "✅ OPTIMAL"
            status_color = "#16A34A"

        sim_rows.append({
            "Department": dept,
            "Total Beds": baseline_bed,
            "Baseline Active": round(baseline_active_patients, 1),
            "Surge Active": round(projected_active, 1),
            "Projected Occupancy (%)": round(occupancy_rate, 1),
            "Bed Deficit / Overflow": round(overflow, 1),
            "Operational Status": status,
            "status_color": status_color
        })

    sim_df = pd.DataFrame(sim_rows)

    # Surge Protocol Banner
    max_occ = sim_df["Projected Occupancy (%)"].max()
    total_overflow = sim_df["Bed Deficit / Overflow"].sum()

    if max_occ > 100:
        st.markdown(
            f'<div class="status-badge-red" style="display: block; font-size: 1rem; padding: 12px; margin-bottom: 15px;">'
            f'🚨 <b>EMERGENCY SURGE PROTOCOL ACTIVATED:</b> Projected system overflow of <b>{total_overflow:.1f} patients</b>. '
            f'Immediate diversion, discharge acceleration, and auxiliary surge units required.'
            f'</div>',
            unsafe_allow_html=True
        )
    elif max_occ >= 85:
        st.markdown(
            f'<div class="status-badge-yellow" style="display: block; font-size: 1rem; padding: 12px; margin-bottom: 15px;">'
            f'⚠️ <b>SURGE ADVISORY (YELLOW ALERT):</b> Strained ward utilization detected (&gt;85%). '
            f'Staffing call-ins and expedited bed turnaround recommended.'
            f'</div>',
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            f'<div class="status-badge-green" style="display: block; font-size: 1rem; padding: 12px; margin-bottom: 15px;">'
            f'✅ <b>NORMAL OPERATIONS:</b> All clinical wards operating within safe operational buffer thresholds (&lt;85% capacity).'
            f'</div>',
            unsafe_allow_html=True
        )

    # Visualization: Gauge or Horizontal Bar for Capacity
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=sim_df["Department"],
        x=sim_df["Total Beds"],
        name="Licensed Bed Capacity",
        orientation="h",
        marker=dict(color="#E2E8F0", line=dict(color="#94A3B8", width=1))
    ))
    fig.add_trace(go.Bar(
        y=sim_df["Department"],
        x=sim_df["Surge Active"],
        name=f"Projected Demand (+{surge_pct}% Surge)",
        orientation="h",
        marker=dict(color="#2563EB")
    ))

    # Add red line markers for 100% capacity limit
    fig.update_layout(
        barmode="overlay",
        title=f"<b>Bed Demand vs. Licensed Capacity Under +{surge_pct}% Intake Surge</b>",
        xaxis=dict(title="Concurrent Inpatients / Beds", gridcolor="#F1F5F9"),
        yaxis=dict(title="Clinical Department"),
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=320,
        margin=dict(l=40, r=40, t=50, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.04, xanchor="right", x=1)
    )
    st.plotly_chart(fig, use_container_width=True)

    # Detailed Table
    display_sim = sim_df[["Department", "Total Beds", "Baseline Active", "Surge Active", "Projected Occupancy (%)", "Bed Deficit / Overflow", "Operational Status"]]
    st.dataframe(display_sim, use_container_width=True, hide_index=True)


def render_data_explorer(df):
    st.markdown("### 📋 De-Identified Patient Admissions Explorer")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        dept_filter = st.multiselect("Department", options=sorted(df["department"].unique()), default=[])
    with col2:
        disp_filter = st.multiselect("Disposition", options=sorted(df["discharge_disposition"].unique()), default=[])
    with col3:
        acuity_filter = st.multiselect("Acuity Score", options=sorted(df["acuity_score"].unique()), default=[])
    with col4:
        search_pat = st.text_input("Search Patient or Admission ID", "").strip()

    filtered = df.copy()
    if dept_filter:
        filtered = filtered[filtered["department"].isin(dept_filter)]
    if disp_filter:
        filtered = filtered[filtered["discharge_disposition"].isin(disp_filter)]
    if acuity_filter:
        filtered = filtered[filtered["acuity_score"].isin(acuity_filter)]
    if search_pat:
        filtered = filtered[
            filtered["patient_id"].str.contains(search_pat, case=False, na=False) |
            filtered["admission_id"].str.contains(search_pat, case=False, na=False)
        ]

    st.caption(f"Showing **{len(filtered):,}** of **{len(df):,}** records")

    display_cols = [
        "admission_id", "patient_id", "department", "admission_timestamp",
        "discharge_timestamp", "los_hours", "age", "acuity_score",
        "discharge_disposition"
    ]
    st.dataframe(
        filtered[display_cols].sort_values(by="admission_timestamp", ascending=False).head(500),
        use_container_width=True,
        hide_index=True
    )

    # CSV Download Button
    csv_bytes = filtered[display_cols].to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Download Filtered Dataset (CSV)",
        data=csv_bytes,
        file_name="filtered_hospital_records.csv",
        mime="text/csv"
    )


def main():
    enriched_df, dept_df, heatmap_df, daily_df = load_data()

    if enriched_df is None or dept_df is None:
        with st.spinner("Initializing Hospital Flow Datasets for first-time deployment..."):
            try:
                import sys
                sys.path.insert(0, os.path.dirname(__file__))
                from scripts.generate_data import main as gen_data
                from scripts.spark_pipeline import main as run_pipeline
                
                # Check if raw data exists
                raw_path = os.path.join(os.path.dirname(__file__), "data", "hospital_admission_logs.csv")
                if not os.path.exists(raw_path):
                    gen_data()
                
                run_pipeline()
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Failed to bootstrap analytical warehouse: {e}")
                return

    # --- SIDEBAR CONTROLS ---
    with st.sidebar:
        st.image("https://img.icons8.com/fluency/96/hospital.png", width=64)
        st.title("Operations Controls")
        st.markdown("---")

        st.subheader("⚡ Bed Surge Simulator")
        surge_slider = st.slider(
            "Intake Surge Multiplier",
            min_value=0,
            max_value=100,
            value=25,
            step=5,
            help="Simulates an influx of patient arrivals above current baseline volume"
        )
        st.caption(f"Simulating: **+{surge_slider}% Admissions Volume**")
        st.markdown("---")

        st.subheader("🏥 Ward Filtering")
        all_departments = sorted(dept_df["department"].unique())
        selected_depts = st.multiselect(
            "Filter Visualizations",
            options=all_departments,
            default=all_departments
        )

        st.markdown("---")
        st.caption("Hospital Operational Analytics v1.0.0")
        st.caption("Engine: PySpark / Streamlit / Plotly")

    # --- MAIN VIEW ---
    render_header()
    st.markdown("---")

    render_kpi_cards(enriched_df, dept_df)
    st.markdown("<br>", unsafe_allow_html=True)

    # Main Visualizations Row 1
    tab1, tab2 = st.tabs(["📊 Executive Analytics & Trends", "🛏️ Surge Capacity Modeling"])

    with tab1:
        col_left, col_right = st.columns([1, 1])
        with col_left:
            # Volume & LOS
            filtered_dept_df = dept_df[dept_df["department"].isin(selected_depts)]
            st.plotly_chart(plot_dept_volume_los(filtered_dept_df), use_container_width=True)
        with col_right:
            # 24-hr Heatmap
            st.plotly_chart(plot_intake_heatmap(heatmap_df), use_container_width=True)

        # Timeline Flow Row
        st.plotly_chart(plot_daily_timeline(daily_df, selected_depts), use_container_width=True)

        st.markdown("---")
        # Data Explorer
        render_data_explorer(enriched_df)

    with tab2:
        render_bed_surge_simulator(enriched_df, dept_df, surge_slider)


if __name__ == "__main__":
    main()
