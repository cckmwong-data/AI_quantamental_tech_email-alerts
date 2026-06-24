import os
import json
import yfinance as yf
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# 1. AUTHENTICATION (Replaces Colab auth)
# This looks for the 'GOOGLE_SHEETS_CREDENTIALS' secret you set up in GitHub
scopes = ["https://www.googleapis.com/auth/spreadsheets"]
secret_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS")

if not secret_json:
    raise ValueError("GOOGLE_SHEETS_CREDENTIALS secret not found. Check your GitHub Settings!")

creds_dict = json.loads(secret_json)
creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
gc = gspread.authorize(creds)

# 2. OPEN SPREADSHEET
# Using your specific Spreadsheet ID
spreadsheet_id = '1IJh9E22UNFZ8soiNZrhilQfiimO7nVIzLiVLNZLRz6M'
sh = gc.open_by_key(spreadsheet_id)

tickers = ["TSLA", "NVDA", "META", "GOOGL"]

def get_financials(ticker_list):
    inc_list, bal_list, cf_list, analysts_list = [], [], [], []
    for ticker in ticker_list:
        t = yf.Ticker(ticker)

        # Helper to process and melt data
        def process(df, name):
            if isinstance(df, pd.DataFrame) and not df.empty:
                df = df.reset_index().melt(id_vars="index", var_name="Period", value_name="Value").rename(columns={"index": "Account"})
                df["Ticker"] = ticker
                return df
            return pd.DataFrame()

        # 1. Core Financial DataFrames
        inc_list.append(process(t.financials, "Income"))
        bal_list.append(process(t.balance_sheet, "Balance"))
        cf_list.append(process(t.cashflow, "CashFlow"))
        
        # 2. Convert Analyst Target Dictionary to a structured DataFrame
        targets_dict = t.analyst_price_targets
        if targets_dict:
            # Structuring the dict to match a melted DataFrame format
            target_df = pd.DataFrame(list(targets_dict.items()), columns=["Account", "Value"])
            target_df["Ticker"] = ticker
            # Rearrange columns to perfectly match the layout of income/balance/cf lists
            target_df = target_df[["Account", "Value", "Ticker"]]
            analysts_list.append(target_df)

    return pd.concat(inc_list), pd.concat(bal_list), pd.concat(cf_list), pd.concat(analysts_list)

# 3. Fetch Data
income_df, balance_df, cashflow_df, analysts_df = get_financials(tickers)

# 4. Write to Google Sheets
def update_sheet(df, sheet_name):
    worksheet = sh.worksheet(sheet_name)
    worksheet.clear()
    # Adding header and values
    worksheet.update([df.columns.values.tolist()] + df.astype(str).values.tolist())

update_sheet(income_df, "Income Statement")
update_sheet(balance_df, "Balance Sheet")
update_sheet(cashflow_df, "Cash Flow")
update_sheet(analysts_df, "Analysts")
