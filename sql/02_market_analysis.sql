-- ============================================================
-- IrishHomeIQ — Market Pulse Analysis
-- Monthly/Annual price trends, county benchmarking,
-- transaction volumes, YoY growth
-- ============================================================

-- ── 1. ANNUAL MEDIAN PRICE BY COUNTY WITH YoY GROWTH ────────────────────────
WITH annual_medians AS (
    SELECT
        county,
        region,
        year,
        COUNT(*)                                        AS transaction_count,
        ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP
              (ORDER BY price_eur), 0)                  AS median_price,
        ROUND(AVG(price_eur), 0)                        AS avg_price,
        ROUND(MIN(price_eur), 0)                        AS min_price,
        ROUND(MAX(price_eur), 0)                        AS max_price
    FROM transactions
    WHERE not_full_market = FALSE
    GROUP BY county, region, year
),
with_growth AS (
    SELECT *,
        LAG(median_price) OVER (
            PARTITION BY county ORDER BY year
        )                                               AS prev_year_median,
        ROUND(
            (median_price - LAG(median_price) OVER (
                PARTITION BY county ORDER BY year
            )) * 100.0 /
            NULLIF(LAG(median_price) OVER (
                PARTITION BY county ORDER BY year
            ), 0), 1
        )                                               AS yoy_growth_pct
    FROM annual_medians
)
SELECT *,
    ROUND(median_price / NULLIF(
        FIRST_VALUE(median_price) OVER (
            PARTITION BY county ORDER BY year
        ), 0) * 100 - 100, 1
    )                                                   AS growth_since_2020_pct
FROM with_growth
ORDER BY county, year;


-- ── 2. DUBLIN VS REST OF IRELAND — ANNUAL DIVERGENCE ────────────────────────
WITH annual AS (
    SELECT
        year,
        CASE WHEN county = 'Dublin' THEN 'Dublin' ELSE 'Rest of Ireland' END AS market,
        ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_eur), 0) AS median_price,
        COUNT(*) AS transactions
    FROM transactions
    WHERE not_full_market = FALSE
    GROUP BY year, market
),
pivoted AS (
    SELECT year,
        MAX(CASE WHEN market = 'Dublin'          THEN median_price END) AS dublin_median,
        MAX(CASE WHEN market = 'Rest of Ireland' THEN median_price END) AS roi_median,
        SUM(transactions)                                                AS total_transactions
    FROM annual
    GROUP BY year
)
SELECT *,
    dublin_median - roi_median                          AS dublin_premium,
    ROUND((dublin_median - roi_median) * 100.0 /
          NULLIF(roi_median, 0), 1)                     AS dublin_premium_pct
FROM pivoted
ORDER BY year;


-- ── 3. REGIONAL PRICE TRAJECTORY (Leinster/Munster/Connacht/Ulster) ──────────
SELECT
    region,
    year,
    COUNT(*)                                            AS transactions,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP
          (ORDER BY price_eur), 0)                      AS median_price,
    ROUND(AVG(price_eur), 0)                            AS avg_price,
    ROUND(STDDEV(price_eur), 0)                         AS price_stddev
FROM transactions
WHERE not_full_market = FALSE
GROUP BY region, year
ORDER BY region, year;


-- ── 4. MONTHLY TRANSACTION VOLUME & SEASONAL PATTERNS ───────────────────────
SELECT
    year,
    month,
    COUNT(*)                                            AS transaction_count,
    ROUND(AVG(price_eur), 0)                            AS avg_price,
    ROUND(AVG(COUNT(*)) OVER (
        PARTITION BY month
        ORDER BY year
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ), 0)                                               AS rolling_3yr_avg_volume
FROM transactions
WHERE not_full_market = FALSE
GROUP BY year, month
ORDER BY year, month;


-- ── 5. NEW vs SECOND-HAND PRICE PREMIUM ─────────────────────────────────────
SELECT
    county,
    year,
    ROUND(AVG(CASE WHEN property_type LIKE '%New%'
                   THEN price_eur END), 0)              AS avg_new_price,
    ROUND(AVG(CASE WHEN property_type LIKE '%Second%'
                   THEN price_eur END), 0)              AS avg_secondhand_price,
    ROUND(AVG(CASE WHEN property_type LIKE '%New%'
                   THEN price_eur END) -
          AVG(CASE WHEN property_type LIKE '%Second%'
                   THEN price_eur END), 0)              AS new_vs_secondhand_premium
FROM transactions
WHERE not_full_market = FALSE
GROUP BY county, year
HAVING COUNT(CASE WHEN property_type LIKE '%New%' THEN 1 END) > 10
ORDER BY county, year;
