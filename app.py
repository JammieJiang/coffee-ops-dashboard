from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st


st.set_page_config(page_title="Coffee Ops | Sales Monitor", page_icon="☕", layout="wide")

APP_DIR = Path(__file__).parent
DATA_PATH = APP_DIR / "index_1.csv"
if not DATA_PATH.exists():
    DATA_PATH = APP_DIR / "data" / "index_1.csv"
if not DATA_PATH.exists():
    st.error("Could not find index_1.csv. Place CSV1 in the project folder next to app.py.")
    st.stop()


@st.cache_data
def load_data() -> pd.DataFrame:
    data = pd.read_csv(DATA_PATH, parse_dates=["date", "datetime"])
    data["coffee_name"] = data["coffee_name"].astype("string").str.strip()
    data["cash_type"] = data["cash_type"].astype("string").str.strip().str.lower()
    return data


df = load_data()
date_min = df["date"].min().date()
date_max = df["date"].max().date()

st.title("Coffee Ops | Vending Machine Sales Monitor")
st.caption(
    "For the vending-machine operator: review recorded demand by date, drink, and hour "
    "to plan replenishment checks."
)
st.caption(
    f"Data period: {date_min:%b %d, %Y} – {date_max:%b %d, %Y} · "
    "Kaggle snapshot · Production refresh proposal: nightly; operator review: weekly."
)

with st.sidebar:
    st.header("Explore the records")
    selected_dates = st.date_input(
        "Transaction date range",
        value=(date_min, date_max),
        min_value=date_min,
        max_value=date_max,
    )
    drinks = sorted(df["coffee_name"].dropna().unique().tolist())
    selected_drinks = st.multiselect("Drink", drinks, default=drinks)

if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
    start_date, end_date = selected_dates
else:
    start_date = end_date = selected_dates

filtered = df.loc[
    df["date"].dt.date.between(start_date, end_date)
    & df["coffee_name"].isin(selected_drinks)
].copy()

if filtered.empty:
    st.info("No recorded transactions match these filters. This does not establish that demand was zero.")
    st.stop()

total_sales = filtered["money"].sum()
transaction_count = len(filtered)
recorded_days = filtered["date"].dt.date.nunique()
transactions_per_recorded_day = transaction_count / recorded_days

metric_columns = st.columns(3)
metric_columns[0].metric("Transaction records", f"{transaction_count:,}")
metric_columns[1].metric("Avg. records per day with records", f"{transactions_per_recorded_day:.1f}")
metric_columns[2].metric("Recorded sales", f"{total_sales:,.2f}")
st.caption("The dataset does not specify the currency; monetary values are shown in source units.")

left, right = st.columns(2)

with left:
    st.subheader("Recorded transactions by complete week")
    # Use full calendar weeks so partial weeks at the selected date boundaries
    # are not compared with complete weeks or used for the review trigger.
    selected_history = df.loc[df["coffee_name"].isin(selected_drinks)].copy()
    full_weekly = (
        selected_history.set_index("datetime")["money"]
        .resample("W-SUN")
        .size()
        .rename("Transactions")
        .to_frame()
    )
    full_weekly["Prior 8-week average"] = (
        full_weekly["Transactions"].shift(1).rolling(8, min_periods=8).mean()
    )
    full_weekly["20% below baseline"] = full_weekly["Prior 8-week average"] * 0.8

    selected_week_starts = (full_weekly.index - pd.Timedelta(days=6)).date
    complete_week_mask = (
        (selected_week_starts >= start_date)
        & (full_weekly.index.date <= end_date)
        & (selected_week_starts >= date_min)
        & (full_weekly.index.date <= date_max)
    )
    complete_weeks = full_weekly.loc[complete_week_mask]

    if complete_weeks.empty:
        st.info("Select a range containing at least one complete Sunday-ending week to view the weekly trend.")
    else:
        visible_weekly = complete_weeks.loc[
            (complete_weeks.index.date >= start_date)
            & (complete_weeks.index.date <= end_date)
        ]
        fig, ax = plt.subplots(figsize=(9, 4.2))
        visible_weekly["Transactions"].plot(
            ax=ax, color="#39786d", linewidth=2, marker="o", label="Transactions"
        )
        visible_weekly["20% below baseline"].plot(
            ax=ax, color="#bd6a49", linestyle="--", linewidth=1.5, label="Review threshold"
        )
        ax.set_xlabel("Complete week ending (Sunday)")
        ax.set_ylabel("Transaction records")
        ax.grid(axis="y", alpha=0.25)
        ax.legend(frameon=False)
        fig.tight_layout()
        st.pyplot(fig, clear_figure=True)

        latest_week = visible_weekly.iloc[-1]
        if (
            pd.notna(latest_week["Prior 8-week average"])
            and latest_week["Transactions"] <= latest_week["20% below baseline"]
        ):
            st.warning(
                "Recorded transactions for the latest complete week are at least 20% below "
                "the preceding eight-week average. Check machine uptime and data capture "
                "before changing the replenishment plan."
            )
    st.caption(
        "Proposed review trigger: a complete week at least 20% below its preceding "
        "eight-week average prompts an uptime and data-capture check. Partial weeks "
        "are excluded from this trend and trigger."
    )

with right:
    st.subheader("Recorded transactions by hour")
    hourly = filtered.assign(hour=filtered["datetime"].dt.hour).groupby("hour").size()
    hourly = hourly.reindex(range(6, 23), fill_value=0)
    fig, ax = plt.subplots(figsize=(9, 4.2))
    hourly.plot.bar(ax=ax, color="#c58a4a", width=0.8)
    ax.set_xlabel("Hour of day (24-hour clock)")
    ax.set_ylabel("Transaction records")
    ax.tick_params(axis="x", rotation=0)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    st.pyplot(fig, clear_figure=True)

st.caption(
    "Interpretation note: a date or hour with no row may reflect no recorded sale or a gap in collection. "
    "This snapshot contains no inventory or stockout records, so sales alone cannot identify lost demand."
)

