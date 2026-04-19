#!/usr/bin/env python3
import os
import sys
import time
import hashlib
import tomllib
import requests
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from datetime import date, timedelta

# --- Data cache ---
DATA_DIR = "data"


def _coord_path(lat, lon):
    return os.path.join(DATA_DIR, f"{lat}_{lon}.csv")


def _existing_ranges(df):
    if df.empty:
        return []
    dates = sorted(df["Date"].dt.date.unique())
    ranges = [[dates[0], dates[0]]]
    for d in dates[1:]:
        if d == ranges[-1][1] + timedelta(days=1):
            ranges[-1][1] = d
        else:
            ranges.append([d, d])
    return [tuple(r) for r in ranges]


def _compute_gaps(req_start, req_end, existing):
    gaps = []
    cursor = req_start
    for s, e in existing:
        if s > cursor:
            gaps.append((cursor, min(s - timedelta(days=1), req_end)))
        cursor = max(cursor, e + timedelta(days=1))
        if cursor > req_end:
            break
    if cursor <= req_end:
        gaps.append((cursor, req_end))
    return gaps


def _fetch_api(lat, lon, start, end):
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
        "timezone": _TIMEZONE,
    }
    delays = [30, 60, 120]
    for attempt in range(4):
        r = requests.get(url, params=params, timeout=60)
        if r.status_code == 429 and attempt < 3:
            wait = delays[attempt]
            print(f"    ⚠ Rate limited (429). Retrying in {wait}s... (attempt {attempt + 2}/4)")
            time.sleep(wait)
            continue
        r.raise_for_status()
        d = r.json()["daily"]
        return pd.DataFrame({
            "Date": pd.to_datetime(d["time"]),
            "Temp Max": pd.to_numeric(d["temperature_2m_max"], errors="coerce"),
            "Temp Min": pd.to_numeric(d["temperature_2m_min"], errors="coerce"),
            "Rain": pd.to_numeric(d["precipitation_sum"], errors="coerce"),
        })


def _load_city(label, lat, lon, start_year, end_year):
    os.makedirs(DATA_DIR, exist_ok=True)
    csv_path = _coord_path(lat, lon)
    req_start = date(start_year, 1, 1)
    req_end = min(date(end_year, 12, 31), date.today() - timedelta(days=1))

    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path, parse_dates=["Date"])
    else:
        df = pd.DataFrame(columns=["Date", "Temp Max", "Temp Min", "Rain"])
        df["Date"] = pd.to_datetime(df["Date"])

    existing = _existing_ranges(df)
    gaps = _compute_gaps(req_start, req_end, existing)
    fmt_ranges = ", ".join(f"{s} to {e}" for s, e in existing)

    if not gaps:
        print(f"  {label} — cached [{fmt_ranges}] ✓")
    else:
        print(f"  {label} — {'cached [' + fmt_ranges + ']' if existing else 'no cache'}")
        for gs, ge in gaps:
            print(f"    → fetching {gs} to {ge}...")
            new_df = _fetch_api(lat, lon, gs, ge)
            df = pd.concat([df, new_df], ignore_index=True) \
                   .drop_duplicates(subset=["Date"]).sort_values("Date").reset_index(drop=True)
            df.to_csv(csv_path, index=False)
            time.sleep(15)

    return df[(df["Date"] >= str(req_start)) & (df["Date"] <= str(req_end))].reset_index(drop=True)


# --- Load config ---
CONFIG_PATH = "config.toml"
if not os.path.exists(CONFIG_PATH):
    sys.exit(f"Error: {CONFIG_PATH} not found. See HANDOFF.md for the expected format.")
with open(CONFIG_PATH, "rb") as f:
    _cfg = tomllib.load(f)
if "cities" not in _cfg or not _cfg["cities"]:
    sys.exit(f"Error: No [cities.*] entries in {CONFIG_PATH}.")

START_YEAR = _cfg.get("start_year", 1951)
END_YEAR = _cfg.get("end_year", 2026)
_out = _cfg.get("output", {})
_SAVE_PNG = _out.get("png", True)
_SAVE_SVG = _out.get("svg", True)
_PNG_DPI = _out.get("png_dpi", 100)
_TIMEZONE = _cfg.get("timezone", "UTC")
_YEAR_LABEL = f"{START_YEAR}-{END_YEAR}"

