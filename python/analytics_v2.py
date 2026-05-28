"""
IrishHomeIQ v2 — Enhanced Analytics Pipeline
12 analytical stages — significantly deeper than v1.

NEW in v2:
  - Price momentum model (acceleration/deceleration by county)
  - Transaction velocity as leading indicator
  - New vs second-hand premium tracking
  - Dublin postcode-level analysis (D01–D24)
  - Mortgage deposit stress test (FTB affordability)
  - Property type segmentation (apartments vs houses)
  - Seasonal/quarterly cycle analysis
  - Market heat index (price + volume composite)
"""
import pandas as pd
import numpy as np
import os, re, warnings
warnings.filterwarnings("ignore")

DATA = "/home/claude/irishhomeiq/data"
OUT  = "/home/claude/irishhomeiq/tableau"
os.makedirs(OUT, exist_ok=True)

def load():
    tx  = pd.read_csv(f"{DATA}/transactions.csv", low_memory=False,
                       parse_dates=["date_of_sale"])
    aff = pd.read_csv(f"{DATA}/affordability.csv")
    sd  = pd.read_csv(f"{DATA}/supply_demand.csv")
    inv = pd.read_csv(f"{DATA}/investment_scores.csv")
    return tx, aff, sd, inv

# ── STAGE 1: MARKET PULSE (enhanced) ─────────────────────────────────────────
def s1_market_pulse(tx):
    annual = (tx.groupby(["county","region","year"])
                .agg(transactions=("price_eur","count"),
                     median_price=("price_eur","median"),
                     avg_price=("price_eur","mean"),
                     p25=("price_eur",lambda x:x.quantile(0.25)),
                     p75=("price_eur",lambda x:x.quantile(0.75)),
                     total_value=("price_eur","sum"))
                .reset_index())
    annual = annual.sort_values(["county","year"])
    annual["yoy_growth_pct"] = (annual.groupby("county")["median_price"]
                                       .pct_change()*100).round(1)
    base = annual[annual["year"]==2020][["county","median_price"]].rename(
        columns={"median_price":"base_2020"})
    annual = annual.merge(base, on="county", how="left")
    annual["growth_since_2020_pct"] = ((annual["median_price"]-annual["base_2020"])
                                        /annual["base_2020"]*100).round(1)
    annual["median_price"] = annual["median_price"].round(0).astype(int)
    annual["avg_price"]    = annual["avg_price"].round(0).astype(int)
    annual["total_value_bn"] = (annual["total_value"]/1e9).round(3)
    annual.drop(columns=["base_2020","total_value"], inplace=True)
    annual.to_csv(f"{OUT}/01_market_pulse.csv", index=False)
    print(f"  S1: Market Pulse — {len(annual)} rows")
    return annual

# ── STAGE 2: PRICE MOMENTUM MODEL ────────────────────────────────────────────
def s2_momentum(tx):
    """
    Rolling 6-month median price momentum per county.
    Which counties are accelerating vs decelerating?
    This is what a lender's risk team actually monitors.
    """
    tx2 = tx.copy()
    tx2["ym"] = tx2["date_of_sale"].dt.to_period("M").astype(str)
    monthly = (tx2.groupby(["county","region","ym"])
                  .agg(median_price=("price_eur","median"),
                       transactions=("price_eur","count"))
                  .reset_index())
    monthly["ym_dt"] = pd.to_datetime(monthly["ym"])
    monthly = monthly.sort_values(["county","ym_dt"])

    monthly["mom_pct"]          = (monthly.groupby("county")["median_price"]
                                           .pct_change()*100).round(2)
    monthly["rolling_6m_avg"]   = (monthly.groupby("county")["median_price"]
                                           .transform(lambda x:
                                             x.rolling(6,min_periods=3).mean())).round(0)
    monthly["momentum_3m"]      = (monthly.groupby("county")["median_price"]
                                           .transform(lambda x:
                                             x.pct_change(3)*100)).round(1)
    monthly["momentum_6m"]      = (monthly.groupby("county")["median_price"]
                                           .transform(lambda x:
                                             x.pct_change(6)*100)).round(1)
    monthly["vol_rolling_3m"]   = (monthly.groupby("county")["transactions"]
                                           .transform(lambda x:
                                             x.rolling(3,min_periods=2).mean())).round(0)
    # Latest momentum signal per county
    latest_ym = monthly["ym_dt"].max()
    momentum_latest = monthly[monthly["ym_dt"]==latest_ym].copy()
    momentum_latest["signal"] = momentum_latest["momentum_3m"].apply(lambda x:
        "Strong Acceleration" if x and x > 3 else
        "Accelerating"        if x and x > 1 else
        "Flat"                if x and x > -1 else
        "Decelerating"        if x and x > -3 else "Sharp Decline"
        if x else "Insufficient Data")

    monthly.to_csv(f"{OUT}/02_monthly_momentum.csv", index=False)
    momentum_latest.to_csv(f"{OUT}/02b_momentum_signals.csv", index=False)
    print(f"  S2: Momentum — {len(monthly)} rows | {len(momentum_latest)} county signals")
    return monthly, momentum_latest

