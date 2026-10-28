# Complete revenue history: no nulls, no 5-period cap

If you have used a popular finance API, you know the pattern:
`annualTotalRevenues` comes back null for every year except the latest,
`pegRatio` is null forever, and time series quietly stop after 5 entries.

EDGAR Fundamentals exists because SEC filings themselves contain none of
those problems. The gaps were introduced by pipelines. We removed them.

## How it works

- **Source:** SEC EDGAR company filings, public domain, no scraping of
  quote sites and no licensing gray zones.
- **Alias merging:** Apple alone has reported revenue under several
  EDGAR tags across the years (RevenueFromContractWithCustomer...,
  Revenues, SalesRevenueNet). We merge the alias tags into one continuous
  series, which is the step that eliminates the famous gaps.
- **Honest unknowns:** where a figure genuinely requires analyst
  estimates (PEG), the API returns an explanation plus the real trailing
  earnings growth it can stand behind. Never a silent null.

## Verified example

Apple (AAPL) annual revenue through this API: **19 consecutive fiscal
years, 2007-2025, zero nulls, zero gaps.** The figures match Apple's own
reported numbers exactly where they overlap (FY2018: $265.595B,
FY2020: $274.515B).

Company summary (name, exchange, SIC industry, headquarters) and
industry-peer tickers come from the same filings data, the fields users
reported missing elsewhere.

Live on RapidAPI: search "EDGAR Fundamentals".
