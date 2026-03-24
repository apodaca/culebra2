import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from jinja2 import Environment, FileSystemLoader
import os
import requests
from io import StringIO
import datetime

# 1. Fetch data
URL = 'https://wcc.sc.egov.usda.gov/reportGenerator/view_csv/customSingleStationReport/daily/430:CO:SNTL%7Cid=%22%22%7Cname/POR_BEGIN,POR_END/WTEQ::value,PREC::value,TMAX::value,TMIN::value,TAVG::value,PRCP::value'

print("Fetching data from USDA...")
response = requests.get(URL)
response.raise_for_status()

# 2. Parse CSV
lines = [line for line in response.text.split('\n') if not line.startswith('#')]
csv_data = '\n'.join(lines)

df = pd.read_csv(StringIO(csv_data))
df.columns = ['Date', 'SWE', 'Precip_Accum', 'T_Max', 'T_Min', 'T_Avg', 'Precip_Inc']
df['Date'] = pd.to_datetime(df['Date'])
df.set_index('Date', inplace=True)

# 3. Add Water Year and Day of Water Year
def get_water_year(date):
    if date.month >= 10:
        return date.year + 1
    return date.year

df['WaterYear'] = df.index.map(get_water_year)

def get_dummy_date(date):
    if date.month >= 10:
        return datetime.date(1999, date.month, date.day)
    else:
        if date.month == 2 and date.day == 29:
            return datetime.date(2000, 2, 29)
        return datetime.date(2000, date.month, date.day)

df['DummyDate'] = df.index.map(get_dummy_date)
df['DummyDate'] = pd.to_datetime(df['DummyDate'])

current_wy = df['WaterYear'].max()
current_df = df[df['WaterYear'] == current_wy]
hist_df = df[df['WaterYear'] < current_wy]

# 4. Advanced Analytics: Bottom 10% (Worst Years) and Percentile Rank
yearly_max_swe = df.groupby('WaterYear')['SWE'].max().dropna()
current_max_swe = current_df['SWE'].max()
last_current_date = current_df.index[-1]
target_date_str = last_current_date.strftime("%B %d")

if pd.isna(current_max_swe):
    percentile = "N/A"
