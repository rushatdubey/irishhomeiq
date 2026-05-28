"""
IrishHomeIQ — Full Analytics Pipeline
Generates all Tableau-ready CSVs from transaction data.

Usage:
    python python/analytics.py

Outputs (to tableau/):
    01_market_pulse.csv          — annual price trends + YoY growth per county
    02_dublin_vs_roi.csv         — Dublin vs Rest of Ireland divergence
    03_regional_trends.csv       — Leinster/Munster/Connacht/Ulster trajectories
    04_affordability.csv         — price-to-income, years-to-buy, rent estimates
    05_supply_demand.csv         — completions vs demand vs deficit
    06_investment_scores.csv     — composite scoring + tier ranking
    07_commuter_belt.csv         — Leinster commuter counties deep-dive
    08_monthly_volume.csv        — transaction volume seasonality
    09_price_distribution.csv    — percentile bands for box plots
"""

import pandas as pd
import numpy as np
import os, sys

DATA_DIR   = os.path.join(os.path.dirname(__file__), "../data")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "../tableau")
os.makedirs(OUTPUT_DIR, exist_ok=True)

COMMUTER_BELT = ["Kildare", "Meath", "Wicklow", "Louth", "Westmeath"]

# ── LOAD ───────────────────────────────────────────────────────────────────────
def load_data():
    tx  = pd.read_csv(f"{DATA_DIR}/transactions.csv", parse_dates=["date_of_sale"],
                      dayfirst=True)
    sd  = pd.read_csv(f"{DATA_DIR}/supply_demand.csv")
    aff = pd.read_csv(f"{DATA_DIR}/affordability.csv")
    inv = pd.read_csv(f"{DATA_DIR}/investment_scores.csv")
    
    # Clean price — handles real PPR format (€123,000)
    if tx["price_eur"].dtype == object:
        tx["price_eur"] = (tx["price_eur"]
                           .str.replace("€","").str.replace(",","")
                           .astype(float))
    
    tx = tx[tx["price_eur"] > 10000]   # remove outliers
    tx = tx[tx["price_eur"] < 5000000]
    print(f"  Loaded {len(tx):,} transactions")
    return tx, sd, aff, inv


# ── STAGE 1: MARKET PULSE ─────────────────────────────────────────────────────
def market_pulse(tx):
    annual = (tx.groupby(["county", "region", "year"])
               .agg(
                   transaction_count=("price_eur", "count"),
                   median_price=("price_eur", "median"),
                   avg_price=("price_eur", "mean"),
                   p25_price=("price_eur", lambda x: x.quantile(0.25)),
                   p75_price=("price_eur", lambda x: x.quantile(0.75)),
               )
               .reset_index())
    
    annual["median_price"] = annual["median_price"].round(0).astype(int)
    annual["avg_price"]    = annual["avg_price"].round(0).astype(int)
    annual["p25_price"]    = annual["p25_price"].round(0).astype(int)
    annual["p75_price"]    = annual["p75_price"].round(0).astype(int)
    
    annual = annual.sort_values(["county", "year"])
    annual["prev_median"]    = annual.groupby("county")["median_price"].shift(1)
    annual["yoy_growth_pct"] = ((annual["median_price"] - annual["prev_median"])
                                 / annual["prev_median"] * 100).round(1)
    
    base_prices = annual[annual["year"] == 2020][["county", "median_price"]].rename(
        columns={"median_price": "base_2020"})
    annual = annual.merge(base_prices, on="county", how="left")
    annual["growth_since_2020_pct"] = ((annual["median_price"] - annual["base_2020"])
                                        / annual["base_2020"] * 100).round(1)
    
    annual.drop(columns=["prev_median", "base_2020"], inplace=True)
    annual.to_csv(f"{OUTPUT_DIR}/01_market_pulse.csv", index=False)
    print(f"  Stage 1: Market Pulse — {len(annual)} rows")
    return annual