# Order: sort_by config > idx first (sorted by idx) > rest alphabetically
_sort_by = _cfg.get("sort_by")
_sort_desc = _cfg.get("sort_order", "asc") == "desc"
_all_cities = list(_cfg["cities"].items())
if _sort_by == "lat":
    _all_cities.sort(key=lambda x: (x[1]["lat"], x[1]["lon"]), reverse=_sort_desc)
elif _sort_by == "lon":
    _all_cities.sort(key=lambda x: (x[1]["lon"], x[1]["lat"]), reverse=_sort_desc)
else:
    _indexed = sorted((x for x in _all_cities if "idx" in x[1]), key=lambda x: x[1]["idx"], reverse=_sort_desc)
    _rest = sorted((x for x in _all_cities if "idx" not in x[1]), key=lambda x: x[0], reverse=_sort_desc)
    _all_cities = _indexed + _rest
CITIES = {name: (c["lat"], c["lon"]) for name, c in _all_cities}

# Colors: config override > default palette > deterministic random
_DEFAULT_PALETTE = [
    "steelblue", "purple", "green", "red", "orange", "brown",
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2",
]
_city_colors = {}
_palette_idx = 0
for city in CITIES:
    cfg_color = _cfg["cities"][city].get("color")
    if cfg_color:
        _city_colors[city] = cfg_color
    elif _palette_idx < len(_DEFAULT_PALETTE):
        _city_colors[city] = _DEFAULT_PALETTE[_palette_idx]
        _palette_idx += 1
    else:
        h = hashlib.md5(city.encode()).hexdigest()[:6]
        _city_colors[city] = f"#{h}"

# Load data (incremental fetch with gap detection)
print(f"\nConfig: {_YEAR_LABEL}\n")
_name_w = max(len(c) for c in CITIES)
_lat_w = max(len(str(lat)) for lat, _ in CITIES.values())
_lon_w = max(len(str(lon)) for _, lon in CITIES.values())
city_data = {}
for city, (lat, lon) in CITIES.items():
    label = f"{city:<{_name_w}} ({str(lat) + ',':<{_lat_w + 1}} {str(lon):<{_lon_w}})"
    city_data[city] = _load_city(label, lat, lon, START_YEAR, END_YEAR)

print("\n" + "=" * 70)
print(f"MULTI-CITY TEMPERATURE ANALYSIS ({_YEAR_LABEL})")
print("=" * 70)

# Summary table
summary = []
for city, df in city_data.items():
    df['Year'] = df['Date'].dt.year
    early = df[df['Year'].between(START_YEAR, START_YEAR + 9)]
    recent = df[df['Year'].between(END_YEAR - 9, END_YEAR)]
    yearly_max = df.groupby('Year')['Temp Max'].mean()
    yearly_rain = df.groupby('Year')['Rain'].sum()
    years = yearly_max.index.values.astype(float)
    slope = np.polyfit(years, yearly_max.values, 1)[0] * 10
    extreme = df[df['Temp Max'] > 40].groupby('Year').size()
    summary.append({
        'City': city,
        'All-time Max (°C)': df['Temp Max'].max(),
        'Max Year': int(df.loc[df['Temp Max'].idxmax(), 'Year']),
        'All-time Min (°C)': df['Temp Min'].min(),
        'Min Year': int(df.loc[df['Temp Min'].idxmin(), 'Year']),
        'Avg Max (°C)': df['Temp Max'].mean(),
        'Std Max (°C)': df['Temp Max'].std(),
        'Avg Min (°C)': df['Temp Min'].mean(),
        'Std Min (°C)': df['Temp Min'].std(),
        'Warming (°C/dec)': slope,
        'Max ΔT (°C)': recent['Temp Max'].mean() - early['Temp Max'].mean(),
        'Min ΔT (°C)': recent['Temp Min'].mean() - early['Temp Min'].mean(),
        'Avg Rain (mm/yr)': yearly_rain.mean(),
        'Wettest Year': int(yearly_rain.idxmax()),
        'Wettest (mm)': yearly_rain.max(),
        'Driest Year': int(yearly_rain.idxmin()),
        'Driest (mm)': yearly_rain.min(),
        'Rain CV (%)': (yearly_rain.std() / yearly_rain.mean()) * 100,
        'Extreme Days/yr': extreme.mean() if len(extreme) > 0 else 0,
    })

