# Trade-copier-Oa2Dx
Python program to copy trades from Oanda to DxTrade

Oanda: utilizes the Oanda V20 streaming interface to receive notifications of opens & closes, uses API calls to get information (account balances, open positions).
       
DxTrade: utilizes the DxTrade API to open & close trades, get account balance, get open positions.

## Important notes:
* This is very new and raw and is currently exhibiting at least one known bug (see To Do section). It should be used only in demo/practice/paper trading.
* Requires installation of the Oanda V20 API:
  pip install oandapyV20
* Before executing Trade-copier-oa2dx you should first test dxtrade_api.py by running it standalone, it includes a small test suite in main().
* Currently handles only Market orders, ignores Limit orders etc (but TP and SL fills are handled).
* Assumes there is only one open order per symbol at a time.
* The time intervals in background_updates() are appropriate for day or swing trading, they may need to be adjusted for lower timeframes.

## To do:
* The background thread should not be started in the while loop, it will have multiple instances
* Having an occassional unexpected crash in this line, added more exception monitoring and logging
```
for trand in r.response:
```
* implement notification of reconcilation problems? trades?

## Usage:
1. Edit dxtrade_api.py to reflect your broker and account credentials - these 2 lines:
```
self.base_url = "https://dxtrade.ftmo.com/dxsca-web/"
ftmo_conn = DXT("accountnumber", "password")
```
3. Run dxtrade_api.py, it should create 3 trades, then delete 1 of them, then delete all of them, giving you a list of open positions after each activity.
4. Edit Trade-copier-oa2dx.py to reflect your Oanda and DxTrade account credentials - these lines:
```
# set this to 1 for Live or 0 for Demo
live_or_practice = 0

if live_or_practice:
    # live
    oanda_env = "live"
    oanda_account_id = "123-456-7890123-456"
    oanda_access_token = "0123456789abcdef0123456789abcdef-0123456789abcdef0123456789abcdef"
    ftmo_account_id = "123456789"
    ftmo_password = "password"
else:
    # demo
    oanda_env = "practice"
    oanda_account_id = "123-456-7890123-456"
    oanda_access_token = "0123456789abcdef0123456789abcdef-0123456789abcdef0123456789abcdef"
    ftmo_account_id = "123456789"
    ftmo_password = "*password"

```
5. Run it in demo (practice) mode, test it extensively.
