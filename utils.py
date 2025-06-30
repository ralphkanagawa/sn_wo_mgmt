import pandas as pd

def classify_signal(v):
    if pd.isna(v):
        return None
    if -70 <= v <= -10:
        return "YES"
    if -200 <= v < -70:
        return "NO"
    return None
