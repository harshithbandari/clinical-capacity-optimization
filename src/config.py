"""Configuration for the clinical operations capacity model."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
DATA, OUT, SQL = ROOT/"data", ROOT/"outputs", ROOT/"sql"
for p in (DATA, OUT): p.mkdir(exist_ok=True)
DB = DATA/"clinic_ops.db"

SEED = 20260818
WEEKS = 78                 # 18 months of weekly operations
HOLDOUT_WEEKS = 13

CLINICS = [
    ("CLN-01", "Riverside Main Campus", "Hospital outpatient"),
    ("CLN-02", "Northgate Health Center", "Community clinic"),
    ("CLN-03", "Lakeview Family Practice", "Primary care"),
    ("CLN-04", "Harbor Specialty Pavilion", "Specialty"),
]

# specialty, weekly referral demand, providers, slots/provider/wk, appt minutes,
# no-show base rate, seasonal amplitude, urgency share
SPECIALTIES = [
    ("Cardiology",        340,  9, 46,  30, 0.114, 0.10, 0.22),
    ("Orthopedics",       400, 11, 42,  35, 0.131, 0.16, 0.18),
    ("Dermatology",       240,  6, 58,  20, 0.163, 0.21, 0.06),
    ("Gastroenterology",  190,  6, 40,  35, 0.128, 0.08, 0.14),
    ("Neurology",         148,  5, 34,  45, 0.147, 0.07, 0.19),
    ("Endocrinology",     105,  4, 38,  35, 0.152, 0.09, 0.11),
    ("Behavioral health", 250,  7, 44,  50, 0.238, 0.12, 0.15),
    ("Primary care",     1150, 22, 70,  20, 0.121, 0.14, 0.09),
]

DEMAND_SCALE = 0.80    # calibrates system-wide utilisation to a realistic ~0.75 mean
OVERBOOK_RECOVERY = 0.55      # share of a no-show slot recovered by overbooking
CANCEL_BASE = 0.086           # cancellations released far enough ahead to refill
CANCEL_REFILL = 0.72

# scenario levers
CAPACITY_STEPS = [0.00, 0.05, 0.10, 0.15, 0.20]
TARGET_WAIT_DAYS = 14         # health-system access standard used for the gap analysis