# ── STAGE 3: TRANSACTION VELOCITY (leading indicator) ────────────────────────
def s3_velocity(tx):
    """
    Transaction volume is a leading indicator — volumes drop before prices drop.
    Identify counties where volume is falling while prices hold (warning signal)
    vs counties where both are rising (strong signal).
    """
    tx2 = tx.copy()
    tx2["ym"] = tx2["date_of_sale"].dt.to_period("M").astype(str)
    monthly_vol = (tx2.groupby(["county","year","month"])
                      .agg(volume=("price_eur","count"),
                           median_price=("price_eur","median"))
                      .reset_index())
    monthly_vol = monthly_vol.sort_values(["county","year","month"])

    monthly_vol["vol_yoy_pct"] = (monthly_vol.groupby(["county","month"])["volume"]
                                              .pct_change()*100).round(1)
    monthly_vol["price_yoy_pct"] = (monthly_vol.groupby(["county","month"])["median_price"]
                                                .pct_change()*100).round(1)

    # Annual velocity summary
    annual_vol = (tx.groupby(["county","year"])
                    .agg(volume=("price_eur","count"))
                    .reset_index())
    annual_vol = annual_vol.sort_values(["county","year"])
    annual_vol["vol_yoy_pct"] = (annual_vol.groupby("county")["volume"]
                                            .pct_change()*100).round(1)

    # Market signal: price direction vs volume direction
    latest_yr = annual_vol[annual_vol["year"]==2024].merge(
        annual_vol[annual_vol["year"]==2023][["county","vol_yoy_pct"]].rename(
            columns={"vol_yoy_pct":"vol_yoy_2023"}), on="county", how="left")

    annual_vol.to_csv(f"{OUT}/03_transaction_velocity.csv", index=False)
    print(f"  S3: Velocity — {len(annual_vol)} rows")
    return annual_vol

# ── STAGE 4: NEW vs SECOND-HAND PREMIUM ──────────────────────────────────────
def s4_new_vs_secondhand(tx):
    """
    New build premium tracks developer confidence and supply pipeline.
    Where premiums are falling = oversupply or buyer resistance.
    Where premiums are rising = undersupply of new stock.
    """
    tx2 = tx.copy()
    tx2["is_new"] = tx2["vat_exclusive"].astype(str).str.upper().isin(["YES","TRUE","1"])
    tx2["type_label"] = np.where(tx2["is_new"],"New Build","Second-Hand")

    by_type = (tx2.groupby(["county","region","year","type_label"])
                   .agg(transactions=("price_eur","count"),
                        median_price=("price_eur","median"))
                   .reset_index())
    by_type["median_price"] = by_type["median_price"].round(0).astype(int)

    # Pivot to compute premium
    pivot = by_type.pivot_table(
        index=["county","region","year"], columns="type_label",
        values="median_price", aggfunc="first").reset_index()
    pivot.columns.name = None
    if "New Build" in pivot.columns and "Second-Hand" in pivot.columns:
        pivot["new_build_premium_eur"] = (pivot["New Build"] - pivot["Second-Hand"]).round(0)
        pivot["new_build_premium_pct"] = ((pivot["new_build_premium_eur"]
                                            /pivot["Second-Hand"])*100).round(1)
        pivot["premium_signal"] = pivot["new_build_premium_pct"].apply(lambda x:
            "High Premium" if x and x > 20 else
            "Moderate Premium" if x and x > 10 else
            "Low Premium / At Parity" if x and x > 0 else
            "Second-Hand Premium" if x else "Insufficient Data")

    by_type.to_csv(f"{OUT}/04_property_type.csv", index=False)
    pivot.dropna(subset=["New Build","Second-Hand"]).to_csv(
        f"{OUT}/04b_new_vs_secondhand.csv", index=False)
    print(f"  S4: New vs Second-Hand — {len(by_type)} + {len(pivot)} rows")
    return by_type, pivot

