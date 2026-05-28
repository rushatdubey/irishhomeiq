-- ============================================================
-- IrishHomeIQ — Affordability Crisis & Supply Gap Analysis
-- The business story: where is it most broken, and why?
-- ============================================================

-- ── 1. AFFORDABILITY CRISIS RANKING (Years of salary to buy) ────────────────
SELECT
    a.county,
    a.region,
    a.year,
    a.median_price,
    a.avg_annual_wage,
    a.years_salary_to_buy,
    a.price_to_income_ratio,
    a.monthly_rent_estimate,
    -- Classify severity
    CASE
        WHEN a.years_salary_to_buy >= 12 THEN 'Severe Crisis'
        WHEN a.years_salary_to_buy >= 9  THEN 'Critical'
        WHEN a.years_salary_to_buy >= 7  THEN 'High Stress'
        WHEN a.years_salary_to_buy >= 5  THEN 'Moderate'
        ELSE 'Manageable'
    END                                                 AS affordability_status,
    -- Rank within year
    RANK() OVER (
        PARTITION BY a.year
        ORDER BY a.years_salary_to_buy DESC
    )                                                   AS unaffordability_rank
FROM affordability a
ORDER BY a.year, a.years_salary_to_buy DESC;


-- ── 2. AFFORDABILITY DETERIORATION 2020→2024 ────────────────────────────────
WITH endpoints AS (
    SELECT county, region,
        MAX(CASE WHEN year = 2020 THEN years_salary_to_buy END) AS ratio_2020,
        MAX(CASE WHEN year = 2024 THEN years_salary_to_buy END) AS ratio_2024,
        MAX(CASE WHEN year = 2020 THEN median_price END)         AS price_2020,
        MAX(CASE WHEN year = 2024 THEN median_price END)         AS price_2024
    FROM affordability
    GROUP BY county, region
)
SELECT *,
    ROUND(ratio_2024 - ratio_2020, 1)                  AS yrs_salary_deterioration,
    ROUND((price_2024 - price_2020) * 100.0 /
          NULLIF(price_2020, 0), 1)                     AS price_growth_pct,
    CASE WHEN ratio_2024 - ratio_2020 >= 2 THEN 'Rapidly Worsening'
         WHEN ratio_2024 - ratio_2020 >= 1 THEN 'Worsening'
         ELSE 'Stable'
    END                                                 AS trend
FROM endpoints
ORDER BY yrs_salary_deterioration DESC;


-- ── 3. SUPPLY DEFICIT — WHERE DEMAND CRUSHES SUPPLY ─────────────────────────
SELECT
    sd.county,
    sd.region,
    sd.year,
    sd.new_completions,
    sd.estimated_demand,
    sd.supply_deficit,
    sd.supply_ratio,
    sd.supply_deficit_pct,
    -- Cumulative unmet demand
    SUM(sd.supply_deficit) OVER (
        PARTITION BY sd.county
        ORDER BY sd.year
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    )                                                   AS cumulative_deficit,
    CASE
        WHEN sd.supply_ratio < 0.40 THEN 'Critical Shortage'
        WHEN sd.supply_ratio < 0.60 THEN 'Severe Shortage'
        WHEN sd.supply_ratio < 0.80 THEN 'Moderate Shortage'
        ELSE 'Near Balance'
    END                                                 AS supply_status
FROM supply_demand sd
ORDER BY sd.county, sd.year;


-- ── 4. SUPPLY VS PRICE CORRELATION ──────────────────────────────────────────
-- Counties where supply is lowest tend to have highest price growth
WITH supply_avg AS (
    SELECT county, ROUND(AVG(supply_ratio), 3) AS avg_supply_ratio
    FROM supply_demand GROUP BY county
),
price_growth AS (
    SELECT county,
        ROUND(
            (MAX(CASE WHEN year = 2024 THEN median_price END) -
             MAX(CASE WHEN year = 2020 THEN median_price END)) * 100.0 /
            NULLIF(MAX(CASE WHEN year = 2020 THEN median_price END), 0), 1
        ) AS price_growth_pct
    FROM affordability GROUP BY county
)
SELECT
    s.county,
    s.avg_supply_ratio,
    p.price_growth_pct,
    CASE
        WHEN s.avg_supply_ratio < 0.5 AND p.price_growth_pct > 40
        THEN 'High Pressure — Low Supply + High Growth'
        WHEN s.avg_supply_ratio < 0.5
        THEN 'Supply Constrained'
        WHEN p.price_growth_pct > 40
        THEN 'High Growth'
        ELSE 'Moderate'
    END AS market_pressure_label
FROM supply_avg s
JOIN price_growth p USING(county)
ORDER BY price_growth_pct DESC;


-- ── 5. LEINSTER COMMUTER BELT ANALYSIS (Dublin overspill counties) ───────────
SELECT
    t.county,
    t.year,
    COUNT(*)                                            AS transactions,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP
          (ORDER BY t.price_eur), 0)                    AS median_price,
    a.years_salary_to_buy,
    sd.supply_ratio,
    sd.supply_deficit
FROM transactions t
JOIN affordability a   ON t.county = a.county AND t.year = a.year
JOIN supply_demand sd  ON t.county = sd.county AND t.year = sd.year
WHERE t.county IN ('Kildare', 'Meath', 'Wicklow', 'Louth', 'Westmeath')
  AND t.not_full_market = FALSE
GROUP BY t.county, t.year, a.years_salary_to_buy, sd.supply_ratio, sd.supply_deficit
ORDER BY t.county, t.year;
