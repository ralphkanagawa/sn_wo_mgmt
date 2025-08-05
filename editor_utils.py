from datetime import datetime, timedelta
import streamlit as st

def apply_bulk_value(df, column, value):
    df[column] = value
    return df

def generate_time_windows(start_date, start_time, count):
    base = datetime.combine(start_date, start_time)
    return [base + timedelta(minutes=27 * i) for i in range(count)]

def fill_temporal_columns(df, incs):
    full = [
        "Promised window From - Work Order",
        "Promised window To - Work Order",
        "StartTime - Bookable Resource Booking",
        "EndTime - Bookable Resource Booking",
    ]
    time_only = [
        "Time window From - Work Order",
        "Time window To - Work Order",
    ]
    for c in full:
        if c in df.columns:
            df[c] = incs
    for c in time_only:
        if c in df.columns:
            df[c] = [d.time().strftime("%H:%M") for d in incs]
    return df