else:
    less = (yearly_max_swe < current_max_swe).sum()
    equal = (yearly_max_swe == current_max_swe).sum()
    percentile_val = (less + 0.5 * equal) / len(yearly_max_swe) * 100
    percentile_int = int(round(percentile_val))
    ordinal = lambda n: "%d%s" % (n,"tsnrhtdd"[(n//10%10!=1)*(n%10<4)*n%10::4])
    percentile = ordinal(percentile_int)

p10_threshold = yearly_max_swe.quantile(0.10)
worst_years = yearly_max_swe[yearly_max_swe <= p10_threshold].index.tolist()
worst_years_filtered = [y for y in worst_years if y != current_wy]
worst_years_df = df[df['WaterYear'].isin(worst_years_filtered)]

# Tabular Data for Worst Years comparison
table_data = []
# Current year row
table_data.append({
    'Year': current_wy,
    'SWE': current_df['SWE'].iloc[-1] if not current_df.empty else "N/A",
    'Precip': current_df['Precip_Accum'].iloc[-1] if not current_df.empty else "N/A"
})

for wy in sorted(worst_years_filtered):
    wy_df = df[df['WaterYear'] == wy]
    match = wy_df[(wy_df.index.month == last_current_date.month) & (wy_df.index.day == last_current_date.day)]
    if not match.empty:
        swe_val = match['SWE'].iloc[-1]
        precip_val = match['Precip_Accum'].iloc[-1]
        table_data.append({
            'Year': wy,
            'SWE': f"{swe_val:.1f}" if pd.notna(swe_val) else "N/A",
            'Precip': f"{precip_val:.1f}" if pd.notna(precip_val) else "N/A"
        })
    else:
        table_data.append({'Year': wy, 'SWE': "N/A", 'Precip': "N/A"})

# Compute Historical Median and Mean
daily_stats = hist_df.groupby('DummyDate').agg({
    'SWE': ['median', 'mean'],
    'Precip_Accum': ['median', 'mean'],
    'T_Max': 'mean',
    'T_Min': 'mean'
}).reset_index()
daily_stats.columns = ['DummyDate', 'SWE_Median', 'SWE_Mean', 'Precip_Median', 'Precip_Mean', 'T_Max_Mean', 'T_Min_Mean']

worst_daily_stats = worst_years_df.groupby('DummyDate').agg({
    'SWE': 'mean',
    'Precip_Accum': 'mean'
}).reset_index()
worst_daily_stats.columns = ['DummyDate', 'SWE_Worst_Mean', 'Precip_Worst_Mean']

# 5. Generate Plots
os.makedirs('output', exist_ok=True)

# Common X-Axis constraints (Oct 1 to May 31)
x_axis_range = ["1999-10-01", "2000-05-31"]

# Plot 1: SWE (Index)
fig_swe = go.Figure()
fig_swe.add_trace(go.Scatter(x=daily_stats['DummyDate'], y=daily_stats['SWE_Median'], name='Historic Median', line=dict(color='gray', dash='dash')))
fig_swe.add_trace(go.Scatter(x=current_df['DummyDate'], y=current_df['SWE'], name=f'Current WY ({current_wy})', line=dict(color='#1f77b4', width=3)))
fig_swe.update_layout(title="Snow Water Equivalent (SWE) - Current vs Historic Median", xaxis_title="Date", yaxis_title="SWE (inches)", template='plotly_white', xaxis=dict(tickformat="%b %d", range=x_axis_range))
swe_div = fig_swe.to_html(full_html=False, include_plotlyjs='cdn')

# Plot 2: Precipitation Accumulation (Index)
fig_precip = go.Figure()
fig_precip.add_trace(go.Scatter(x=daily_stats['DummyDate'], y=daily_stats['Precip_Median'], name='Historic Median', line=dict(color='gray', dash='dash')))
fig_precip.add_trace(go.Scatter(x=current_df['DummyDate'], y=current_df['Precip_Accum'], name=f'Current WY ({current_wy})', line=dict(color='#2ca02c', width=3)))
fig_precip.update_layout(title="Precipitation Accumulation - Current vs Historic", xaxis_title="Date", yaxis_title="Precipitation (inches)", template='plotly_white', xaxis=dict(tickformat="%b %d", range=x_axis_range))
precip_div = fig_precip.to_html(full_html=False, include_plotlyjs=False)

# Plot 3: Temperature (Index)
last_30 = df.iloc[-30:]
fig_temp = go.Figure()
fig_temp.add_trace(go.Scatter(x=last_30.index, y=last_30['T_Max'], name="Max Temp", line=dict(color='#d62728')))
fig_temp.add_trace(go.Scatter(x=last_30.index, y=last_30['T_Min'], name="Min Temp", line=dict(color='#1f77b4')))
fig_temp.add_trace(go.Scatter(x=last_30.index, y=last_30['T_Avg'], name="Avg Temp", line=dict(color='#ff7f0e', dash='dot')))
fig_temp.update_layout(title="Temperatures (Last 30 Days)", xaxis_title="Date", yaxis_title="Temperature (°F)", template='plotly_white')
temp_div = fig_temp.to_html(full_html=False, include_plotlyjs=False)

# Plot 4: Worst Years Analysis (Enhanced Q&A Chart)
fig_worst = go.Figure()

# Historic Median
fig_worst.add_trace(go.Scatter(x=daily_stats['DummyDate'], y=daily_stats['SWE_Median'], name='Historic Median', line=dict(color='#7f7f7f', width=2, dash='dot')))

for wy in worst_years_filtered:
    wy_data = df[df['WaterYear'] == wy]
    fig_worst.add_trace(go.Scatter(x=wy_data['DummyDate'], y=wy_data['SWE'], name=f'WY {wy}', mode='lines', line=dict(width=1), opacity=0.4))

fig_worst.add_trace(go.Scatter(x=worst_daily_stats['DummyDate'], y=worst_daily_stats['SWE_Worst_Mean'], name='Bottom 10% Mean', line=dict(color='#d62728', width=3, dash='dash')))
fig_worst.add_trace(go.Scatter(x=current_df['DummyDate'], y=current_df['SWE'], name=f'Current WY ({current_wy})', line=dict(color='#1f77b4', width=4)))
fig_worst.update_layout(
    title=f"SWE: Peak & Dropoff Comparison (WY {current_wy} vs Median & Challenging Years)", 
    xaxis_title="Date", 
    yaxis_title="SWE (inches)", 
    template='plotly_white', 
    xaxis=dict(tickformat="%b %d", range=x_axis_range),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)
worst_swe_div = fig_worst.to_html(full_html=False, include_plotlyjs='cdn')


# 6. HTML Template Generation
env = Environment(loader=FileSystemLoader('templates'))

# Render Index
template_index = env.get_template('index.html')
html_index = template_index.render(
    station_name="Culebra #2 SNOTEL",
    current_wy=current_wy,
    update_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    swe_div=swe_div,
    precip_div=precip_div,
    temp_div=temp_div,
    current_swe=current_df['SWE'].iloc[-1] if not current_df.empty else 'N/A',
    current_precip=current_df['Precip_Accum'].iloc[-1] if not current_df.empty else 'N/A',
    percentile=percentile
)
with open('output/index.html', 'w', encoding='utf-8') as f:
    f.write(html_index)

# Render Worst Years
template_worst = env.get_template('worst_years.html')
worst_years_str = ", ".join([str(y) for y in worst_years])
html_worst = template_worst.render(
    station_name="Culebra #2 SNOTEL",
    current_wy=current_wy,
    update_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    worst_swe_div=worst_swe_div,
    percentile=percentile,
    worst_years_str=worst_years_str,
    target_date_str=target_date_str,
    table_data=table_data,
    current_swe=current_df['SWE'].iloc[-1] if not current_df.empty else 'N/A',
    current_precip=current_df['Precip_Accum'].iloc[-1] if not current_df.empty else 'N/A'
)
with open('output/worst_years.html', 'w', encoding='utf-8') as f:
    f.write(html_worst)

print("Dashboards generated successfully in output/")