# ── STAGE 2: DUBLIN VS ROI ────────────────────────────────────────────────────
def dublin_vs_roi(tx):
    tx2 = tx.copy()
    tx2["market"] = tx2["county"].apply(
        lambda c: "Dublin" if c == "Dublin" else "Rest of Ireland")
    
    annual = (tx2.groupby(["year", "market"])
                 .agg(median_price=("price_eur", "median"),
                      transactions=("price_eur", "count"))
                 .reset_index())
    
    pivot = annual.pivot(index="year", columns="market",
                         values=["median_price", "transactions"]).reset_index()
    pivot.columns = ["year", "dublin_median", "roi_median",
                     "dublin_txns", "roi_txns"]
    
    pivot["dublin_premium"]     = (pivot["dublin_median"] - pivot["roi_median"]).round(0).astype(int)
    pivot["dublin_premium_pct"] = ((pivot["dublin_premium"] / pivot["roi_median"]) * 100).round(1)
    pivot["dublin_median"]      = pivot["dublin_median"].round(0).astype(int)
    pivot["roi_median"]         = pivot["roi_median"].round(0).astype(int)
    
    pivot.to_csv(f"{OUTPUT_DIR}/02_dublin_vs_roi.csv", index=False)
    print(f"  Stage 2: Dublin vs ROI — {len(pivot)} rows")
    return pivot


# ── STAGE 3: REGIONAL TRENDS ──────────────────────────────────────────────────
def regional_trends(tx):
    regional = (tx.groupby(["region", "year"])
                  .agg(transactions=("price_eur", "count"),
                       median_price=("price_eur", "median"),
                       avg_price=("price_eur", "mean"))
                  .reset_index())
    
    regional["median_price"] = regional["median_price"].round(0).astype(int)
    regional["avg_price"]    = regional["avg_price"].round(0).astype(int)
    regional = regional.sort_values(["region", "year"])
    regional["yoy_growth_pct"] = (regional.groupby("region")["median_price"]
                                           .pct_change() * 100).round(1)
    
    regional.to_csv(f"{OUTPUT_DIR}/03_regional_trends.csv", index=False)
    print(f"  Stage 3: Regional Trends — {len(regional)} rows")
    return regional


# ── STAGE 4: AFFORDABILITY ────────────────────────────────────────────────────
def affordability_analysis(aff):
    df = aff.copy()
    
    # Deterioration column
    base = df[df["year"] == 2020][["county", "years_salary_to_buy"]].rename(
        columns={"years_salary_to_buy": "yrs_2020"})
    df = df.merge(base, on="county", how="left")
    df["deterioration_vs_2020"] = (df["years_salary_to_buy"] - df["yrs_2020"]).round(1)
    
    df["affordability_status"] = df["years_salary_to_buy"].apply(lambda y:
        "Severe Crisis" if y >= 12 else
        "Critical"      if y >= 9  else
        "High Stress"   if y >= 7  else
        "Moderate"      if y >= 5  else "Manageable"
    )
    
    df.drop(columns=["yrs_2020"], inplace=True)
    df.to_csv(f"{OUTPUT_DIR}/04_affordability.csv", index=False)
    print(f"  Stage 4: Affordability — {len(df)} rows")
    return df


# ── STAGE 5: SUPPLY & DEMAND ──────────────────────────────────────────────────
def supply_analysis(sd):
    df = sd.copy()
    df["supply_gap_label"] = df["supply_ratio"].apply(lambda r:
        "Critical Shortage" if r < 0.40 else
        "Severe Shortage"   if r < 0.60 else
        "Moderate Shortage" if r < 0.80 else "Near Balance"
    )
    df["cumulative_deficit"] = (df.sort_values("year")
                                  .groupby("county")["supply_deficit"]
                                  .cumsum())
    
    df.to_csv(f"{OUTPUT_DIR}/05_supply_demand.csv", index=False)
    print(f"  Stage 5: Supply & Demand — {len(df)} rows")
    return df


# ── STAGE 6: INVESTMENT SCORES ────────────────────────────────────────────────
def investment_analysis(inv):
    df = inv.copy()
    
    # Risk-adjusted return
    df["risk_adj_return"] = (
        df["price_growth_4yr_pct"] * 0.40 +
        df["rental_yield_est_pct"] * 10 * 0.40 -
        df["years_salary_to_buy"]  * 2  * 0.20
    ).round(1)
    
    df["risk_adj_rank"] = df["risk_adj_return"].rank(ascending=False).astype(int)
    
    # National median benchmark
    nat_median = df["median_price_2024"].median()
    df["discount_to_national_pct"] = (
        (nat_median - df["median_price_2024"]) / nat_median * 100
    ).round(1)
    
    df["undervalued_flag"] = (
        (df["median_price_2024"] < nat_median) &
        (df["price_growth_4yr_pct"] > 30) &
        (df["supply_deficit_pct"] > 45)
    )
    
    df.to_csv(f"{OUTPUT_DIR}/06_investment_scores.csv", index=False)
    print(f"  Stage 6: Investment Scores — {len(df)} rows")
    return df


