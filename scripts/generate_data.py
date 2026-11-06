"""
Hospital Patient-Flow Synthetic Data Generator
Generates realistic de-identified patient admission and discharge logs.
"""

import csv
import os
import random
from datetime import datetime, timedelta

# Set deterministic seed for reproducibility
random.seed(42)

DEPARTMENTS = [
    "Emergency",
    "ICU",
    "Cardiology",
    "General Medicine",
    "Orthopedics",
    "Pediatrics",
]

# Department configurations:
# (weight, min_los_hours, max_los_hours, avg_los_hours, acuity_weights_1_to_5, age_range)
DEPT_CONFIGS = {
    "Emergency": {
        "weight": 0.32,
        "min_los": 1.5,
        "max_los": 24.0,
        "mean_los": 7.0,
        "std_los": 4.0,
        "acuity_weights": [0.10, 0.25, 0.35, 0.20, 0.10],  # 1=Critical to 5=Non-urgent
        "age_range": (18, 90),
    },
    "ICU": {
        "weight": 0.12,
        "min_los": 24.0,
        "max_los": 360.0,
        "mean_los": 96.0,
        "std_los": 48.0,
        "acuity_weights": [0.45, 0.40, 0.12, 0.03, 0.00],
        "age_range": (20, 92),
    },
    "Cardiology": {
        "weight": 0.16,
        "min_los": 18.0,
        "max_los": 168.0,
        "mean_los": 64.0,
        "std_los": 28.0,
        "acuity_weights": [0.20, 0.35, 0.30, 0.12, 0.03],
        "age_range": (40, 94),
    },
    "General Medicine": {
        "weight": 0.20,
        "min_los": 24.0,
        "max_los": 192.0,
        "mean_los": 72.0,
        "std_los": 36.0,
        "acuity_weights": [0.08, 0.22, 0.40, 0.22, 0.08],
        "age_range": (18, 95),
    },
    "Orthopedics": {
        "weight": 0.11,
        "min_los": 20.0,
        "max_los": 120.0,
        "mean_los": 52.0,
        "std_los": 20.0,
        "acuity_weights": [0.05, 0.15, 0.50, 0.25, 0.05],
        "age_range": (16, 88),
    },
    "Pediatrics": {
        "weight": 0.09,
        "min_los": 12.0,
        "max_los": 96.0,
        "mean_los": 38.0,
        "std_los": 18.0,
        "acuity_weights": [0.10, 0.25, 0.45, 0.15, 0.05],
        "age_range": (0, 17),
    },
}

DISPOSITIONS = ["Home", "Transfer", "Deceased"]


def generate_records(num_records: int = 3500, start_days_ago: int = 90):
    records = []
    end_time = datetime.now()
    start_time = end_time - timedelta(days=start_days_ago)
    total_seconds_span = int((end_time - start_time).total_seconds())

    # Patient pool for recurring patients
    num_unique_patients = int(num_records * 0.72)
    patient_ids = [f"PAT-{10000 + i}" for i in range(num_unique_patients)]

    dept_names = list(DEPT_CONFIGS.keys())
    dept_weights = [DEPT_CONFIGS[d]["weight"] for d in dept_names]

    for idx in range(1, num_records + 1):
        admission_id = f"ADM-{100000 + idx}"
        patient_id = random.choice(patient_ids)

        dept = random.choices(dept_names, weights=dept_weights, k=1)[0]
        cfg = DEPT_CONFIGS[dept]

        # Random admission time (simulate diurnal peaks: higher probability during daytime 08:00 - 20:00)
        random_offset_seconds = random.randint(0, total_seconds_span)
        adm_dt = start_time + timedelta(seconds=random_offset_seconds)

        # Diurnal adjustment: shift 25% of night arrivals toward daytime
        if adm_dt.hour in [1, 2, 3, 4, 5] and random.random() < 0.45:
            adm_dt = adm_dt.replace(hour=random.choice([9, 10, 11, 14, 15, 16, 17, 18]))

        # Acuity score (1 to 5)
        acuity_score = random.choices([1, 2, 3, 4, 5], weights=cfg["acuity_weights"], k=1)[0]

        # Length of Stay calculation (Gaussian with truncation)
        raw_los = random.gauss(cfg["mean_los"], cfg["std_los"])
        los_hours = max(cfg["min_los"], min(cfg["max_los"], raw_los))

        # Acuity impact on LOS: higher acuity (1-2) slightly extends stay
        if acuity_score == 1:
            los_hours *= random.uniform(1.15, 1.45)
        elif acuity_score == 2:
            los_hours *= random.uniform(1.05, 1.25)
        elif acuity_score == 5:
            los_hours *= random.uniform(0.75, 0.95)

        los_hours = round(max(cfg["min_los"], los_hours), 2)
        dis_dt = adm_dt + timedelta(hours=los_hours)

        # Patient age
        min_age, max_age = cfg["age_range"]
        age = random.randint(min_age, max_age)

        # Discharge disposition: dependent on department and acuity
        if dept == "ICU":
            if acuity_score == 1:
                disp = random.choices(DISPOSITIONS, weights=[0.60, 0.25, 0.15], k=1)[0]
            else:
                disp = random.choices(DISPOSITIONS, weights=[0.78, 0.17, 0.05], k=1)[0]
        elif dept == "Emergency":
            if acuity_score == 1:
                disp = random.choices(DISPOSITIONS, weights=[0.50, 0.44, 0.06], k=1)[0]
            else:
                disp = random.choices(DISPOSITIONS, weights=[0.90, 0.09, 0.01], k=1)[0]
        else:
            if acuity_score == 1:
                disp = random.choices(DISPOSITIONS, weights=[0.75, 0.20, 0.05], k=1)[0]
            else:
                disp = random.choices(DISPOSITIONS, weights=[0.93, 0.06, 0.01], k=1)[0]

        records.append({
            "admission_id": admission_id,
            "patient_id": patient_id,
            "department": dept,
            "admission_timestamp": adm_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "discharge_timestamp": dis_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "age": age,
            "acuity_score": acuity_score,
            "discharge_disposition": disp,
        })

    # Sort chronological by admission_timestamp
    records.sort(key=lambda x: x["admission_timestamp"])
    return records


def main():
    output_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "hospital_admission_logs.csv")

    record_count = 3500
    print(f"Generating {record_count} patient admission records...")
    records = generate_records(record_count)

    fields = [
        "admission_id",
        "patient_id",
        "department",
        "admission_timestamp",
        "discharge_timestamp",
        "age",
        "acuity_score",
        "discharge_disposition",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)

    print(f"Successfully generated {len(records)} records saved to: {output_path}")


if __name__ == "__main__":
    main()
