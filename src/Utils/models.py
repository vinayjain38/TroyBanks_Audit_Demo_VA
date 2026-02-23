# models.py
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from src.Utils.database import Base

# ==========================================
# 1. TARIFF RATES (Rules from Schedule 100, 130, etc.)
# ==========================================
class TariffRate(Base):
    __tablename__ = "tariff_rates"

    id = Column(Integer, primary_key=True, index=True)
    schedule_code = Column(String, index=True, nullable=False) # e.g. "100", "130"
    
    category = Column(String, nullable=True)
    sub_category = Column(String, nullable=True)
    item = Column(String, nullable=False)
    condition_tier = Column(String, nullable=True)
    rate_description = Column(String, nullable=True) # The raw text, e.g. "1.298¢ / kWh"
    rate = Column(String, nullable=True) 
    description = Column(String, nullable=True)
    
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

# ==========================================
# 2. RIDER RATES 
# ==========================================
class RiderRate(Base):
    __tablename__ = "rider_rates"

    id = Column(Integer, primary_key=True, index=True)

    # The Row Header (e.g., "SCHEDULE 100", "TRAFFIC", "OUTDOOR LIGHTING")
    rate_schedule = Column(String, index=True, nullable=True) 

    # The Columns (Riders) - Stored as String to handle '$', '/', and text notes
    t_cm = Column(String, nullable=True)
    b_cm = Column(String, nullable=True)
    bw_cm = Column(String, nullable=True)
    gv_cm = Column(String, nullable=True)
    us2_cm = Column(String, nullable=True)
    us3_cm = Column(String, nullable=True)
    us4_cm = Column(String, nullable=True)
    rps_cm = Column(String, nullable=True)
    ce_cm = Column(String, nullable=True)
    rbb_cm = Column(String, nullable=True)
    e_cm = Column(String, nullable=True)

    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

# ==========================================
# 3. USAGE RECORDS (The Input Data / Audit File)
# ==========================================
class UsageBill(Base):
    __tablename__ = "usage_bill"

    id = Column(Integer, primary_key=True, index=True)

    # Basic Info
    year = Column(String, nullable=True)
    month = Column(String, nullable=True)
    
    # Financials (Raw Strings to hold '$')
    subtotal_raw = Column(String, nullable=True)        
    total_charges_raw = Column(String, nullable=True)   
    
    # Dates
    bill_from_raw = Column(String, nullable=True)       
    bill_to_raw = Column(String, nullable=True)         
    billing_days = Column(String, nullable=True)
    
    # Billing Meta
    billed_rate = Column(String, nullable=True)         
    bill_summary = Column(String, nullable=True)

    # Usage Stats
    demand = Column(String, nullable=True)
    demand_charges = Column(String, nullable=True)
    demand_ess = Column(String, nullable=True)
    total_consumption = Column(String, nullable=True)
    historical_usage = Column(String, nullable=True)    
    rkva = Column(String, nullable=True)

    # Energy Breakdown
    energy_charges = Column(String, nullable=True)
    energy_dis = Column(String, nullable=True)
    energy_ess = Column(String, nullable=True)
    fuel_charges = Column(String, nullable=True)
    fuel_chg_abbr = Column(String, nullable=True)       
    distribution_demand = Column(String, nullable=True)
    distribution_demand_sec = Column(String, nullable=True)

    # Customer Charges
    basic_cust_charges = Column(String, nullable=True)  
    basic_cust_chg_abbr = Column(String, nullable=True) 

    # Peak / Off-Peak
    off_peak_energy_ess = Column(String, nullable=True)
    off_peak_usage = Column(String, nullable=True)
    on_peak_energy_ess = Column(String, nullable=True)
    on_peak_usage = Column(String, nullable=True)

    # Rider Usage Columns (Specific to the Usage File)
    rider_b_kw = Column(String, nullable=True)
    rider_b_kwh = Column(String, nullable=True)
    rider_bw_kw = Column(String, nullable=True)
    rider_bw_kwh = Column(String, nullable=True)
    rider_ccr = Column(String, nullable=True)
    rider_ce_kw = Column(String, nullable=True)
    rider_ce_kwh = Column(String, nullable=True)
    rider_dist_kw = Column(String, nullable=True)
    rider_dist_kwh = Column(String, nullable=True)
    rider_e_kw = Column(String, nullable=True)
    rider_e_kwh = Column(String, nullable=True)
    rider_gen_kw = Column(String, nullable=True)
    rider_gen_kwh = Column(String, nullable=True)
    rider_gt_kw = Column(String, nullable=True)
    rider_gv_kw = Column(String, nullable=True)
    rider_gv_kwh = Column(String, nullable=True)
    rider_osw_kw = Column(String, nullable=True)
    rider_osw_kwh = Column(String, nullable=True)
    rider_pipp = Column(String, nullable=True)
    rider_ppa = Column(String, nullable=True)
    rider_r_kw = Column(String, nullable=True)
    rider_r_kwh = Column(String, nullable=True)
    rider_r_kw_alt = Column(String, nullable=True)
    rider_rbb_kw = Column(String, nullable=True)
    rider_rbb_kwh = Column(String, nullable=True)
    rider_rggi = Column(String, nullable=True)
    rider_rps = Column(String, nullable=True)
    rider_s_kw = Column(String, nullable=True)
    rider_s_kwh = Column(String, nullable=True)
    rider_smr_kw = Column(String, nullable=True)
    rider_smr_kwh = Column(String, nullable=True)
    rider_sna_kw = Column(String, nullable=True)
    rider_sna_kwh = Column(String, nullable=True)
    rider_u1_kw = Column(String, nullable=True)
    rider_u1_kwh = Column(String, nullable=True)
    rider_u2_kw = Column(String, nullable=True)
    rider_u2_kwh = Column(String, nullable=True)
    rider_u2_kw_alt = Column(String, nullable=True)
    rider_us2_kw = Column(String, nullable=True)
    rider_us2_kwh = Column(String, nullable=True)
    rider_us3_kw = Column(String, nullable=True)
    rider_us3_kwh = Column(String, nullable=True)
    rider_us4_kw = Column(String, nullable=True)
    rider_us4_kwh = Column(String, nullable=True)
    rider_w_kw = Column(String, nullable=True)
    rider_w_kwh = Column(String, nullable=True)
    rider_w_kw_alt = Column(String, nullable=True)
    rider_gt = Column(String, nullable=True)

    # Misc
    kw_adj_ess_secondary = Column(String, nullable=True)
    transmission_energy = Column(String, nullable=True)
    transmission_demand = Column(String, nullable=True)
    tax_surcharge = Column(String, nullable=True)       
    other_charges_credits = Column(String, nullable=True)
    service_auth_name = Column(String, nullable=True)
    w_misc = Column(String, nullable=True)
    unknown_symbol = Column(String, nullable=True)

    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())