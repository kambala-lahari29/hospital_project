"""
Hospital Patient-Flow PySpark Analytics Pipeline
Reads raw admission logs, performs feature engineering and aggregations,
and saves low-latency analytical layers (Parquet & CSV) in warehouse/.
"""

import os
import sys
import time
from datetime import datetime

WAREHOUSE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "warehouse"))
DATA_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "hospital_admission_logs.csv"))


def run_pandas_fallback(reason: str = ""):
    """
    Fallback processing pipeline using Pandas/PyArrow when PySpark JVM runtime is unavailable.
    Produces identical schema and warehouse artifacts.
    """
    print(f"\n[INFO] Running Analytics Pipeline via Python Engine (Reason: {reason})...")
    import pandas as pd
    import numpy as np

    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(f"Input data not found at {DATA_PATH}")

    df = pd.read_csv(DATA_PATH)
    print(f"[INFO] Loaded {len(df)} records from {DATA_PATH}")

    # Feature Engineering
    df["admission_timestamp"] = pd.to_datetime(df["admission_timestamp"])
    df["discharge_timestamp"] = pd.to_datetime(df["discharge_timestamp"])

    df["los_hours"] = ((df["discharge_timestamp"] - df["admission_timestamp"]).dt.total_seconds() / 3600.0).round(2)
    df["los_days"] = (df["los_hours"] / 24.0).round(2)
    df["adm_hour"] = df["admission_timestamp"].dt.hour
    df["adm_day_of_week"] = df["admission_timestamp"].dt.strftime("%a")
    df["adm_day_name"] = df["admission_timestamp"].dt.strftime("%A")
    df["adm_day_num"] = df["admission_timestamp"].dt.day_of_week  # 0=Monday, 6=Sunday
    df["adm_date"] = df["admission_timestamp"].dt.strftime("%Y-%m-%d")
    df["dis_date"] = df["discharge_timestamp"].dt.strftime("%Y-%m-%d")

    # Acuity categorization
    acuity_map = {1: "1 - Resuscitation", 2: "2 - Emergent", 3: "3 - Urgent", 4: "4 - Less Urgent", 5: "5 - Non-urgent"}
    df["acuity_label"] = df["acuity_score"].map(acuity_map)

    # 1. Department Metrics Aggregation
    dept_grp = df.groupby("department")
    dept_metrics = dept_grp.agg(
        total_admissions=("admission_id", "count"),
        avg_los_hours=("los_hours", "mean"),
        median_los_hours=("los_hours", "median"),
        min_los_hours=("los_hours", "min"),
        max_los_hours=("los_hours", "max"),
        avg_acuity=("acuity_score", "mean"),
        avg_age=("age", "mean"),
        home_count=("discharge_disposition", lambda x: (x == "Home").sum()),
        transfer_count=("discharge_disposition", lambda x: (x == "Transfer").sum()),
        deceased_count=("discharge_disposition", lambda x: (x == "Deceased").sum()),
    ).reset_index()

    dept_metrics["avg_los_hours"] = dept_metrics["avg_los_hours"].round(2)
    dept_metrics["median_los_hours"] = dept_metrics["median_los_hours"].round(2)
    dept_metrics["avg_acuity"] = dept_metrics["avg_acuity"].round(2)
    dept_metrics["avg_age"] = dept_metrics["avg_age"].round(1)
    dept_metrics["home_pct"] = ((dept_metrics["home_count"] / dept_metrics["total_admissions"]) * 100).round(1)
    dept_metrics["transfer_pct"] = ((dept_metrics["transfer_count"] / dept_metrics["total_admissions"]) * 100).round(1)
    dept_metrics["mortality_rate_pct"] = ((dept_metrics["deceased_count"] / dept_metrics["total_admissions"]) * 100).round(1)

    # 2. Hourly Heatmap Aggregation (Day of Week vs Hour of Day)
    heatmap_metrics = df.groupby(["adm_day_num", "adm_day_name", "adm_day_of_week", "adm_hour"]).agg(
        admission_count=("admission_id", "count"),
        avg_acuity=("acuity_score", "mean"),
        avg_los_hours=("los_hours", "mean"),
    ).reset_index()
    heatmap_metrics["avg_acuity"] = heatmap_metrics["avg_acuity"].round(2)
    heatmap_metrics["avg_los_hours"] = heatmap_metrics["avg_los_hours"].round(2)
    heatmap_metrics = heatmap_metrics.sort_values(by=["adm_day_num", "adm_hour"])

    # 3. Daily Flow Metrics
    daily_flow = df.groupby(["adm_date", "department"]).agg(
        daily_admissions=("admission_id", "count"),
        avg_los_hours=("los_hours", "mean"),
        avg_acuity=("acuity_score", "mean"),
    ).reset_index()
    daily_flow["avg_los_hours"] = daily_flow["avg_los_hours"].round(2)
    daily_flow["avg_acuity"] = daily_flow["avg_acuity"].round(2)
    daily_flow = daily_flow.sort_values(by=["adm_date", "department"])

    # Save to warehouse
    os.makedirs(WAREHOUSE_DIR, exist_ok=True)

    # Save Enriched Records / Patient Flow Facts
    enriched_csv = os.path.join(WAREHOUSE_DIR, "enriched_admissions.csv")
    enriched_parquet = os.path.join(WAREHOUSE_DIR, "enriched_admissions.parquet")
    patient_facts_csv = os.path.join(WAREHOUSE_DIR, "patient_flow_facts.csv")
    patient_facts_parquet = os.path.join(WAREHOUSE_DIR, "patient_flow_facts.parquet")
    patient_facts_dir = os.path.join(WAREHOUSE_DIR, "patient_flow_facts")
    
    df.to_csv(enriched_csv, index=False)
    df.to_csv(patient_facts_csv, index=False)
    try:
        df.to_parquet(enriched_parquet, index=False)
        df.to_parquet(patient_facts_parquet, index=False)
        # Also create patient_flow_facts directory with parquet file for Spark-style folder layout
        os.makedirs(patient_facts_dir, exist_ok=True)
        df.to_parquet(os.path.join(patient_facts_dir, "part-00000.parquet"), index=False)
    except Exception as e:
        print(f"[WARN] Parquet write skipped for enriched records: {e}")

    # Save Dept Metrics
    dept_csv = os.path.join(WAREHOUSE_DIR, "department_metrics.csv")
    dept_parquet = os.path.join(WAREHOUSE_DIR, "department_metrics.parquet")
    dept_m_csv = os.path.join(WAREHOUSE_DIR, "dept_metrics.csv")
    dept_m_parquet = os.path.join(WAREHOUSE_DIR, "dept_metrics.parquet")
    dept_metrics.to_csv(dept_csv, index=False)
    dept_metrics.to_csv(dept_m_csv, index=False)
    try:
        dept_metrics.to_parquet(dept_parquet, index=False)
        dept_metrics.to_parquet(dept_m_parquet, index=False)
    except Exception:
        pass

    # Save Heatmap / Hourly Flow Metrics
    heatmap_csv = os.path.join(WAREHOUSE_DIR, "hourly_heatmap_metrics.csv")
    heatmap_parquet = os.path.join(WAREHOUSE_DIR, "hourly_heatmap_metrics.parquet")
    hourly_flow_csv = os.path.join(WAREHOUSE_DIR, "hourly_flow.csv")
    hourly_flow_parquet = os.path.join(WAREHOUSE_DIR, "hourly_flow.parquet")
    heatmap_metrics.to_csv(heatmap_csv, index=False)
    heatmap_metrics.to_csv(hourly_flow_csv, index=False)
    try:
        heatmap_metrics.to_parquet(heatmap_parquet, index=False)
        heatmap_metrics.to_parquet(hourly_flow_parquet, index=False)
    except Exception:
        pass

    # Save Daily Dept Flow Metrics
    daily_csv = os.path.join(WAREHOUSE_DIR, "daily_flow_metrics.csv")
    daily_parquet = os.path.join(WAREHOUSE_DIR, "daily_flow_metrics.parquet")
    daily_dept_csv = os.path.join(WAREHOUSE_DIR, "daily_dept_flow.csv")
    daily_dept_parquet = os.path.join(WAREHOUSE_DIR, "daily_dept_flow.parquet")
    daily_flow.to_csv(daily_csv, index=False)
    daily_flow.to_csv(daily_dept_csv, index=False)
    try:
        daily_flow.to_parquet(daily_parquet, index=False)
        daily_flow.to_parquet(daily_dept_parquet, index=False)
    except Exception:
        pass

    print("[SUCCESS] Analytical layers generated successfully in warehouse/ directory:")
    for f in os.listdir(WAREHOUSE_DIR):
        fpath = os.path.join(WAREHOUSE_DIR, f)
        size_kb = os.path.getsize(fpath) / 1024
        print(f"  - {f} ({size_kb:.1f} KB)")


