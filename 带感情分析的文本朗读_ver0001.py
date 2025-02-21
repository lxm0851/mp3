import pyttsx3  # 做不到
from textblob import TextBlob

engine = pyttsx3.init()

text = "这段文字非常感人，充满了深刻的情感。"
blob = TextBlob(text)
sentiment = blob.sentiment

# 根据情感极性调整语速
if sentiment.polarity > 0:
    rate = 150
else:
    rate = 100

engine.setProperty('rate', rate)

engine.say(text)
engine.runAndWait()