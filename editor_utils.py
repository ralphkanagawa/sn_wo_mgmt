from datetime import datetime, timedelta
import streamlit as st

def apply_bulk_value(df, column, value):
    df[column] = value
    return df

def generate_time_windows(start_date, start_time, count):
    base = datetime.combine(start_date, start_time)
    return [base + timedelta(minutes=27 * i) for i in range(count)]

def fill_temporal_columns(df, incs):
    full_from = [
        "Promised window From - Work Order",
        "StartTime - Bookable Resource Booking",
    ]
    full_to = [
        "Promised window To - Work Order",
        "EndTime - Bookable Resource Booking",
    ]
    time_from = ["Time window From - Work Order"]
    time_to = ["Time window To - Work Order"]

    for c in full_from:
        if c in df.columns:
            df[c] = [d.strftime("%d/%m/%Y %I:%M %p") for d in incs]

    for c in full_to:
        if c in df.columns:
            df[c] = [(d + timedelta(minutes=1)).strftime("%d/%m/%Y %I:%M %p") for d in incs]

    for c in time_from:
        if c in df.columns:
            df[c] = [d.strftime("%I:%M %p") for d in incs]

    for c in time_to:
        if c in df.columns:
            df[c] = [(d + timedelta(minutes=1)).strftime("%I:%M %p") for d in incs]

    return df
