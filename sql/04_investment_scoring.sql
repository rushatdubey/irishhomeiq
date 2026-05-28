-- ============================================================
-- IrishHomeIQ — Investment Opportunity Scoring
-- Composite model: Growth + Supply Pressure + Yield + Affordability
-- ============================================================

-- ── 1. FULL INVESTMENT SCORECARD ─────────────────────────────────────────────
SELECT
    rank,
    county,
    region,
    investment_tier,
    composite_investment_score,
    median_price_2024,
    price_growth_4yr_pct,
    rental_yield_est_pct,
    years_salary_to_buy,
    supply_deficit_pct,
    growth_score,
    supply_score,
    yield_score,
    affordability_score
FROM investment_scores
ORDER BY rank;


-- ── 2. TIER SUMMARY ──────────────────────────────────────────────────────────
SELECT
    investment_tier,
    COUNT(*)                                        AS county_count,
    ROUND(AVG(composite_investment_score), 1)       AS avg_score,
    ROUND(AVG(median_price_2024), 0)                AS avg_median_price,
    ROUND(AVG(price_growth_4yr_pct), 1)             AS avg_growth_pct,
    ROUND(AVG(rental_yield_est_pct), 2)             AS avg_rental_yield,
    STRING_AGG(county, ', ' ORDER BY rank)          AS counties
FROM investment_scores
GROUP BY investment_tier
ORDER BY avg_score DESC;


-- ── 3. UNDERVALUED COUNTIES ───────────────────────────────────────────────────
-- High supply pressure + strong growth but price still below national median
WITH national_median AS (
    SELECT ROUND(AVG(median_price_2024), 0) AS nat_median
    FROM investment_scores
)
SELECT
    i.county,
    i.region,
    i.median_price_2024,
    n.nat_median,
    ROUND((n.nat_median - i.median_price_2024) * 100.0 /
          NULLIF(n.nat_median, 0), 1)               AS discount_to_national_pct,
    i.price_growth_4yr_pct,
    i.supply_deficit_pct,
    i.composite_investment_score,
    i.investment_tier
FROM investment_scores i
CROSS JOIN national_median n
WHERE i.median_price_2024 < n.nat_median
  AND i.price_growth_4yr_pct > 30
  AND i.supply_deficit_pct > 45
ORDER BY i.composite_investment_score DESC;


-- ── 4. RISK-ADJUSTED RETURN RANKING ──────────────────────────────────────────
-- Combines rental yield with growth but penalises affordability stress
SELECT
    county,
    region,
    median_price_2024,
    price_growth_4yr_pct,
    rental_yield_est_pct,
    years_salary_to_buy,
    -- Risk-adjusted return score
    ROUND(
        (price_growth_4yr_pct * 0.4 +
         rental_yield_est_pct * 10 * 0.4 -
         years_salary_to_buy * 2 * 0.2), 1
    )                                               AS risk_adj_return_score,
    RANK() OVER (
        ORDER BY (price_growth_4yr_pct * 0.4 +
                  rental_yield_est_pct * 10 * 0.4 -
                  years_salary_to_buy * 2 * 0.2) DESC
    )                                               AS risk_adj_rank
FROM investment_scores
ORDER BY risk_adj_return_score DESC;
