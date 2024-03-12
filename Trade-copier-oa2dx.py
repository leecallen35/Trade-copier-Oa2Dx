'''
Copy trades from Oanda to FTMO
Oanda: utilize a streaming interface to receive notifications of opens & closes,
       also use API calls to get account information, open positions.
FTMO: utilize the API to open & close trades, get balance, get open positions.

Important notes:
- Requires module dxtrade_api.py and installation of the Oanda V20 API:
  pip install oandapyV20
- Currently handles only Market orders, ignores Limit orders etc (but TP and 
  SL fills are handled).
- Assumes there is only one open order per symbol at a time.
- The time intervals in background_updates() are appropriate for day or swing trading,
  probably not suited for lower timeframes.

To do:
- Having an unexpected crash in this line, added more exception monitoring and logging
    for trand in r.response:
- implement notification of reconcilation problems? trades?

'''

import json
import time	# for sleep
import threading
import logging
from datetime import datetime, timedelta
import oandapyV20
import oandapyV20.endpoints.transactions as trans
import oandapyV20.endpoints.accounts as accounts
import oandapyV20.endpoints.positions as Positions
from dxtrade_api import DXT

# Global stuff

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

lock = threading.Lock()
open_trades = {}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[ logging.FileHandler("TradeCopier-O2D.log"), logging.StreamHandler() ]
)


# This thread is run in background, because handling streaming transactions
# ties up the main thread.
# Locks are implementedto avoid corruption of ftmo_conn and open_trades.

def background_updates( oanda_client, ftmo_conn ):
    last_ping = last_reconcile = datetime.now()
    connected = True

    while True:
        time.sleep(60)
        # ping FTMO connection every 10 minutes to keep it alive
        if datetime.now() > last_ping + timedelta( minutes=10):
            connected = True
            #logging.info("BG pinging")
            with lock: # shared ftmo_conn
                if not ftmo_conn.ping():
                    logging.info("background FTMO ping failed, re-connecting")
                    if not ftmo_conn.login():
                        logging.critical("background FTMO re-connected failed")
                        connected = False
            last_ping = datetime.now()
        # reconcile positions every hour
        if datetime.now() > last_reconcile + timedelta( minutes=60) and connected:            
            logging.debug("background reconciliation")
            with lock: # shared open_trades
                reconcile(oanda_client, ftmo_conn)
            last_reconcile = datetime.now()

def oanda_get_balance( oanda_client ):
    r = accounts.AccountSummary(oanda_account_id)
    oanda_client.request(r)
    return float( r.response['account']['balance'] )
    
def oanda_get_positions( oanda_client ):    
    r = Positions.OpenPositions(oanda_account_id)
    oanda_client.request(r)
    # returns a dict named 'positions' containing a list of positions, each position is a dict
    order_list = r.response['positions']
    # create a simplified list-of-dicts to return the results
    positions = []
    for list_item in order_list:
        symbol = list_item['instrument'].replace("_","")
        dir = 0 if int( list_item['long']['units'] ) == 0 else 1     
        positions.append({ "symbol": symbol, "side": dir })
    return positions
    
# Reconcile open trades between Oanda and FTMO:
# Look for any open positions in FTMO that are NOT in Oanda and close them
# and rebuild the open_trades dict

def reconcile( oanda_client, ftmo_conn ):
    global open_trades
    errCnt = 0
    
    # clear open_trades dict, we will rebuild it
    open_trades = {}
    
    oanda_positions = oanda_get_positions(oanda_client)
    for ftmo_position in ftmo_conn.get_positions():
        # is the FTMO position in the Oanda position list?
        found = False
        for oanda_position in oanda_positions:
            if oanda_position['symbol'] == ftmo_position['symbol'] and \
               oanda_position['side']   == ftmo_position['side']:
                found = True
                break
        if found:
            # add to open_trades{}
            open_trades[ ftmo_position['symbol'] ] = ( ftmo_position['quantity'], ftmo_position['side'], ftmo_position['positionCode'] )
        else:
            # 'orphan' FTMO trade, must close it
            logging.info("Found orphan FTMO position symbol: %s, side: %s -- closing trade", ftmo_position['symbol'], ftmo_position['side'])
            errCnt += 1
            ftmo_conn.closeOrder(currpair=ftmo_position['symbol'], lotsize=ftmo_position['quantity'], buy_or_sell=ftmo_position['side'], positionCode=ftmo_position['positionCode'])
    if errCnt > 0:
        logging.info("Reconciliation found one or more orphan trades in FTMO")
        list_open_trades()

