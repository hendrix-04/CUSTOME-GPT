from fastapi import FastAPI
import yt_dlp
import re
import os
import time
import azure.cognitiveservices.speech as speechsdk
from dotenv import load_dotenv

load_dotenv()

AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY")
AZURE_REGION = os.getenv("AZURE_REGION")

app = FastAPI()


@app.get("/")
def root():
    return {"status": "API running"}


# ---------------------------
# Extract video ID
# ---------------------------
def extract_video_id(url):
    pattern = r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})"
    match = re.search(pattern, url)

    if match:
        return match.group(1)

    return None


# ---------------------------
# Fetch metadata
# ---------------------------
def get_metadata(url):

    try:
        ydl_opts = {"quiet": True}

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        return {
            "title": info.get("title"),
            "description": info.get("description"),
            "channel": info.get("uploader"),
            "upload_date": info.get("upload_date"),
            "view_count": info.get("view_count"),
            "duration": info.get("duration"),
            "video_url": info.get("webpage_url"),
        }

    except Exception as e:
        return {"error": str(e)}


# ---------------------------
# Download YouTube audio
# ---------------------------
def download_audio(url):

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": "audio.%(ext)s",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "wav",
            "preferredquality": "192"
        }],
        "quiet": True
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    return "audio.wav"


# ---------------------------
# Azure Speech-to-Text
# ---------------------------
def transcribe_audio(audio_file):

    speech_config = speechsdk.SpeechConfig(
        subscription=AZURE_SPEECH_KEY,
        region=AZURE_REGION
    )

    speech_config.speech_recognition_language = "hi-IN"

    audio_config = speechsdk.AudioConfig(filename=audio_file)

    speech_recognizer = speechsdk.SpeechRecognizer(
        speech_config=speech_config,
        audio_config=audio_config
    )

    transcript_parts = []
    done = False

    def recognized(evt):

        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:

            text = evt.result.text

            if text.strip():
                transcript_parts.append(text)

    def stop(evt):
        nonlocal done
        done = True

    speech_recognizer.recognized.connect(recognized)
    speech_recognizer.session_stopped.connect(stop)
    speech_recognizer.canceled.connect(stop)

    speech_recognizer.start_continuous_recognition()

    while not done:
        time.sleep(1)

    speech_recognizer.stop_continuous_recognition()

    return " ".join(transcript_parts)


# ---------------------------
# API Endpoint
# ---------------------------
@app.get("/youtube")
def youtube_data(url: str):

    video_id = extract_video_id(url)

    if not video_id:
        return {"error": "Invalid YouTube URL"}

    metadata = get_metadata(url)

    try:

        audio_file = download_audio(url)

        transcript = transcribe_audio(audio_file)

        if os.path.exists(audio_file):
            os.remove(audio_file)

    except Exception as e:

        return {
            "metadata": metadata,
            "error": str(e)
        }

    return {
        "metadata": metadata,
        "transcript": transcript
    }