"""
IrishHomeIQ — Real PPR Data Loader
Loads, cleans, and merges actual Property Price Register CSV files.

Place your downloaded PPR CSVs in the data/ folder:
    data/PPR-2020.csv
    data/PPR-2021.csv
    data/PPR-2022.csv
    data/PPR-2023.csv
    data/PPR-2024.csv

Then run:
    python python/load_real_data.py

This will produce data/transactions.csv ready for analytics.py
"""

import pandas as pd
import numpy as np
import os, re

DATA_DIR = os.path.join(os.path.dirname(__file__), "../data")

COUNTY_REGIONS = {
    "Dublin": "Leinster", "Kildare": "Leinster", "Meath": "Leinster",
    "Wicklow": "Leinster", "Wexford": "Leinster", "Kilkenny": "Leinster",
    "Carlow": "Leinster", "Laois": "Leinster", "Offaly": "Leinster",
    "Westmeath": "Leinster", "Longford": "Leinster", "Louth": "Leinster",
    "Cork": "Munster", "Limerick": "Munster", "Waterford": "Munster",
    "Tipperary": "Munster", "Clare": "Munster", "Kerry": "Munster",
    "Galway": "Connacht", "Mayo": "Connacht", "Roscommon": "Connacht",
    "Sligo": "Connacht", "Leitrim": "Connacht",
    "Donegal": "Ulster", "Cavan": "Ulster", "Monaghan": "Ulster",
}

# Known PPR column name variants
COL_DATE    = ["Date of Sale (dd/mm/yyyy)", "Date of Sale", "date_of_sale"]
COL_COUNTY  = ["County", "county"]
COL_PRICE   = ["Price (€)", "Price", "price_eur"]
COL_TYPE    = ["Description of Property", "property_type"]
COL_NOTFULL = ["Not Full Market Price", "not_full_market_price"]
COL_VAT     = ["VAT Exclusive", "vat_exclusive"]


def find_col(df, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return None


def clean_price(val):
    """Handle '€320,000', '320000', '320,000.00' etc."""
    if pd.isna(val):
        return np.nan
    s = str(val).replace("€", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return np.nan


def clean_county(val):
    """Standardise county names from PPR (Co. Dublin → Dublin etc.)"""
    if pd.isna(val):
        return None
    s = str(val).strip()
    s = re.sub(r"^Co\.?\s*", "", s, flags=re.IGNORECASE)
    # Handle Dublin postcodes → Dublin
    s = re.sub(r"^Dublin\s*\d+.*", "Dublin", s, flags=re.IGNORECASE)
    s = s.title().strip()
    # Fix known variants
    replacements = {
        "Tipperary North": "Tipperary", "Tipperary South": "Tipperary",
        "Cork City": "Cork", "Cork County": "Cork",
        "Galway City": "Galway", "Galway County": "Galway",
        "Limerick City": "Limerick", "Limerick County": "Limerick",
        "Waterford City": "Waterford", "Waterford County": "Waterford",
    }
    return replacements.get(s, s)


def load_year(year):
    path = os.path.join(DATA_DIR, f"PPR-{year}.csv")
    if not os.path.exists(path):
        print(f"  ⚠  PPR-{year}.csv not found in data/ — skipping")
        return None

    # PPR files are often Latin-1 encoded
    for enc in ["latin-1", "utf-8", "cp1252"]:
        try:
            df = pd.read_csv(path, encoding=enc, low_memory=False)
            break
        except UnicodeDecodeError:
            continue

    print(f"  Loaded PPR-{year}.csv — {len(df):,} rows, columns: {list(df.columns)}")

    # Rename columns to standard names
    rename = {}
    for std, candidates in [
        ("date_of_sale",  COL_DATE),
        ("county",        COL_COUNTY),
        ("price_eur",     COL_PRICE),
        ("property_type", COL_TYPE),
        ("not_full_market_price", COL_NOTFULL),
        ("vat_exclusive", COL_VAT),
    ]:
        col = find_col(df, candidates)
        if col:
            rename[col] = std
    df = df.rename(columns=rename)

    # Ensure required columns exist
    for col in ["date_of_sale", "county", "price_eur"]:
        if col not in df.columns:
            print(f"  ✗  Missing required column '{col}' — skipping year {year}")
            return None

    return df


def clean_and_merge(years):
    frames = []
    for y in years:
        df = load_year(y)
        if df is None:
            continue

        # Clean price
        df["price_eur"] = df["price_eur"].apply(clean_price)

        # Clean county
        df["county"] = df["county"].apply(clean_county)

        # Parse date
        df["date_of_sale"] = pd.to_datetime(
            df["date_of_sale"], dayfirst=True, errors="coerce")

        # Filter
        df = df.dropna(subset=["date_of_sale", "county", "price_eur"])
        df = df[df["price_eur"] > 10000]
        df = df[df["price_eur"] < 5_000_000]
        df = df[df["county"].isin(COUNTY_REGIONS.keys())]

        # Exclude non-market sales
        if "not_full_market_price" in df.columns:
            df = df[df["not_full_market_price"].astype(str).str.upper().isin(["NO", "N", "FALSE", "0", ""])]

        # Add derived columns
        df["year"]    = df["date_of_sale"].dt.year
        df["month"]   = df["date_of_sale"].dt.month
        df["quarter"] = "Q" + df["date_of_sale"].dt.quarter.astype(str)
        df["region"]  = df["county"].map(COUNTY_REGIONS)

        # Standardise property type
        if "property_type" not in df.columns:
            df["property_type"] = "Unknown"

        # Keep only needed columns
        keep = ["date_of_sale", "county", "region", "price_eur",
                "property_type", "year", "month", "quarter"]
        if "vat_exclusive" in df.columns:
            keep.append("vat_exclusive")
        df = df[keep]

        frames.append(df)
        print(f"  ✓  {y}: {len(df):,} clean transactions")

    if not frames:
        print("\n✗ No PPR files found. Run data/generate_data.py instead.")
        return None

    merged = pd.concat(frames, ignore_index=True)
    return merged


def main():
    print("IrishHomeIQ — Real PPR Data Loader\n" + "="*40)
    years = [2020, 2021, 2022, 2023, 2024]
    merged = clean_and_merge(years)

    if merged is None:
        return

    out = os.path.join(DATA_DIR, "transactions.csv")
    merged.to_csv(out, index=False)

    print(f"\n✓ Saved {len(merged):,} transactions to data/transactions.csv")
    print(f"  Counties: {merged['county'].nunique()}")
    print(f"  Years: {sorted(merged['year'].unique())}")
    print(f"  Price range: €{merged['price_eur'].min():,.0f} — €{merged['price_eur'].max():,.0f}")
    print(f"  Median price: €{merged['price_eur'].median():,.0f}")
    print("\nNow run: python python/analytics.py")


if __name__ == "__main__":
    main()
