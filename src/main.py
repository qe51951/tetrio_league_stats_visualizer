import requests
import time
import pandas as pd
import os
from datetime import datetime, timedelta
import plotly.graph_objects as go
import sqlite3
import numpy as np


BASE_URL = "https://ch.tetr.io/api"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
headers = {
    "User-Agent": "tetr_stats_visualizer/alpha1.0 (Discord: waharu_)",
    "X-Session-ID": "20260318_toyproject_session_001",
    "Accept": "application/json"#,
    #"Accept-Encoding": "gzip, deflate, br"
}

def main(user_name, n=100):

    ## early return: when the instance of n isn't int
    if(n<=20):
        print("The number of requested recent matches should be larger than 20.")
        return
    if(isinstance(n, int)==False):
        print("The number of requested recent matches should be natural number.")
        return
    
    
    ########## Fetch User's info (to collect user's MongoID) ##########
    object_user_info = requests.get(BASE_URL+"/users/"+user_name, headers=headers)

    # exception handling
    if(object_user_info.status_code==404):
        print("No such user!\nEither you mistyped something, or the account no longer exists.")
        return
    elif(object_user_info.status_code!=200):
        print("There is an error! Status code: "+object_user_info.status_code)
        return
    
    # user_id is user's internal ID
    user_info = object_user_info.json()
    user_id = user_info['data']['_id']

    print("User Successfully Found. Now Fetching League Data...")
    time.sleep(1)


    ########## Fetch User's League Data ##########
    object_user_league_data = requests.get(BASE_URL+"/labs/leagueflow/"+user_id, headers=headers)
    user_league_data = object_user_league_data.json()
    if(user_league_data['success']==False):
        print("Fetch failed: user_data['error']")
        return
    # user_league_data['data']['points'] is User's all league data in season 2.
    tot_league_count = min(n, len(user_league_data['data']['points']))
    league_count = 0

    print(f"League Data Successfully Fetched. Now Collecting League Stats...(0/{tot_league_count})", end="")
    time.sleep(1)

    ########## Fetch User's Stats of Each League Record ##########
    start_time = user_league_data['data']['startTime']
    stat_list = {}
    stat_list['start_time'] = start_time
    stat_list_data = []

    ## database
    conn = sqlite3.connect(os.path.join(BASE_DIR, '..', 'data', 'stats_db.db'))
    cur = conn.cursor()

    cur.execute('''CREATE TABLE IF NOT EXISTS stats (
                time_offset BIGINT PRIMARY KEY,
                is_won BIT(1),
                user_tr FLOAT,
                opponent_tr FLOAT,
                apm FLOAT,
                pps FLOAT,
                vsscore FLOAT
                )''')
    conn.commit()

    ## iter
    for league_data in reversed(user_league_data['data']['points']):
        target_time_offset = league_data[0]
        cur.execute("SELECT * FROM stats WHERE time_offset = ?", (target_time_offset, ))
        row = cur.fetchone()

        if row:
            ## if there is data in database
            temp_stat = {
                'time_offset': row[0],
                'is_won': bool(row[1]),
                'user_tr': row[2],
                'opponent_tr': row[3],
                'apm': row[4],
                'pps': row[5],
                'vsscore': row[6]
            }
            print(f"\rLeague Data Successfully Loaded. Now Collecting League Stats...({league_count}/{tot_league_count})", end="")
        else: 
            ## get match data
            query_params = {
                "user": user_id,
                "gamemode": "league",
                "ts": start_time + league_data[0]
            }
            object_record_data = requests.get(BASE_URL+"/records/reverse", params=query_params, headers=headers)
            record_data = object_record_data.json()

            ## formatting data
            temp_stat = {}
            temp_stat['time_offset'] = league_data[0]
            temp_stat['is_won'] = True if (league_data[1]==1 or league_data[1]==3) else False
            for key, value in record_data['data']['extras']['league'].items():
                if(key==user_id): temp_stat['user_tr'] = value[1]['tr']
                else: temp_stat['opponent_tr'] = None if value[0] is None else value[0]['tr']
            match_user_num = -1
            if(record_data['data']['results']['leaderboard'][0]['id']==user_id): match_user_num = 0
            elif(record_data['data']['results']['leaderboard'][1]['id']==user_id): match_user_num = 1
            assert match_user_num!=-1, "Wrong Match Found"
            temp_stat['apm'] = record_data['data']['results']['leaderboard'][match_user_num]['stats']['apm']
            temp_stat['pps'] = record_data['data']['results']['leaderboard'][match_user_num]['stats']['pps']
            temp_stat['vsscore'] = record_data['data']['results']['leaderboard'][match_user_num]['stats']['vsscore']

            cur.execute('''INSERT INTO stats VALUES (?, ?, ?, ?, ?, ?, ?)''', (
                temp_stat['time_offset'],
                bool(temp_stat['is_won']),
                temp_stat['user_tr'],
                temp_stat['opponent_tr'],
                temp_stat['apm'],
                temp_stat['pps'],
                temp_stat['vsscore']
            ))
            conn.commit()
            print(f"\rLeague Data Successfully Fetched. Now Collecting League Stats...({league_count}/{tot_league_count})", end="")
            time.sleep(1)

        stat_list_data.append(temp_stat)
        ## stat_list_data = {
        ##     'time_offset': (int),
        ##     'is_won': (bool),
        ##     'user_tr': (int),
        ##     'opponent_tr': (int),
        ##     'apm': (float),
        ##     'pps': (float),
        ##     'vsscore': (float)
        ## }

        league_count += 1
        
        if(league_count >= tot_league_count): break
        
    
    conn.close()
    stat_list['data'] = stat_list_data
    print(f"\rLeague Data Successfully Loaded({tot_league_count}/{tot_league_count}). Now Fetching League info...    ")


    ######## 랭크컷 가져옴
    DATA_PATH = os.path.join(BASE_DIR, '../data/rank.csv')
    if(os.path.exists(DATA_PATH) and datetime.now()-datetime.fromtimestamp(os.path.getmtime(DATA_PATH))< timedelta(days=1)): ## should be re-factoring later
        rank_tr = pd.read_csv(DATA_PATH)
    else: 
        time.sleep(6)
        object_league_info = requests.get(BASE_URL+"/labs/league_ranks", headers=headers)
        league_info = object_league_info.json()
        rank_tr_list = []
        tier_name_list = ["x+", "x", "u", "ss", "s+", "s", "s-", "a+", "a", "a-", "b+", "b", "b-", "c+", "c", "c-", "d+", "d"]
        for tier_name in tier_name_list:
            rank_tr_list.append({"Rank": tier_name, "Tr": league_info['data']['data'][tier_name]['tr']})
        rank_tr = pd.DataFrame(rank_tr_list)
        rank_tr.to_csv(DATA_PATH, index=False, encoding='utf-8')
    rank_tr = rank_tr.set_index("Rank")
        


    ######## 데이터 처리
    ## stat_list = {
    ##     'start_time': (int),
    ##     'data': [
    ##         {
    ##         'time_offset': (int),
    ##         'is_won': (bool),
    ##         'user_tr': (string),
    ##         'opponent_tr': (string),
    ##         'apm': (float),
    ##         'pps': (float),
    ##         'vsscore': (float)
    ##         }, ...
    ##     ]
    ## }
    df = pd.DataFrame(stat_list['data'][::-1])
    df['absolute_time'] = stat_list['start_time'] + df['time_offset']
    df['time_offset_delta'] = df['time_offset'].diff().fillna(0)
    df['time_offset_delta_scaled'] = df['time_offset_delta'].apply(heuristic_scale)
    df['final_time'] = df['time_offset_delta_scaled'].cumsum()

    win_mask = df['is_won'] == True
    lose_mask = df['is_won'] == False
    df.loc[win_mask, 'win_by_opponent_avg_tr'] = (df[win_mask]['opponent_tr'].rolling(window=10, min_periods=1).mean())
    df.loc[lose_mask, 'lose_by_opponent_avg_tr'] = (df[lose_mask]['opponent_tr'].rolling(window=10, min_periods=1).mean())
    df['win_by_opponent_avg_tr'] = df['win_by_opponent_avg_tr'].ffill()
    df['lose_by_opponent_avg_tr'] = df['lose_by_opponent_avg_tr'].ffill()
    win_df = df[df['is_won']==True]
    lose_df = df[df['is_won']==False]

    fig = go.Figure()
    
    colors_rgb = pd.read_csv(os.path.join(BASE_DIR, "../data/colors.csv"))
    current_min = df['user_tr'].min() * 0.95
    current_max = df['user_tr'].max() * 1.05
    mask = set()
    for i in range(len(rank_tr)):
        top_tr = 25000 if i==0 else rank_tr.iloc[i-1]['Tr']
        bottom_tr = rank_tr.iloc[i]['Tr']
        if((not (current_min <= top_tr)) ^ (bottom_tr <= current_max)):
            mask.add(i)

    for i in mask:
        top_tr = 25000 if i==0 else rank_tr.iloc[i-1]['Tr']
        bottom_tr = rank_tr.iloc[i]['Tr']
        target_row = colors_rgb.loc[colors_rgb['Rank']==rank_tr.iloc[i].name]

        fig.add_hrect(
            y0= bottom_tr, y1= top_tr,
            fillcolor = f"rgba({target_row['R'].item()}, {target_row['G'].item()}, {target_row['B'].item()}, 1)",
            layer='below', line_width=0
        )

    ####### 시각화

    

    fig.add_trace(go.Scatter(
        x=df['final_time'], y=df['user_tr'],
        mode='lines',
        name='TR',
        line=dict(color='#00d4ff', width=3, shape='hv'),
        hovertemplate='TR: ${y:.2f}'
    ))

    fig.add_trace(go.Scatter(
        x=win_df['final_time'], y=win_df['user_tr'],
        mode='markers', name='Win',
        marker=dict(color='#50fa7b', size=8, symbol='triangle-up')
    ))

    fig.add_trace(go.Scatter(
        x=lose_df['final_time'], y=lose_df['user_tr'],
        mode='markers', name='Lose',
        marker=dict(color='#ff5555', size=8, symbol='triangle-down')
    ))

    fig.add_trace(go.Scatter(
        x=df['final_time'], y=df['win_by_opponent_avg_tr'],
        name = 'Avg Opp Tr (Win)',
        line = dict(color='#f9ff24', width=2, dash='dot', shape='linear'),
        opacity=0.6
    ))

    fig.add_trace(go.Scatter(
        x=df['final_time'], y=df['lose_by_opponent_avg_tr'],
        name = 'Avg Opp Tr (Lose)',
        line = dict(color='#c524ff', width=2, dash='dot', shape='linear'),
        opacity=0.6
    ))

    

    fig.update_layout(
        template='plotly_dark',
        title='League TR Data',
        xaxis_title = 'time',
        yaxis_title = 'TR',
        hovermode = 'x unified',
        paper_bgcolor = '#1e1e1e',
        plot_bgcolor = '#fefefe'
    )

    fig.show()

def heuristic_scale(delta):
    DAY = 86400
    WEEK = DAY * 7
    if(delta < DAY): return 1
    elif(delta < WEEK): return (delta/DAY)
    else: return (delta/DAY)**0.7

if __name__ == "__main__":
    main('sumsum2', 500)