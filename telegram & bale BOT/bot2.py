import os
import re
import time
import logging
import subprocess
import requests
import yt_dlp
import imageio_ffmpeg

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = ""
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
PROXIES = None
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def telegram_request(method: str, params: dict = None, files: dict = None):
    url = f"{API_URL}/{method}"
    try:
        response = requests.post(url, data=params, files=files, proxies=PROXIES, timeout=120)
        return response.json()
    except Exception as e:
        logger.error(f"Network error in {method}: {e}")
        return None

def clean_url(raw_text: str) -> str:
    match = re.search(r"https?://[^\s]+", raw_text)
    if not match:
        return None
    url = match.group(0)
    if "?" in url:
        url = url.split("?")[0]
    return url

def extract_audio_from_video(video_path: str, chat_id: int):
    """استخراج مستقیم و سبک صدا به کمک ffmpeg بدون فشار به رم"""
    audio_path = os.path.join(DOWNLOAD_DIR, f"{chat_id}_{int(time.time())}_music.mp3")
    try:
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [
            ffmpeg_exe,
            "-y",
            "-i",
            video_path,
            "-vn",
            "-acodec",
            "libmp3lame",
            "-q:a",
            "3",
            audio_path,
        ]
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if res.returncode == 0 and os.path.exists(audio_path):
            return audio_path
        else:
            logger.error(f"FFmpeg failed: {res.stderr.decode('utf-8', errors='ignore')[:150]}")
    except Exception as e:
        logger.error(f"Audio extraction error: {e}")
    return None


def download_from_aparat(url: str, chat_id: int):
    match = re.search(r"/v/([a-zA-Z0-9]+)", url)
    if not match:
        return None
    video_hash = match.group(1)

    api_endpoint = f"https://www.aparat.com/api/fa/v1/video/video/show/videohash/{video_hash}"
    res = requests.get(api_endpoint, timeout=15)
    if res.status_code != 200:
        return None

    data = res.json()
    download_links = data.get("data", {}).get("attributes", {}).get("file_link_all", [])
    if not download_links:
        return None

    target_link = download_links[-1].get("urls", [None])[0]
    if not target_link:
        return None

    timestamp = int(time.time())
    video_path = os.path.join(DOWNLOAD_DIR, f"{chat_id}_{timestamp}.mp4")

    r = requests.get(target_link, stream=True, timeout=90)
    with open(video_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)

    return video_path


def download_media(url: str, chat_id: int):
    timestamp = int(time.time())
    video_path = os.path.join(DOWNLOAD_DIR, f"{chat_id}_{timestamp}.mp4")

    if "aparat.com" in url:
        direct_video = download_from_aparat(url, chat_id)
        if direct_video:
            video_path = direct_video
    else:
        ydl_opts = {
            "format": "best",
            "outtmpl": video_path,
            "quiet": True,
            "no_warnings": True,
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

    audio_path = None
    if os.path.exists(video_path):
        audio_path = extract_audio_from_video(video_path, chat_id)

    return audio_path, video_path


def send_message(chat_id: int, text: str):
    return telegram_request("sendMessage", {"chat_id": chat_id, "text": text})


def send_audio(chat_id: int, file_path: str, caption: str = ""):
    with open(file_path, "rb") as f:
        return telegram_request(
            "sendAudio",
            {"chat_id": chat_id, "caption": caption},
            files={"audio": f},
        )


def send_video(chat_id: int, file_path: str, caption: str = ""):
    with open(file_path, "rb") as f:
        return telegram_request(
            "sendVideo",
            {"chat_id": chat_id, "caption": caption},
            files={"video": f},
        )


def process_update(update: dict):
    message = update.get("message")
    if not message:
        return

    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")

    if not chat_id or not text:
        return

    if text.startswith("/start"):
        send_message(
            chat_id,
            "سلام! 👋\nلینک ویدیو را ارسال کنید تا فایل صوتی (موزیک) و ویدیو را براتون استخراج کنم.",
        )
        return

    url = clean_url(text)
    if not url:
        send_message(chat_id, "لطفاً یک لینک معتبر ارسال کنید.")
        return

    send_message(chat_id, "در حال استخراج موزیک و دانلود ویدیو... لطفاً کمی صبر کنید ⏳")

    audio_file = None
    video_file = None

    try:
        audio_file, video_file = download_media(url, chat_id)

        
        if audio_file and os.path.exists(audio_file):
            send_audio(chat_id, audio_file, caption="🎵 فایل صوتی (موزیک)")

        if video_file and os.path.exists(video_file):
            send_video(chat_id, video_file, caption="🎬 ویدیوی کامل")

    except Exception as e:
        logger.error(f"Error processing link: {e}")
        send_message(chat_id, f"خطا در پردازش: {str(e)[:150]}")

    finally:
        if audio_file and os.path.exists(audio_file):
            try:
                os.remove(audio_file)
            except:
                pass
        if video_file and os.path.exists(video_file):
            try:
                os.remove(video_file)
            except:
                pass


def main():
    logger.info("Bot starting polling on Telegram...")

    try:
        telegram_request("deleteWebhook", {"drop_pending_updates": True})
    except Exception as e:
        logger.warning(f"deleteWebhook warning: {e}")

    offset = None

    while True:
        try:
            params = {"timeout": 20}
            if offset is not None:
                params["offset"] = offset

            res = telegram_request("getUpdates", params)

            if res and res.get("ok"):
                updates = res.get("result", [])
                for u in updates:
                    offset = u.get("update_id") + 1
                    logger.info(f"Incoming Telegram Update from {u.get('message', {}).get('chat', {}).get('id')}")
                    process_update(u)
            else:
                time.sleep(2)
        except Exception as err:
            logger.error(f"Polling loop error: {err}")
            time.sleep(3)


if __name__ == "__main__":
    main()