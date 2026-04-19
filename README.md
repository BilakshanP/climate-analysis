# Temperature Analysis

Multi-city temperature and rainfall analysis using daily weather data from the [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api). No API key required.

Fetches daily max/min temperature and precipitation for any set of cities, caches the data locally, and produces a summary table and 8-chart visualization.

## Quick Start

```bash
# Requires Python 3.14+ and uv
uv sync
uv run src/multi_city_analysis.py
```

On first run, data is fetched from the API and cached as `data/{lat}_{lon}.csv`. Subsequent runs only fetch missing date ranges.

## Configuration

Everything is controlled via `config.toml`:

```toml
start_year = 1951
end_year = 2026
timezone = "UTC"

# sort_by = "lat"    # "lat" | "lon" | omit for idx/alphabetical
# sort_order = "asc" # "asc" | "desc"

[output]
png = true
svg = true
png_dpi = 100

[cities.London]
lat = 51.5074
lon = -0.1278
color = "steelblue"   # optional: name or "#hex"
# idx = 1             # optional: controls ordering (1-based)
```

To add a city, add a `[cities.<Name>]` block with `lat` and `lon`. To remove one, delete or comment out the block.

## Output

### Terminal — Summary Table

Cities as columns, stats as rows:

```
               London     NewYork      Sydney       Cairo    SaoPaulo
  Record High   37.30       39.40       45.20       47.80       39.20
   Record Low  -13.40      -21.10       -0.10        1.40        3.20
      Avg Max   14.52       16.38       22.08       28.72       27.22
      ...
```

### Charts — 8 subplots (4×2 grid)

1. Annual Avg Max Temperature (5-yr rolling)
2. Annual Avg Min Temperature (5-yr rolling)
3. Monthly Avg Max Temperature (climatology)
4. Monthly Avg Min Temperature (climatology)
5. Average Annual Rainfall (bar chart)
6. Annual Rainfall Trend (5-yr rolling)
7. Full Temperature Range (shaded min–max band)
8. Extreme Heat Days >40°C (5-yr rolling)

Saved to `output/multi_city_analysis.png` and `.svg` (configurable).

## Data Caching

- Cached as flat CSV files: `data/{lat}_{lon}.csv`
- Gaps detected automatically by scanning dates in the CSV
- Rate-limited API responses (429) retried 3× with exponential backoff
- Changing `start_year`/`end_year` only fetches the missing ranges

## Dependencies

- pandas, matplotlib, numpy, requests
