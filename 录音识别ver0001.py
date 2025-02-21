from aip import AipSpeech
import speech_recognition as sr
import pyaudio
import wave
import numpy as np
import time
import whisper

# 你的百度API密钥
APP_ID = '你的APP_ID'
API_KEY = '你的API_KEY'
SECRET_KEY = '你的SECRET_KEY'

client = AipSpeech(APP_ID, API_KEY, SECRET_KEY)

def check_microphone():
    """检查麦克风设备"""
    p = pyaudio.PyAudio()
    device_count = p.get_device_count()
    print("\n=== 可用麦克风设备 ===")
    for i in range(device_count):
        device_info = p.get_device_info_by_index(i)
        if device_info['maxInputChannels'] > 0:  # 仅显示输入设备
            print(f"设备 {i}: {device_info['name']}")
    p.terminate()

def monitor_audio_level(stream, chunk=1024, threshold=1000):
    """实时监测音量"""
    data = stream.read(chunk)
    audio_data = np.frombuffer(data, dtype=np.int16)
    volume = np.abs(audio_data).mean()
    return volume > threshold

def recognize_audio():
    try:
        check_microphone()
        
        # 录音参数
        CHUNK = 1024
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 16000
        
        # 加载whisper模型
        print("正在加载Whisper模型...")
        model = whisper.load_model("base")
        print("模型加载完成！")
        
        p = pyaudio.PyAudio()
        stream = p.open(format=FORMAT,
                       channels=CHANNELS,
                       rate=RATE,
                       input=True,
                       frames_per_buffer=CHUNK)
        
        print("\n=== 语音识别系统启动 ===")
        print("正在监听麦克风输入...")
        
        while True:
            if monitor_audio_level(stream):
                print("检测到声音输入!")
                frames = []
                
                # 开始录音
                print("正在录音...")
                for i in range(0, int(RATE / CHUNK * 5)):  # 录制5秒
                    data = stream.read(CHUNK)
                    frames.append(data)
                    if i % 10 == 0:
                        volume = np.frombuffer(data, dtype=np.int16).mean()
                        print(f"当前音量: {'*' * int(volume/500)}")
                
                print("\n录音完成！")
                
                # 保存录音文件
                audio_file = "test.wav"
                wf = wave.open(audio_file, 'wb')
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(p.get_sample_size(FORMAT))
                wf.setframerate(RATE)
                wf.writeframes(b''.join(frames))
                wf.close()
                
                print("正在识别语音...")
                # 使用whisper进行识别
                try:
                    result = model.transcribe(audio_file)
                    recognized_text = result["text"].strip()
                    print("\n识别结果:")
                    print("-" * 30)
                    print(recognized_text)
                    print("-" * 30)
                except Exception as e:
                    print(f"识别失败: {str(e)}")
                
                print("\n等待下一次输入...")
            
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("\n程序已退出")
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()

if __name__ == "__main__":
    recognize_audio()