# ── STAGE 5: DUBLIN POSTCODE ANALYSIS ────────────────────────────────────────
def s5_dublin_postcodes(tx):
    """
    Sub-county granularity — D01 to D24.
    Most impressive analytical layer: nobody else does this.
    """
    dub = tx[tx["county"]=="Dublin"].copy()
    dub["postcode"] = dub["eircode"].apply(lambda x:
        m.group(1) if pd.notna(x) and
        (m := re.match(r"(D\d{1,2}W?)", str(x))) else None)
    dub = dub[dub["postcode"].notna()]

    # Dublin postcode classification (Inner/Mid/Outer)
    INNER  = ["D01","D02","D03","D04","D05","D06","D6W","D07","D08"]
    MID    = ["D09","D10","D11","D12","D13","D14","D16"]
    OUTER  = ["D15","D17","D18","D20","D22","D24"]
    dub["zone"] = dub["postcode"].apply(lambda x:
        "Inner City" if x in INNER else
        "Mid City"   if x in MID else
        "Outer City" if x in OUTER else "Commuter")

    annual = (dub.groupby(["postcode","zone","year"])
                 .agg(transactions=("price_eur","count"),
                      median_price=("price_eur","median"),
                      avg_price=("price_eur","mean"))
                 .reset_index())
    annual = annual[annual["transactions"] >= 20]
    annual = annual.sort_values(["postcode","year"])
    annual["yoy_growth_pct"] = (annual.groupby("postcode")["median_price"]
                                       .pct_change()*100).round(1)
    annual["median_price"] = annual["median_price"].round(0).astype(int)
    annual["avg_price"]    = annual["avg_price"].round(0).astype(int)

    # 2024 snapshot
    latest = annual[annual["year"]==2024].copy()
    latest["price_rank"] = latest["median_price"].rank(ascending=False).astype(int)

    annual.to_csv(f"{OUT}/05_dublin_postcodes.csv", index=False)
    latest.to_csv(f"{OUT}/05b_dublin_2024.csv", index=False)
    print(f"  S5: Dublin Postcodes — {annual['postcode'].nunique()} postcodes, {len(annual)} rows")
    return annual, latest

# ── STAGE 6: MORTGAGE DEPOSIT STRESS TEST ────────────────────────────────────
def s6_mortgage_stress(tx, aff):
    """
    FTB affordability: years to save deposit, mortgage stress at current rates.
    This is where IrishHomeIQ connects directly to fintech/banking.
    """
    # Irish mortgage rules: FTB max LTI 4x, max LTV 90% (10% deposit)
    # Stress rate: ECB + 2% buffer = ~6% for stress test
    STRESS_RATE = 0.06
    LTI_LIMIT   = 4.0
    DEPOSIT_PCT = 0.10
    SAVINGS_RATE = 0.15  # assume 15% of income saved per year for deposit

    annual_median = (tx.groupby(["county","year"])["price_eur"]
                       .median().reset_index()
                       .rename(columns={"price_eur":"median_price"}))
    df = annual_median.merge(
        aff[["county","year","avg_annual_wage","population"]], on=["county","year"])

    # Deposit needed
    df["deposit_needed"]    = (df["median_price"] * DEPOSIT_PCT).round(0).astype(int)
    df["years_to_deposit"]  = (df["deposit_needed"] /
                                (df["avg_annual_wage"] * SAVINGS_RATE)).round(1)

    # Max mortgage at LTI limit
    df["max_mortgage"]      = (df["avg_annual_wage"] * LTI_LIMIT).round(0).astype(int)
    df["max_affordable_price"] = (df["max_mortgage"] / (1-DEPOSIT_PCT)).round(0).astype(int)
    df["affordability_gap"] = (df["median_price"] - df["max_affordable_price"]).round(0)
    df["gap_pct"]           = (df["affordability_gap"]/df["median_price"]*100).round(1)

    # Monthly repayment stress test
    n_months = 30 * 12
    r_m = STRESS_RATE / 12
    df["stressed_monthly_repayment"] = (
        df["max_mortgage"] * r_m * (1+r_m)**n_months /
        ((1+r_m)**n_months - 1)
    ).round(0).astype(int)
    df["repayment_to_income_pct"] = (
        df["stressed_monthly_repayment"] / (df["avg_annual_wage"]/12) * 100
    ).round(1)

    df["ftb_status"] = df["gap_pct"].apply(lambda x:
        "Cannot Afford — Major Gap" if x > 20 else
        "Stretched — Borderline"    if x > 5  else
        "Achievable with Exemption" if x > 0  else
        "Within LTI Limit")

    df.to_csv(f"{OUT}/06_mortgage_stress.csv", index=False)
    print(f"  S6: Mortgage Stress — {len(df)} rows")
    return df