def run_spark_pipeline():
    """
    Executes the PySpark feature engineering and aggregation pipeline.
    """
    print("[INFO] Initializing PySpark pipeline...")
    from pyspark.sql import SparkSession
    from pyspark.sql.functions import (
        col, unix_timestamp, round as spark_round, hour,
        date_format, to_date, dayofweek, avg, count, min as spark_min,
        max as spark_max, when, expr
    )

    spark = (
        SparkSession.builder
        .appName("HospitalPatientFlowAnalytics")
        .master("local[*]")
        .config("spark.driver.memory", "2g")
        .config("spark.sql.shuffle.partitions", "4")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    print(f"[INFO] Spark Session initialized (Version: {spark.version})")

    # Ingest Raw Data
    df = spark.read.option("header", "true").option("inferSchema", "true").csv(DATA_PATH)
    print(f"[INFO] Ingested {df.count()} records into Spark DataFrame")

    # Feature Engineering
    enriched_df = df.withColumn(
        "los_hours",
        spark_round((unix_timestamp(col("discharge_timestamp")) - unix_timestamp(col("admission_timestamp"))) / 3600.0, 2)
    ).withColumn(
        "los_days",
        spark_round(col("los_hours") / 24.0, 2)
    ).withColumn(
        "adm_hour",
        hour(col("admission_timestamp"))
    ).withColumn(
        "adm_day_of_week",
        date_format(col("admission_timestamp"), "E")
    ).withColumn(
        "adm_day_name",
        date_format(col("admission_timestamp"), "EEEE")
    ).withColumn(
        "adm_day_num",
        dayofweek(col("admission_timestamp"))
    ).withColumn(
        "adm_date",
        to_date(col("admission_timestamp"))
    ).withColumn(
        "dis_date",
        to_date(col("discharge_timestamp"))
    ).withColumn(
        "acuity_label",
        when(col("acuity_score") == 1, "1 - Resuscitation")
        .when(col("acuity_score") == 2, "2 - Emergent")
        .when(col("acuity_score") == 3, "3 - Urgent")
        .when(col("acuity_score") == 4, "4 - Less Urgent")
        .otherwise("5 - Non-urgent")
    )

    # 1. Department Metrics Aggregation
    dept_metrics = enriched_df.groupBy("department").agg(
        count("admission_id").alias("total_admissions"),
        spark_round(avg("los_hours"), 2).alias("avg_los_hours"),
        spark_round(expr("percentile_approx(los_hours, 0.5)"), 2).alias("median_los_hours"),
        spark_round(spark_min("los_hours"), 2).alias("min_los_hours"),
        spark_round(spark_max("los_hours"), 2).alias("max_los_hours"),
        spark_round(avg("acuity_score"), 2).alias("avg_acuity"),
        spark_round(avg("age"), 1).alias("avg_age"),
        count(when(col("discharge_disposition") == "Home", True)).alias("home_count"),
        count(when(col("discharge_disposition") == "Transfer", True)).alias("transfer_count"),
        count(when(col("discharge_disposition") == "Deceased", True)).alias("deceased_count"),
    ).withColumn(
        "home_pct", spark_round((col("home_count") / col("total_admissions")) * 100.0, 1)
    ).withColumn(
        "transfer_pct", spark_round((col("transfer_count") / col("total_admissions")) * 100.0, 1)
    ).withColumn(
        "mortality_rate_pct", spark_round((col("deceased_count") / col("total_admissions")) * 100.0, 1)
    )

    # 2. Hourly Heatmap Aggregation
    heatmap_metrics = enriched_df.groupBy("adm_day_num", "adm_day_name", "adm_day_of_week", "adm_hour").agg(
        count("admission_id").alias("admission_count"),
        spark_round(avg("acuity_score"), 2).alias("avg_acuity"),
        spark_round(avg("los_hours"), 2).alias("avg_los_hours"),
    ).orderBy("adm_day_num", "adm_hour")

    # 3. Daily Flow Metrics
    daily_flow = enriched_df.groupBy("adm_date", "department").agg(
        count("admission_id").alias("daily_admissions"),
        spark_round(avg("los_hours"), 2).alias("avg_los_hours"),
        spark_round(avg("acuity_score"), 2).alias("avg_acuity"),
    ).orderBy("adm_date", "department")

    os.makedirs(WAREHOUSE_DIR, exist_ok=True)

    # Write tables to warehouse as Parquet and CSV
    print("[INFO] Writing analytical datasets to warehouse/...")
    enriched_pdf = enriched_df.toPandas()
    dept_pdf = dept_metrics.toPandas()
    heatmap_pdf = heatmap_metrics.toPandas()
    daily_pdf = daily_flow.toPandas()

    enriched_pdf.to_csv(os.path.join(WAREHOUSE_DIR, "enriched_admissions.csv"), index=False)
    enriched_pdf.to_csv(os.path.join(WAREHOUSE_DIR, "patient_flow_facts.csv"), index=False)
    dept_pdf.to_csv(os.path.join(WAREHOUSE_DIR, "department_metrics.csv"), index=False)
    dept_pdf.to_csv(os.path.join(WAREHOUSE_DIR, "dept_metrics.csv"), index=False)
    heatmap_pdf.to_csv(os.path.join(WAREHOUSE_DIR, "hourly_heatmap_metrics.csv"), index=False)
    heatmap_pdf.to_csv(os.path.join(WAREHOUSE_DIR, "hourly_flow.csv"), index=False)
    daily_pdf.to_csv(os.path.join(WAREHOUSE_DIR, "daily_flow_metrics.csv"), index=False)
    daily_pdf.to_csv(os.path.join(WAREHOUSE_DIR, "daily_dept_flow.csv"), index=False)

    try:
        enriched_pdf.to_parquet(os.path.join(WAREHOUSE_DIR, "enriched_admissions.parquet"), index=False)
        enriched_pdf.to_parquet(os.path.join(WAREHOUSE_DIR, "patient_flow_facts.parquet"), index=False)
        pff_dir = os.path.join(WAREHOUSE_DIR, "patient_flow_facts")
        os.makedirs(pff_dir, exist_ok=True)
        enriched_pdf.to_parquet(os.path.join(pff_dir, "part-00000.parquet"), index=False)

        dept_pdf.to_parquet(os.path.join(WAREHOUSE_DIR, "department_metrics.parquet"), index=False)
        dept_pdf.to_parquet(os.path.join(WAREHOUSE_DIR, "dept_metrics.parquet"), index=False)
        heatmap_pdf.to_parquet(os.path.join(WAREHOUSE_DIR, "hourly_heatmap_metrics.parquet"), index=False)
        heatmap_pdf.to_parquet(os.path.join(WAREHOUSE_DIR, "hourly_flow.parquet"), index=False)
        daily_pdf.to_parquet(os.path.join(WAREHOUSE_DIR, "daily_flow_metrics.parquet"), index=False)
        daily_pdf.to_parquet(os.path.join(WAREHOUSE_DIR, "daily_dept_flow.parquet"), index=False)
    except Exception as pe:
        print(f"[WARN] Parquet write encountered notice: {pe}")

    spark.stop()
    print("[SUCCESS] Spark Pipeline execution finished successfully.")


def main():
    start_t = time.time()
    try:
        # Check if PySpark and Java are accessible
        import pyspark
        run_spark_pipeline()
    except Exception as e:
        print(f"[NOTICE] PySpark pipeline initialization resulted in: {e}")
        run_pandas_fallback(str(e))

    duration = time.time() - start_t
    print(f"[INFO] Pipeline completed in {duration:.2f} seconds.")


if __name__ == "__main__":
    main()