# ── STAGE 7: COMMUTER BELT ────────────────────────────────────────────────────
def commuter_belt(tx, aff, sd):
    cb_tx = (tx[tx["county"].isin(COMMUTER_BELT)]
               .groupby(["county", "year"])
               .agg(transactions=("price_eur", "count"),
                    median_price=("price_eur", "median"))
               .reset_index())
    cb_tx["median_price"] = cb_tx["median_price"].round(0).astype(int)
    
    cb_aff = aff[aff["county"].isin(COMMUTER_BELT)][
        ["county", "year", "years_salary_to_buy", "monthly_rent_estimate"]]
    cb_sd  = sd[sd["county"].isin(COMMUTER_BELT)][
        ["county", "year", "supply_ratio", "supply_deficit"]]
    
    cb = cb_tx.merge(cb_aff, on=["county", "year"]).merge(cb_sd, on=["county", "year"])
    cb = cb.sort_values(["county", "year"])
    cb["yoy_growth_pct"] = (cb.groupby("county")["median_price"]
                              .pct_change() * 100).round(1)
    
    cb.to_csv(f"{OUTPUT_DIR}/07_commuter_belt.csv", index=False)
    print(f"  Stage 7: Commuter Belt — {len(cb)} rows")
    return cb


# ── STAGE 8: MONTHLY VOLUME ───────────────────────────────────────────────────
def monthly_volume(tx):
    mv = (tx.groupby(["year", "month"])
            .agg(transaction_count=("price_eur", "count"),
                 avg_price=("price_eur", "mean"))
            .reset_index())
    mv["avg_price"] = mv["avg_price"].round(0).astype(int)
    mv["month_name"] = pd.to_datetime(mv["month"], format="%m").dt.strftime("%b")
    mv.to_csv(f"{OUTPUT_DIR}/08_monthly_volume.csv", index=False)
    print(f"  Stage 8: Monthly Volume — {len(mv)} rows")
    return mv


# ── STAGE 9: PRICE DISTRIBUTION ──────────────────────────────────────────────
def price_distribution(tx):
    dist = (tx.groupby(["county", "year"])["price_eur"]
              .describe(percentiles=[0.1, 0.25, 0.5, 0.75, 0.9])
              .reset_index())
    dist.columns = ["county", "year", "count", "mean", "std",
                    "min", "p10", "p25", "median", "p75", "p90", "max"]
    dist = dist.round(0)
    dist.to_csv(f"{OUTPUT_DIR}/09_price_distribution.csv", index=False)
    print(f"  Stage 9: Price Distribution — {len(dist)} rows")
    return dist


# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("IrishHomeIQ — Analytics Pipeline\n" + "="*40)
    
    tx, sd, aff, inv = load_data()
    
    market_pulse(tx)
    dublin_vs_roi(tx)
    regional_trends(tx)
    affordability_analysis(aff)
    supply_analysis(sd)
    investment_analysis(inv)
    commuter_belt(tx, aff, sd)
    monthly_volume(tx)
    price_distribution(tx)
    
    print(f"\n✓ All Tableau CSVs written to tableau/")
    print("\nKey findings preview:")
    inv_df = pd.read_csv(f"{OUTPUT_DIR}/06_investment_scores.csv")
    print("\nTop 5 Investment Opportunities:")
    print(inv_df[["rank","county","composite_investment_score",
                  "investment_tier","median_price_2024",
                  "price_growth_4yr_pct","rental_yield_est_pct"
                  ]].head(5).to_string(index=False))
    
    aff_df = pd.read_csv(f"{OUTPUT_DIR}/04_affordability.csv")
    worst = aff_df[aff_df["year"]==2024].nlargest(5, "years_salary_to_buy")
    print("\nMost Unaffordable Counties (2024):")
    print(worst[["county","median_price","years_salary_to_buy",
                 "affordability_status"]].to_string(index=False))
    
    div_df = pd.read_csv(f"{OUTPUT_DIR}/02_dublin_vs_roi.csv")
    print("\nDublin Premium over Rest of Ireland:")
    print(div_df[["year","dublin_median","roi_median",
                  "dublin_premium","dublin_premium_pct"]].to_string(index=False))