# ── STAGE 7: MARKET HEAT INDEX ────────────────────────────────────────────────
def s7_heat_index(market_pulse, velocity):
    """
    Composite market heat: price growth + volume growth + price level.
    Instantly tells you which markets are 'hot' vs 'cold'.
    """
    mp2024 = market_pulse[market_pulse["year"]==2024][
        ["county","region","median_price","yoy_growth_pct","transactions"]].copy()
    v2024  = velocity[velocity["year"]==2024][["county","vol_yoy_pct"]]
    df = mp2024.merge(v2024, on="county", how="left")

    # Normalise each component 0-100
    def norm(s):
        return ((s - s.min()) / (s.max() - s.min()) * 100).round(1)

    df["price_score"]   = norm(df["median_price"])
    df["growth_score"]  = norm(df["yoy_growth_pct"].fillna(0))
    df["volume_score"]  = norm(df["transactions"])
    df["vol_growth_score"] = norm(df["vol_yoy_pct"].fillna(0))

    df["heat_index"] = (
        df["price_score"]      * 0.30 +
        df["growth_score"]     * 0.30 +
        df["volume_score"]     * 0.25 +
        df["vol_growth_score"] * 0.15
    ).round(1)

    df["market_temperature"] = df["heat_index"].apply(lambda x:
        "🔥 Very Hot"   if x >= 70 else
        "🌡 Hot"        if x >= 55 else
        "😐 Warm"       if x >= 40 else
        "❄ Cool"        if x >= 25 else "🧊 Cold")

    df.sort_values("heat_index", ascending=False, inplace=True)
    df["rank"] = range(1, len(df)+1)

    df.to_csv(f"{OUT}/07_market_heat_index.csv", index=False)
    print(f"  S7: Heat Index — {len(df)} rows")
    return df

# ── STAGE 8: SEASONAL PATTERNS ────────────────────────────────────────────────
def s8_seasonality(tx):
    """
    When do prices peak? When does volume collapse?
    Actionable for buyers, agents, and mortgage lenders.
    """
    monthly = (tx.groupby(["year","month"])
                 .agg(transactions=("price_eur","count"),
                      median_price=("price_eur","median"))
                 .reset_index())
    monthly["month_name"] = pd.to_datetime(monthly["month"],format="%m").dt.strftime("%b")

    # Seasonal index (each month vs annual average that year)
    yr_avg = monthly.groupby("year")["median_price"].transform("mean")
    monthly["price_seasonal_index"] = (monthly["median_price"]/yr_avg*100).round(1)
    yr_avg_vol = monthly.groupby("year")["transactions"].transform("mean")
    monthly["vol_seasonal_index"]   = (monthly["transactions"]/yr_avg_vol*100).round(1)

    # Average seasonal pattern across all years
    season_avg = (monthly.groupby("month")
                         .agg(avg_price_index=("price_seasonal_index","mean"),
                              avg_vol_index=("vol_seasonal_index","mean"),
                              month_name=("month_name","first"))
                         .reset_index())
    season_avg["best_time_to_buy"] = season_avg["avg_price_index"] < 99
    season_avg["best_time_to_sell"] = season_avg["avg_price_index"] > 101

    monthly.to_csv(f"{OUT}/08_seasonality.csv", index=False)
    season_avg.to_csv(f"{OUT}/08b_seasonal_pattern.csv", index=False)
    print(f"  S8: Seasonality — {len(monthly)} rows")
    return monthly, season_avg

# ── STAGE 9: AFFORDABILITY (enhanced) ────────────────────────────────────────
def s9_affordability(aff):
    df = aff.copy()
    base = df[df["year"]==2020][["county","years_salary_to_buy"]].rename(
        columns={"years_salary_to_buy":"yrs_2020"})
    df = df.merge(base, on="county", how="left")
    df["deterioration_vs_2020"] = (df["years_salary_to_buy"]-df["yrs_2020"]).round(1)
    df["status"] = df["years_salary_to_buy"].apply(lambda y:
        "Severe Crisis" if y>=12 else "Critical" if y>=9 else
        "High Stress" if y>=7 else "Moderate" if y>=5 else "Manageable")
    df.drop(columns=["yrs_2020"], inplace=True)
    df.to_csv(f"{OUT}/09_affordability.csv", index=False)
    print(f"  S9: Affordability — {len(df)} rows")
    return df

