import ccxt
from py3cw.request import Py3CW
import spot_config as config
import time
from time import gmtime, strftime
import datetime
from datetime import timezone
import pandas as pd
import pandas_ta as ta


# Setup to collect the data from Binance Exchange
binance = ccxt.binance()

# Setup to connect to 3commas
p3cw = Py3CW(
    key=config.TC_API_KEY,
    secret=config.TC_API_SECRET,
    request_options={
        'request_timeout': 20,
        'nr_of_retries': 5,
        'retry_status_codes': [500, 502, 503, 504]
    }
)


def get_bot_info():
    data = []
    bot_info = []
    first_run = True
    base_offset = 100
    offset = 0
    while len(data) == 100 or first_run:
        first_run = False
        error, data = p3cw.request(
            entity='bots',
            action='',
            payload={
                "account_id": config.TC_ACCOUNT_ID,
                "limit": base_offset,
                "offset": offset,
            }
        )
        if type(data) is not list:
            print("Data from 3Commas is not a list.")
            print(data)
            data = []
        bot_info = bot_info + data
        offset += base_offset
    return bot_info


def get_enabled_bots():
    enabled_bots = {}
    bot_list = get_bot_info()
    for bot in bot_list:
        if bot["is_enabled"] == True:
            bot_id = bot["id"]
            bot_pair = bot["pairs"][0]
            bot_strategy = bot["strategy"]
            enabled_bots[bot_pair[4:]] = bot_id, bot_strategy
    return enabled_bots


def enable_bot(bot_id):
    f = open("3c-enable-bot-ema_log.txt", "a")
    f.write(f'Enable bot ID {bot_id} at {strftime("%Y-%m-%d %H:%M:%S", gmtime())} UTC\n')
    f.close()
    error, bot_trigger = p3cw.request(
        entity = 'bots',
        action = 'enable',
        action_id = bot_id
    )   
    print(f'Bot ID {bot_id} Enabled')


def disable_bot(bot_id):
    f = open("3c-enable-bot-ema_log.txt", "a")
    f.write(f'Disable bot ID {bot_id} at {strftime("%Y-%m-%d %H:%M:%S", gmtime())} UTC\n')
    f.close()
    error, bot_trigger = p3cw.request(
        entity = 'bots',
        action = 'disable',
        action_id = bot_id
    )   
    print(f'Bot ID {bot_id} Disabled')


def close_deal(bot_id):
    f = open("3c-enable-bot-ema_log.txt", "a")
    f.write(f'Panic Close - Bot ID #{bot_id} at {strftime("%Y-%m-%d %H:%M:%S", gmtime())} UTC\n')
    f.close()
    error, deal_close = p3cw.request(
        entity = 'bots',
        action = 'panic_sell_all_deals',
        action_id = str(bot_id)
    )
    print(f'Panic Close - Bot ID #{bot_id}')


def check_trend(ma1, ma2, ma3):
    if (ma1 > ma2) & (ma2 > ma3):
        trend = 'BULL'
    elif (ma1 < ma2) & (ma2 < ma3):
        trend = 'BEAR'
    else:
        trend = 'NEUTRAL'
    return trend


##    <<<<<<<<<<<   START OF PROGRAM HERE     >>>>>>>>>>>>>>>>>


# Compute timeframe
time_frame_mins = config.TF
if time_frame_mins < 60:
    time_frame = int(time_frame_mins)
    time_frame_unit = 'm'
elif time_frame_mins >= 60:
    time_frame = int(time_frame_mins//60)
    time_frame_unit = 'h'
timeframe = str(time_frame) + time_frame_unit


ema_1 = config.EMA_1
ema_2 = config.EMA_2
ema_3 = config.EMA_3

update_stats_time = True

##    <<<<<<<<<<<   START LOOP HERE     >>>>>>>>>>>>>>>>>

while True:
    while update_stats_time:

        # Check for bot status (on/off)
        BotIsEnabled = False
        enabled_bots = get_enabled_bots()
        for key in enabled_bots:
            if str(enabled_bots[key][0]) == config.BOT_ID:
                BotIsEnabled = True
        
        # Collect the candlestick data from Binance Exchange
        candles = binance.fetch_ohlcv(config.TRADING_PAIR, timeframe)

        ##### METHOD with Pandas #####
        # Format the data and calculation of indicators
        candles = [[binance.iso8601(candle[0])] + candle[1:] for candle in candles]
        header = ['time', 'open', 'high', 'low', 'close', 'volume']
        df = pd.DataFrame(candles, columns=header)
        #df['MA20'] = df.close.rolling(20).mean()
        #df['MA50'] = df.close.rolling(50).mean()
        #df['MA100'] = df.close.rolling(100).mean()

        # EMA
        df.ta.ema(close='Close', length=ema_1, append=True)
        df.ta.ema(close='Close', length=ema_2, append=True)
        df.ta.ema(close='Close', length=ema_3, append=True)

        ema1 = df.loc[(df.shape[0]-2), 'EMA_'+str(ema_1)]
        ema2 = df.loc[(df.shape[0]-2), 'EMA_'+str(ema_2)]
        ema3 = df.loc[(df.shape[0]-2), 'EMA_'+str(ema_3)]

        # Check for BULL, BEAR or NEUTRAL case
        df['TREND'] =df.apply(lambda x: check_trend(x['EMA_'+str(ema_1)],x['EMA_'+str(ema_2)],x['EMA_'+str(ema_3)]),axis=1)

        # [Add logic EMA rising Condition?]
        """ 

            ma1Con                      = ma1 >=    ma1[1]   // create a rising condition for MA
            ma2Con                      = ma2 >=    ma2[1]
            ma3Con                      = ma3 >=    ma3[1]
            maRisingCon                 = ma1Con and ma2Con and ma3Con
            maDecreasingCon             = (not ma1Con) and (not ma2Con) and (not ma3Con)

            validLongEntry              = (case1Long or case2Long) and maRisingCon and not na(atr) // assigns the cross conditon to each entry variable. 
            validShortEntry             = (case1Short or case2Short) and maDecreasingCon and not na(atr) // "and not na(atr)" is used to prevent entries at very beginning of the backtest before ATR can render over its 14 period lookback. 
                                                                    // Stops and targets cannot calcualte in this period resulting in a broken strategy. Its reccomended to keep that with your own criteria. 
        """


        # Enable (BULL) or disable bot (else) according to trend direction
        lastCloseTrend = df.loc[(df.shape[0]-2), 'TREND']
        previousCloseTrend = df.loc[(df.shape[0]-3), 'TREND']

        # Enable bot - call function to enable
        if (lastCloseTrend == 'BULL') and (previousCloseTrend != 'BULL') and not BotIsEnabled:
            enable_bot(config.BOT_ID)

        # Disable bot - call function to disable
        elif (lastCloseTrend != 'BULL') and BotIsEnabled:
            disable_bot(config.BOT_ID)
            close_deal(config.BOT_ID)

        # End of Stats & Bot Update (Inner while loop)
        update_stats_time = False
            
        
        # Export df previous last row to JSON file
        df.loc[df.shape[0]-2].to_json(r'./BTC_Stats.json')
        # df.to_csv(r'./BTC_Dataframe.csv') # Export df to CSV file
    
    # Wait before running script again (timer)
    now = datetime.datetime.now(timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    minutes = ((now - midnight).seconds) // 60
    
    if (minutes % config.SCRIPT_FREQ) == 0 :
        time.sleep(5)
        update_stats_time = True

    time.sleep(5) # Give the CPU a break: time between to loop [sec]

