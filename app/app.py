import json
import configparser
import requests
import urllib
import codecs
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import pandas
import os

'''
    WebAPIのRequetsURLを取得する
        in browser  : chromeDriver
           video_url    : 動画のURL
        out
'''
def __get_webapiurl(browser,video_url):

    # 動画へアクセス
    browser.get(video_url)

    WebDriverWait(browser, 15).until(EC.presence_of_element_located((By.ID,"chatframe"))) # チャットランが読み込まれるまで待機
    # WebAPIのRequetsURLを取得する
    url = browser.find_element_by_id("chatframe").get_attribute("src")
    return url

'''
    WebAPI実行
        in webapi_url  : youtube webapiのRequetsURL
'''
def __call_api(webapi_url,params,videoId):

    message_list = []
    chat_time_list = []
    id_list = []

    output_path = './'
    output_path = output_path + "\\" + videoId + ".csv"

    # Postmanだとuser-agent入れてないとエラーになるので一応入れとく
    payload_str = "&".join("%s=%s" % (k,v) for k,v in params.items()) # URLエンコードされるため変換
    res = requests.get("https://www.youtube.com/live_chat_replay/get_live_chat_replay",params=payload_str,headers={"user-agent":"ozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.130 Safari/537.36"}) # webapiコール
    res_json = res.json()
    for chatInfo in res_json["response"]["continuationContents"]["liveChatContinuation"]["actions"]:

        videoOffsetTimeMsec = chatInfo["replayChatItemAction"]["videoOffsetTimeMsec"] # チャット投稿時間(msec)
        print(videoOffsetTimeMsec)

        chatItemAction = ""
        if "addLiveChatTickerItemAction" in chatInfo["replayChatItemAction"]["actions"][0]:
            chatItemAction = "addLiveChatTickerItemAction"
        elif "addChatItemAction" in chatInfo["replayChatItemAction"]["actions"][0]:
            chatItemAction = "addChatItemAction"

        if "liveChatViewerEngagementMessageRenderer" in chatInfo["replayChatItemAction"]["actions"][0][chatItemAction]["item"]:
            # 該当キーが合った場合はシステムメッセージのためスキップ
            continue

        # チャット文字列
        MessageRenderer = ""
        if "liveChatTextMessageRenderer" in chatInfo["replayChatItemAction"]["actions"][0][chatItemAction]["item"]:
            # 通常チャット
            MessageRenderer = "liveChatTextMessageRenderer"
        elif "liveChatPaidMessageRenderer" in chatInfo["replayChatItemAction"]["actions"][0][chatItemAction]["item"]:
            # スパチャ文字 + 絵文字？ # 無言スパチャはこの後のmessageキーがないため注意
            MessageRenderer = "liveChatPaidMessageRenderer"
            continue
        elif "liveChatPaidStickerRenderer" in chatInfo["replayChatItemAction"]["actions"][0][chatItemAction]["item"]:
            # スパチャ絵文字のみ
            continue
        elif "liveChatTickerPaidStickerItemRenderer" in chatInfo["replayChatItemAction"]["actions"][0][chatItemAction]["item"]:
            # スパチャ絵文字のみの額
            continue
        elif "liveChatTickerPaidMessageItemRenderer" in chatInfo["replayChatItemAction"]["actions"][0][chatItemAction]["item"]:
            # スパチャの額
            # こっちは一旦いらない
            continue
        elif "liveChatMembershipItemRenderer" in chatInfo["replayChatItemAction"]["actions"][0][chatItemAction]["item"]:
            # メンバーシップ
            # 今回はカウントしない
            continue
        elif "liveChatTickerSponsorItemRenderer" in chatInfo["replayChatItemAction"]["actions"][0][chatItemAction]["item"]:
            # メンバーシップ
            # 今回はカウントしない
            continue
        elif "liveChatPlaceholderItemRenderer" in chatInfo["replayChatItemAction"]["actions"][0][chatItemAction]["item"]:
            # 多分コメント撤回したやつ
            continue
        id = chatInfo["replayChatItemAction"]["actions"][0][chatItemAction]["item"][MessageRenderer]["id"]
        print(id)

        chat_strs = chatInfo["replayChatItemAction"]["actions"][0][chatItemAction]["item"][MessageRenderer]["message"]["runs"]
        chat_time = chatInfo["replayChatItemAction"]["actions"][0][chatItemAction]["item"][MessageRenderer]["timestampText"]["simpleText"]
        print(chat_time)

        # idの重複チェック
        if os.path.exists(output_path):
            if __check_id(output_path,id):
                # 重複してたら次
                continue

        # リストで分かれてる場合があるため回す。
        message = ""
        for chat_str in chat_strs:
            if "emoji" in chat_str:
                # 絵文字だった場合
                message += "emoji"
            if "text" in chat_str:
                message += chat_str["text"]

        message_list.append(message)
        chat_time_list.append(chat_time)
        id_list.append(id)
        print(message)

    # 時間が同じだったら終了
    if videoOffsetTimeMsec == params["playerOffsetMs"]:
        return

    # 最後のoffsetを使用してAPI呼び出し
    params = {
        "commandMetadata" : params["commandMetadata"],
        "continuation" : params["continuation"],
        "playerOffsetMs" : videoOffsetTimeMsec,
        "hidden" : params["hidden"],
        "pbj" : params["pbj"]
    }

    # 保存して再帰
    __save_file(message_list,chat_time_list,id_list,output_path)

    __call_api(webapi_url,params,videoId)

def __check_id(output_path,id):
    is_id = False
    # idの重複チェック
    with codecs.open(output_path,'r',encoding='cp932',errors="ignore") as csv_file:
        read_csv = pandas.read_csv(csv_file)
        if id in read_csv["id"].values:
            is_id = True
    return is_id

'''
    csvに保存
'''
def __save_file(message_list,chat_time_list,id_list,output_path):
    # csvに出力
    df = pandas.DataFrame({
        "id":id_list,
        "chatTime":chat_time_list,
        "chatMessage":message_list
    })

    # csvファイルがあれば上書きなければ新規作成
    if os.path.exists(output_path):
        # csvのパス、エンコード、書き込み方法（w：上書き, a：追記）,header= falseにすることでカラムは無視される
        with codecs.open(output_path,'a',encoding='cp932',errors="ignore") as csv_file:
            # 既にcsvにidが存在すればListのデータは削除
            df.to_csv(csv_file,header=False)
    else:
        with codecs.open(output_path,'w',encoding='cp932',errors="ignore") as csv_file:
            df.to_csv(csv_file)

if __name__ == "__main__":
    webdriver_path = '/usr/lib/chromium/chromedriver'

    options =  webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--allow-insecure-localhost")
    browser = webdriver.Chrome(executable_path=webdriver_path,options=options)

    video_url = input("YouTubeの動画IDを入力する\n")

    start = time.time()

    videoId = video_url.split("?")[1].split("=")[1]

    webapi_url = __get_webapiurl(browser,video_url)

    browser.quit()

    # 初期呼び出し用
    params = {
        "commandMetadata": "objectObject",
        "continuation": webapi_url.split("?")[1].split("=")[1],
        "playerOffsetMs":"0",
        "hidden": False,
        "pbj":"1"
        }
    __call_api(webapi_url,params,videoId)

    elapsed_time = time.time() - start
    print ("elapsed_time:{0}".format(elapsed_time) + "[sec]")
