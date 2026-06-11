import os
import json
import joblib
import datetime
import numpy as np
import pandas as pd
import yfinance as yf
import tensorflow as tf
import gspread
from google.oauth2.service_account import Credentials

# --- Configuration & Artifact Loading ---
TICKERS = ['TSLA', 'GOOGL', 'NVDA', 'META']
SPREADSHEET_ID = '1rfEppBM_ZLtF9lIBVo7MW47ZSOVeVZt9U--0pEGwlr8'
ROLLING_WINDOW = 30
NUM_STD_DEV = 2

# 1. Load the time_step artifact
try:
    TIME_STEP = joblib.load('time_step.joblib')
    print(f"Loaded time_step: {TIME_STEP}")
except Exception as e:
    print(f"Using default time_step: 30. (Note: {e})")
    TIME_STEP = 30

def get_google_sheet_client():
    try:
        secret_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS")
        if not secret_json:
            raise ValueError("Secret GOOGLE_SHEETS_CREDENTIALS is empty.")
        service_account_info = json.loads(secret_json)
        credentials = Credentials.from_service_account_info(
            service_account_info, 
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        )
        return gspread.authorize(credentials)
    except Exception as e:
        raise Exception(f"Auth Error: {e}")

def run_pipeline():
    gc = get_google_sheet_client()
    sh = gc.open_by_key(SPREADSHEET_ID)
    
    # Range to capture enough history for rolling stats
    start_date = (datetime.date.today() - datetime.timedelta(days=90)).isoformat()
    end_date = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()

    for ticker in TICKERS:
        print(f"\n--- Ticker: {ticker} ---")
        try:
            # Load artifacts
            model = tf.keras.models.load_model(f'models/lstm_autoencoder_{ticker}.keras')
            scaler = joblib.load(f'scalers/minmax_scaler_{ticker}.joblib')
            
            # Fetch data
            data = yf.download(ticker, start=start_date, end=end_date, progress=False, auto_adjust=True)
            if data.empty:
                print("No data returned from yfinance.")
                continue

            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
            
            df = data.reset_index()
            df["Log_Return"] = np.log(df["Close"] / df["Close"].shift(1))
            df = df.dropna(subset=["Log_Return"])
            
            # Sequence Creation
            scaled_values = scaler.transform(df[['Log_Return']].values)
            X = [scaled_values[i-TIME_STEP:i, 0] for i in range(TIME_STEP, len(scaled_values))]
            X_array = np.array(X)
            X_reshaped = np.reshape(X_array, (X_array.shape[0], X_array.shape[1], 1))
            
            # Prediction
            reconstructed = model.predict(X_reshaped, verbose=0)
            mae_loss = np.mean(np.abs(X_reshaped - reconstructed), axis=1).flatten()
            
            # Calculation
            res = df.iloc[TIME_STEP:].copy()
            res['MAE'] = mae_loss
            res['Mean'] = res['MAE'].rolling(window=ROLLING_WINDOW, min_periods=1).mean()
            res['Std'] = res['MAE'].rolling(window=ROLLING_WINDOW, min_periods=1).std()
            res['Thresh'] = res['Mean'] + (NUM_STD_DEV * res['Std'].fillna(0))
            res['Anom'] = res['MAE'] > res['Thresh']
            
            # Prepare Row
            latest = res.iloc[-1:]
            d_str = latest['Date'].dt.strftime('%Y-%m-%d').values[0]
            row = [d_str, round(float(latest['Close'].values[0]), 2), 
                   round(float(latest['Log_Return'].values[0]), 6),
                   round(float(latest['MAE'].values[0]), 6),
                   round(float(latest['Thresh'].values[0]), 6),
                   "TRUE" if latest['Anom'].values[0] else "FALSE"]
            
            # Update Sheet
            worksheet = sh.worksheet(ticker)
            existing_dates = worksheet.col_values(1)
            
            print(f"Latest data found for date: {d_str}")
            if d_str not in existing_dates:
                worksheet.append_row(row)
                print(f"SUCCESS: Row appended to {ticker}.")
            else:
                print(f"SKIPPED: {d_str} is already in the sheet.")

        except Exception as e:
            print(f"ERROR: {e}")

if __name__ == "__main__":
    run_pipeline()