summary_df = pd.DataFrame(summary).set_index('City').T

_fmt = "  {:>12}" + " {:>11}" * len(summary_df.columns)
_sep = "  " + "-" * (14 + 12 * len(summary_df.columns))
print(f"\n{_sep}\n{_fmt.format('', *summary_df.columns)}\n{_sep}")

_rows = [
    ("Record High", "All-time Max (°C)", ".2f"),
    ("Record Low", "All-time Min (°C)", ".2f"),
    ("Avg Max", "Avg Max (°C)", ".2f"),
    ("Avg Min", "Avg Min (°C)", ".2f"),
    ("Std Max", "Std Max (°C)", ".2f"),
    ("Std Min", "Std Min (°C)", ".2f"),
    ("°C/decade", "Warming (°C/dec)", "+.2f"),
    ("Max ΔT", "Max ΔT (°C)", "+.2f"),
    ("Min ΔT", "Min ΔT (°C)", "+.2f"),
    ("Extreme/yr", "Extreme Days/yr", ".2f"),
    ("Avg mm/yr", "Avg Rain (mm/yr)", ".2f"),
    ("Wettest mm", "Wettest (mm)", ".2f"),
    ("Driest mm", "Driest (mm)", ".2f"),
    ("CV %", "Rain CV (%)", ".2f"),
    ("High Year", "Max Year", ".0f"),
    ("Low Year", "Min Year", ".0f"),
    ("Wettest yr", "Wettest Year", ".0f"),
    ("Driest yr", "Driest Year", ".0f"),
]
for label, key, spec in _rows:
    vals = [f"{v:{spec}}" if isinstance(v, (int, float)) else str(v) for v in summary_df.loc[key]]
    print(_fmt.format(label, *vals))
print(_sep)

# Visualizations
fig, axes = plt.subplots(4, 2, figsize=(16, 20))
fig.suptitle(f'Multi-City Temperature & Rainfall Analysis ({_YEAR_LABEL})', fontsize=16, fontweight='bold')

colors = _city_colors

# 1. Annual max temperature trends
ax1 = axes[0, 0]
for city, df in city_data.items():
    yearly = df.groupby('Year')['Temp Max'].mean()
    ax1.plot(yearly.index, yearly.rolling(5, min_periods=1).mean(), label=city, color=colors[city], linewidth=1.8)
ax1.set_title('Annual Avg Max Temperature (5-yr rolling)')
ax1.set_xlabel('Year')
ax1.set_ylabel('Temperature (°C)')
ax1.legend()
ax1.grid(alpha=0.3)

# 2. Annual min temperature trends
ax2 = axes[0, 1]
for city, df in city_data.items():
    yearly = df.groupby('Year')['Temp Min'].mean()
    ax2.plot(yearly.index, yearly.rolling(5, min_periods=1).mean(), label=city, color=colors[city], linewidth=1.8)
ax2.set_title('Annual Avg Min Temperature (5-yr rolling)')
ax2.set_xlabel('Year')
ax2.set_ylabel('Temperature (°C)')
ax2.legend()
ax2.grid(alpha=0.3)

# 3. Monthly avg max climatology
ax3 = axes[1, 0]
months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
for city, df in city_data.items():
    df['Month'] = df['Date'].dt.month
    monthly = df.groupby('Month')['Temp Max'].mean()
    ax3.plot(range(1, 13), monthly, 'o-', label=city, color=colors[city], linewidth=1.8)
ax3.set_xticks(range(1, 13))
ax3.set_xticklabels(months)
ax3.set_title('Monthly Avg Max Temperature')
ax3.set_ylabel('Temperature (°C)')
ax3.legend()
ax3.grid(alpha=0.3)