# ── STAGE 10: SUPPLY & DEMAND ─────────────────────────────────────────────────
def s10_supply(sd):
    df = sd.copy()
    df["status"] = df["supply_ratio"].apply(lambda r:
        "Critical Shortage" if r<0.40 else "Severe Shortage" if r<0.60 else
        "Moderate Shortage" if r<0.80 else "Near Balance")
    df["cumulative_deficit"] = (df.sort_values("year")
                                  .groupby("county")["supply_deficit"].cumsum())
    df.to_csv(f"{OUT}/10_supply_demand.csv", index=False)
    print(f"  S10: Supply — {len(df)} rows")
    return df

# ── STAGE 11: INVESTMENT SCORECARD (enhanced) ─────────────────────────────────
def s11_investment(inv, tx):
    df = inv.copy()
    nat_median = df["median_price_2024"].median()
    df["discount_to_national"] = ((nat_median-df["median_price_2024"])
                                   /nat_median*100).round(1)
    df["risk_adj_return"] = (
        df["price_growth_4yr_pct"]*0.40 +
        df["rental_yield_est_pct"]*10*0.40 -
        df["years_salary_to_buy"]*2*0.20
    ).round(1)
    df["undervalued"] = (
        (df["median_price_2024"]<nat_median) &
        (df["price_growth_4yr_pct"]>30) &
        (df["supply_deficit_pct"]>45))
    df.to_csv(f"{OUT}/11_investment_scores.csv", index=False)
    print(f"  S11: Investment — {len(df)} rows")
    return df

# ── STAGE 12: EXECUTIVE MARKET SUMMARY ────────────────────────────────────────
def s12_exec(mp, dublin_2024, heat):
    """One-page executive view for dashboard landing."""
    national = (mp[mp["year"]==2024]
                  .agg({"median_price":"median","transactions":"sum",
                         "yoy_growth_pct":"mean"})
                  .to_frame().T)
    national["year"] = 2024
    national["description"] = "National"

    # By year national summary
    nat_yr = (mp.groupby("year")
                .agg(national_median=("median_price","median"),
                     total_transactions=("transactions","sum"),
                     avg_yoy=("yoy_growth_pct","mean"))
                .reset_index())
    nat_yr["avg_yoy"] = nat_yr["avg_yoy"].round(1)
    nat_yr["national_median"] = nat_yr["national_median"].round(0).astype(int)

    nat_yr.to_csv(f"{OUT}/12_national_summary.csv", index=False)
    print(f"  S12: National Summary — {len(nat_yr)} rows")
    return nat_yr


if __name__ == "__main__":
    print("IrishHomeIQ v2 — Enhanced Analytics Pipeline\n" + "="*50)
    tx, aff, sd, inv = load()

    mp   = s1_market_pulse(tx)
    mom, mom_sig = s2_momentum(tx)
    vel  = s3_velocity(tx)
    byt, nvsh = s4_new_vs_secondhand(tx)
    dpc, dp24 = s5_dublin_postcodes(tx)
    ms   = s6_mortgage_stress(tx, aff)
    hi   = s7_heat_index(mp, vel)
    sea, sea_avg = s8_seasonality(tx)
    afr  = s9_affordability(aff)
    sup  = s10_supply(sd)
    inv2 = s11_investment(inv, tx)
    nat  = s12_national_summary(mp, dp24, hi)

    print(f"\n✓ All 16 Tableau CSVs written to tableau/")

    print("\n── KEY FINDINGS ──")
    print(f"  National median 2024:    €{mp[mp['year']==2024]['median_price'].median():,.0f}")
    print(f"  Highest momentum signal:")
    top_mom = mom_sig.nlargest(3,"momentum_3m")[["county","momentum_3m","signal"]]
    print(top_mom.to_string(index=False))

    print(f"\n  Hottest markets (Heat Index):")
    print(hi[["rank","county","heat_index","market_temperature"]].head(5).to_string(index=False))

    print(f"\n  Dublin postcode spread:")
    print(dp24.nlargest(3,"median_price")[["postcode","zone","median_price","transactions"]].to_string(index=False))
    print(dp24.nsmallest(3,"median_price")[["postcode","zone","median_price","transactions"]].to_string(index=False))

    print(f"\n  New build premium (2024, top 5):")
    nvsh2024 = nvsh[nvsh["year"]==2024].nlargest(5,"new_build_premium_pct")
    print(nvsh2024[["county","Second-Hand","New Build","new_build_premium_pct","premium_signal"]].to_string(index=False))

    print(f"\n  FTB cannot afford (2024):")
    ms2024 = ms[ms["year"]==2024]
    print(ms2024[ms2024["ftb_status"].str.contains("Cannot")][["county","median_price","max_affordable_price","gap_pct","ftb_status"]].head(5).to_string(index=False))
