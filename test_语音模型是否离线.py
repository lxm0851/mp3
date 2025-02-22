import whisper
model = whisper.load_model("base")
result = model.transcribe("temp_playback.wav")
print(result["text"])