# 4. Monthly avg min climatology
ax4 = axes[1, 1]
for city, df in city_data.items():
    monthly = df.groupby('Month')['Temp Min'].mean()
    ax4.plot(range(1, 13), monthly, 'o-', label=city, color=colors[city], linewidth=1.8)
ax4.set_xticks(range(1, 13))
ax4.set_xticklabels(months)
ax4.set_title('Monthly Avg Min Temperature')
ax4.set_ylabel('Temperature (°C)')
ax4.legend()
ax4.grid(alpha=0.3)

# 5. Annual rainfall comparison
ax5 = axes[2, 0]
rain_by_city = []
for city, df in city_data.items():
    annual_rain = df.groupby('Year')['Rain'].sum().mean()
    rain_by_city.append((city, annual_rain))
cities_list = [x[0] for x in rain_by_city]
rain_list = [x[1] for x in rain_by_city]
bars = ax5.bar(cities_list, rain_list, color=[colors[c] for c in cities_list], alpha=0.7)
ax5.set_title('Average Annual Rainfall')
ax5.set_ylabel('Rainfall (mm)')
for bar, val in zip(bars, rain_list):
    ax5.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 20, f'{val:.0f}', ha='center', fontweight='bold')
ax5.grid(alpha=0.3, axis='y')

# 6. Annual rainfall trend
ax6 = axes[2, 1]
for city, df in city_data.items():
    yearly_rain = df.groupby('Year')['Rain'].sum()
    ax6.plot(yearly_rain.index, yearly_rain.rolling(5, min_periods=1).mean(), label=city, color=colors[city], linewidth=1.8)
ax6.set_title('Annual Rainfall Trend (5-yr rolling)')
ax6.set_xlabel('Year')
ax6.set_ylabel('Rainfall (mm)')
ax6.legend()
ax6.grid(alpha=0.3)

# 7. Full temperature trend (max & min) for all cities
ax7 = axes[3, 0]
for city, df in city_data.items():
    yearly = df.groupby('Year').agg({'Temp Max': 'mean', 'Temp Min': 'mean'})
    ax7.fill_between(yearly.index, yearly['Temp Min'].rolling(5, min_periods=1).mean(),
                     yearly['Temp Max'].rolling(5, min_periods=1).mean(), alpha=0.15, color=colors[city])
    ax7.plot(yearly.index, yearly['Temp Max'].rolling(5, min_periods=1).mean(), color=colors[city], linewidth=1.2)
    ax7.plot(yearly.index, yearly['Temp Min'].rolling(5, min_periods=1).mean(), color=colors[city], linewidth=1.2, label=city)
ax7.set_title('Full Temperature Range (5-yr rolling)')
ax7.set_xlabel('Year')
ax7.set_ylabel('Temperature (°C)')
ax7.legend()
ax7.grid(alpha=0.3)

# 8. Extreme heat days (>40°C) trend
ax8 = axes[3, 1]
for city, df in city_data.items():
    extreme = df[df['Temp Max'] > 40].groupby('Year').size().reindex(df['Year'].unique(), fill_value=0)
    if extreme.sum() > 0:
        ax8.plot(extreme.index, extreme.rolling(5, min_periods=1).mean(), label=city, color=colors[city], linewidth=1.8)
ax8.set_title('Extreme Heat Days >40°C (5-yr rolling)')
ax8.set_xlabel('Year')
ax8.set_ylabel('Days per year')
ax8.legend()
ax8.grid(alpha=0.3)

plt.tight_layout(rect=[0, 0, 1, 0.96])
_saved = []
if _SAVE_PNG:
    plt.savefig('output/multi_city_analysis.png', dpi=_PNG_DPI, bbox_inches='tight')
    _saved.append("output/multi_city_analysis.png")
if _SAVE_SVG:
    plt.savefig('output/multi_city_analysis.svg', bbox_inches='tight')
    _saved.append("output/multi_city_analysis.svg")
if _saved:
    print(f"\n✓ Saved: {', '.join(_saved)}")
else:
    print("\n⚠ No output formats enabled in config.toml [output]")