def list_open_trades():
    global open_trades

    if len(open_trades) == 0:
        logging.info("Current open trades: (none)")
    else:
        logging.info("Current open trades:")
        for symbol in open_trades:
            ( lotSize, dir, positionCode ) = open_trades[ symbol ]
            side = "BUY" if dir == 1 else "SELL"
            logging.info("\tSymbol:%s\tSize:%s\tDir:%s\tID:%s", symbol, lotSize, side, positionCode)

def main():
    global open_trades
    
    # start thread for background updates
    x = threading.Thread(target=background_updates, args=(oanda_client, ftmo_conn), daemon=True)
    x.start()
    
    # outer loop: sometimes the trans stream crashes
    while True:

        # initialize FTMO / DxTrade connection - requests
        ftmo_conn = DXT(ftmo_account_id, ftmo_password)
        if not ftmo_conn.login():
            logging.critical("Initial login to FTMO failed, program terminated")
            quit(1)

        # initialize Oanda connection - streaming
        oanda_client = oandapyV20.API(oanda_access_token, environment=oanda_env)
        r = trans.TransactionsStream(oanda_account_id)
        oanda_client.request(r)

        # reconcile open positions between Oanda and FTMO    
        reconcile(oanda_client, ftmo_conn)
        list_open_trades()
    
        try:
            for trand in r.response:
                if trand['type'] != "ORDER_FILL":
                    continue
                if not ftmo_conn.ping():
                    logging.info("FTMO ping failed, re-connecting")
                    if not ftmo_conn.login():
                        logging.critical("lost connection to FTMO, unable to re-connect")
                        quit(2)
                
                if trand['reason'] == "MARKET_ORDER":
                    pair = trand['instrument'].replace("_","")
                    base_size = float( trand['units'] )
                    # infer dir (side) from sign of lotsize
                    if base_size > 0:
                        dir = 1
                    elif base_size < 0:
                        base_size = abs(base_size)
                        dir = 0
                    else: # size is 0
                        break
                    # factor lot size based on relative account balances of FTMO vs Oanda
                    lotSize = int( base_size * ftmo_conn.account_balance() / oanda_get_balance(oanda_client) )
                    # FTMO requires trade size be rounded to nearest 1000
                    lotSize = round( lotSize / 1000, 0 ) * 1000
                    # open trade in FTMO, save positionCode (order ID) for closing later
                    logging.info("opening: pair=%s, dir=%s, base_size=%s, lotSize=%s", pair, dir, base_size, lotSize)
                    positionCode = ftmo_conn.openOrder(currpair=pair, lotsize=lotSize, buy_or_sell=dir)
                    # add to open_trades dict
                    with lock:
                        open_trades[ pair ] = ( lotSize, dir, positionCode )
                    list_open_trades()
                elif trand['reason'] == "MARKET_ORDER_TRADE_CLOSE" or \
                     trand['reason'] == "TAKE_PROFIT_ORDER" or \
                     trand['reason'] == "STOP_LOSS_ORDER" or \
                     trand['reason'] == "MARKET_IF_TOUCHED_ORDER":
                    pair = trand['instrument'].replace("_","")
                    # lookup factored lot size in open_trades{}
                    if pair in open_trades:
                        ( lotSize, dir, positionCode ) = open_trades[ pair ]
                    else:
                        logging.error("received order close notification from Oanda but cannot find trade in open_trades{} for %s - starting reconciliation", pair)
                        with lock:
                            reconcile(oanda_client, ftmo_conn)
                        break
                    # close trade in FTMO
                    logging.info("closing: pair=%s, dir=%s, lotSize=%s", pair, dir, lotSize)
                    ftmo_conn.closeOrder(currpair=pair, lotsize=lotSize, buy_or_sell=dir, positionCode=positionCode)
                    # remove from open_trades{}
                    with lock:
                        del open_trades[ pair ]
                    list_open_trades()
                else:
                    logging.critical("Unexpected transaction - symbol: %s order type: %s reason: %s", trand['instrument'], trand['type'], trand['reason'])

        except trans.StreamTerminated as e:
            logging.error("the Oanda transaction stream terminated, restarting")
        except Exception as e:
            logging.critical("Unexpected error encountered, restarting: %e", e)

if __name__ == '__main__':
    main()
