import whisper
model = whisper.load_model("base")
result = model.transcribe("英语听力 - Lesson 1 Excuse me!.mp3")
print(result["text"])