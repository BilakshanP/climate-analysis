# Temperature Analysis — Project Handoff

Multi-city temperature and rainfall analysis for 6 Indian cities using daily weather data from 1951–2026 (Open-Meteo archive API).

## Cities

Defined in `config.toml`. Default set: Shimla, Manali, Kangra, Delhi, Mumbai, Bengaluru.

## Project Structure

```
temperature-analysis/
├── config.toml             # City definitions (coords, order, colors, year range)
├── pyproject.toml          # uv project config (Python 3.14+)
├── uv.lock                 # Locked dependencies
├── src/
│   └── multi_city_analysis.py   # Single script — data fetch/cache, stats, 8 charts
├── data/                        # Coordinate-based cache (auto-managed)
│   ├── {lat}_{lon}.csv          # One CSV per coordinate pair, sorted & deduped
│   └── ...
└── output/                      # Generated charts
    ├── multi_city_analysis.png
    ├── multi_city_analysis.svg
    └── temperature_analysis.png
```

## Setup & Run

```bash
# Install dependencies (one-time)
uv sync

# Run the main multi-city analysis (from project root)
uv run src/multi_city_analysis.py
```

On first run, `multi_city_analysis.py` fetches data from the Open-Meteo API and caches it as `data/{lat}_{lon}.csv`. Subsequent runs only fetch missing date ranges — gaps are detected by scanning the dates already present in the CSV. Rate-limited requests (429) are retried 3 times with exponential backoff (30s, 60s, 120s).

## Configuration (`config.toml`)

Cities are defined in `config.toml` at the project root. Top-level settings control the data range:

```toml
start_year = 1951
end_year = 2026
```

Each city is a TOML table under `[cities.<Name>]` with required `lat`/`lon` and optional `idx` and `color`:

```toml
[cities.Shimla]
lat = 31.1048
lon = 77.1734
idx = 1              # optional: controls ordering (1-based)
color = "steelblue"  # optional: name or "#hex"
```

**Ordering:** Default is `idx` first (sorted by idx), then alphabetically. Set `sort_by = "lat"` (lon secondary) or `sort_by = "lon"` (lat secondary) at the top level to override.

**Colors:** Priority is config `color` → default palette (13 colors) → deterministic random (md5 hash of city name). Hex values like `"#ff7f0e"` are supported.

To add a new city, add a `[cities.<Name>]` block with `lat` and `lon`. Changing `start_year`/`end_year` only fetches the missing date ranges — existing cached data is preserved.

### Output (`[output]`)

```toml
[output]
png = true       # enable/disable PNG output
svg = true       # enable/disable SVG output
png_dpi = 100    # PNG resolution (dots per inch)
```

All three keys are optional and default to the values shown above.

## Dependencies

- `pandas` — data manipulation
- `matplotlib` — charts
- `requests` — API calls
- `numpy` — linear regression for warming rate

## What `multi_city_analysis.py` Produces

### Console: Summary Table

Transposed layout — cities as columns, stats as rows — printed as a single compact table:

| Row | Description |
|-----|-------------|
| Record High/Low | All-time max and min temperatures (°C) |
| High/Low Year | Year the record occurred |
| Avg Max/Min | Mean daily max/min over full period (°C) |
| Std Max/Min | Standard deviation of daily max/min — measures volatility |
| °C/decade | Linear trend in annual avg max temp per decade |
| Max/Min ΔT | Difference between first and last decade averages (°C) |
| Extreme/yr | Average days per year exceeding 40°C |
| Avg mm/yr | Mean annual total rainfall |
| Wettest/Driest yr | Year with most/least rainfall and amount (mm) |
| CV % | Coefficient of variation of annual rainfall — lower = more reliable |

### Charts (8 subplots, 4×2 grid)

1. **Annual Avg Max Temperature** — 5-year rolling mean per city
2. **Annual Avg Min Temperature** — 5-year rolling mean per city
3. **Monthly Avg Max Temperature** — seasonal climatology
4. **Monthly Avg Min Temperature** — seasonal climatology
5. **Average Annual Rainfall** — bar chart comparison across cities
6. **Annual Rainfall Trend** — 5-year rolling total per city
7. **Full Temperature Range** — shaded band (min–max) per city over time
8. **Extreme Heat Days >40°C** — 5-year rolling count per city

Output: `output/multi_city_analysis.png` and `.svg`

## Data Source

[Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api) — free, no API key required. Daily `temperature_2m_max`, `temperature_2m_min`, `precipitation_sum`.

## Key Findings

- **Delhi** has ~37 extreme heat days (>40°C) per year — far more than any other city
- **Manali** is warming fastest at +0.32°C/decade
- **Mumbai** has the most stable daily temperatures (lowest std dev)
- **Kangra** has the most variable rainfall (CV 31%)

## Notes

- All scripts must be run from the **project root** (paths are relative to it)
- Data is cached as flat `data/{lat}_{lon}.csv` files; fetched date ranges are inferred from the dates present in each CSV
- **Update this HANDOFF.md after any major changes** (new scripts, config changes, output format changes, etc.)
