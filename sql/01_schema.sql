-- ============================================================
-- IrishHomeIQ — PostgreSQL Schema
-- Irish Property Market Intelligence
-- ============================================================

CREATE TABLE transactions (
    transaction_id    SERIAL PRIMARY KEY,
    date_of_sale      DATE NOT NULL,
    county            VARCHAR(50) NOT NULL,
    region            VARCHAR(30) NOT NULL,
    price_eur         NUMERIC(12,2) NOT NULL,
    property_type     VARCHAR(80),
    not_full_market   BOOLEAN DEFAULT FALSE,
    vat_exclusive     BOOLEAN DEFAULT FALSE,
    year              SMALLINT,
    month             SMALLINT,
    quarter           CHAR(2)
);

CREATE TABLE supply_demand (
    id                SERIAL PRIMARY KEY,
    county            VARCHAR(50) NOT NULL,
    region            VARCHAR(30),
    year              SMALLINT NOT NULL,
    new_completions   INT,
    estimated_demand  INT,
    supply_deficit    INT,
    supply_ratio      NUMERIC(5,3),
    supply_deficit_pct NUMERIC(5,1)
);

CREATE TABLE affordability (
    id                    SERIAL PRIMARY KEY,
    county                VARCHAR(50) NOT NULL,
    region                VARCHAR(30),
    year                  SMALLINT NOT NULL,
    median_price          NUMERIC(12,2),
    avg_annual_wage       NUMERIC(10,2),
    years_salary_to_buy   NUMERIC(5,1),
    monthly_rent_estimate NUMERIC(10,2),
    price_to_income_ratio NUMERIC(5,2),
    population            INT
);

CREATE TABLE investment_scores (
    county                    VARCHAR(50) PRIMARY KEY,
    region                    VARCHAR(30),
    median_price_2020         NUMERIC(12,2),
    median_price_2024         NUMERIC(12,2),
    price_growth_4yr_pct      NUMERIC(5,1),
    rental_yield_est_pct      NUMERIC(5,2),
    years_salary_to_buy       NUMERIC(5,1),
    supply_deficit_pct        NUMERIC(5,1),
    growth_score              NUMERIC(5,1),
    supply_score              NUMERIC(5,1),
    yield_score               NUMERIC(5,1),
    affordability_score       NUMERIC(5,1),
    composite_investment_score NUMERIC(5,1),
    investment_tier           VARCHAR(40),
    rank                      SMALLINT
);

CREATE INDEX idx_tx_county_year  ON transactions(county, year);
CREATE INDEX idx_tx_year_month   ON transactions(year, month);
CREATE INDEX idx_tx_region       ON transactions(region);
CREATE INDEX idx_aff_county_year ON affordability(county, year);
CREATE INDEX idx_sd_county_year  ON supply_demand(county, year);
