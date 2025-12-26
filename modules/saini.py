import os
import re
import time
import mmap
import datetime
import aiohttp
import aiofiles
import asyncio
import logging
import requests
import tgcrypto
import subprocess
import concurrent.futures
from math import ceil
from utils import progress_bar
from pyrogram import Client, filters
from pyrogram.types import Message
from io import BytesIO
from pathlib import Path  
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from base64 import b64decode

def duration(filename):
    if not Path(filename).exists():
        print(f"❌ File not found for duration: {filename}")
        return 0.0

    try:
        result = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of",
            "default=noprint_wrappers=1:nokey=1", filename
        ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

        output = result.stdout.decode().strip()
        return float(output)
    except Exception as e:
        print(f"❌ Failed to get duration for {filename}: {e}")
        return 0.0

def get_mps_and_keys(api_url):
    response = requests.get(api_url)
    response_json = response.json()
    mpd = response_json.get('MPD')
    keys = response_json.get('KEYS')
    return mpd, keys
   
def exec(cmd):
        process = subprocess.run(cmd, stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        output = process.stdout.decode()
        print(output)
        return output
        #err = process.stdout.decode()
def pull_run(work, cmds):
    with concurrent.futures.ThreadPoolExecutor(max_workers=work) as executor:
        print("Waiting for tasks to complete")
        fut = executor.map(exec,cmds)
async def aio(url,name):
    k = f'{name}.pdf'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                f = await aiofiles.open(k, mode='wb')
                await f.write(await resp.read())
                await f.close()
    return k


async def download(url,name):
    ka = f'{name}.pdf'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                f = await aiofiles.open(ka, mode='wb')
                await f.write(await resp.read())
                await f.close()
    return ka

async def pdf_download(url, file_name, chunk_size=1024 * 10):
    if os.path.exists(file_name):
        os.remove(file_name)
    r = requests.get(url, allow_redirects=True, stream=True)
    with open(file_name, 'wb') as fd:
        for chunk in r.iter_content(chunk_size=chunk_size):
            if chunk:
                fd.write(chunk)
    return file_name   
   

def parse_vid_info(info):
    info = info.strip()
    info = info.split("\n")
    new_info = []
    temp = []
    for i in info:
        i = str(i)
        if "[" not in i and '---' not in i:
            while "  " in i:
                i = i.replace("  ", " ")
            i.strip()
            i = i.split("|")[0].split(" ",2)
            try:
                if "RESOLUTION" not in i[2] and i[2] not in temp and "audio" not in i[2]:
                    temp.append(i[2])
                    new_info.append((i[0], i[2]))
            except:
                pass
    return new_info


def vid_info(info):
    info = info.strip()
    info = info.split("\n")
    new_info = dict()
    temp = []
    for i in info:
        i = str(i)
        if "[" not in i and '---' not in i:
            while "  " in i:
                i = i.replace("  ", " ")
            i.strip()
            i = i.split("|")[0].split(" ",3)
            try:
                if "RESOLUTION" not in i[2] and i[2] not in temp and "audio" not in i[2]:
                    temp.append(i[2])
                    
                    # temp.update(f'{i[2]}')
                    # new_info.append((i[2], i[0]))
                    #  mp4,mkv etc ==== f"({i[1]})" 
                    
                    new_info.update({f'{i[2]}':f'{i[0]}'})

            except:
                pass
    return new_info


import os
import subprocess
from pathlib import Path

async def decrypt_and_merge_video(mpd_url, keys_string, output_path, output_name, quality="720"):
    try:
        output_path = Path(output_path)
        output_path.mkdir(parents=True, exist_ok=True)

        # Step 1: Download with yt-dlp
        cmd1 = f'yt-dlp -f "bv[height<={quality}]+ba/b" -o "{output_path}/file.%(ext)s" --allow-unplayable-formats --no-check-certificate --external-downloader aria2c "{mpd_url}"'
        print(f"▶️ Downloading: {cmd1}")
        subprocess.run(cmd1, shell=True)

        # Step 2: Detect downloaded files
        video_file = None
        audio_file = None
        for f in output_path.iterdir():
            if f.suffix in [".mp4", ".webm"] and not video_file:
                video_file = f
            elif f.suffix in [".m4a", ".webm"] and not audio_file:
                audio_file = f

        if not video_file or not audio_file:
            raise FileNotFoundError("❌ Decryption failed: video or audio file not found.")

        # Step 3: Decrypt
        decrypted_video = output_path / "video.mp4"
        decrypted_audio = output_path / "audio.m4a"

        subprocess.run(f'mp4decrypt {keys_string} "{video_file}" "{decrypted_video}"', shell=True)
        subprocess.run(f'mp4decrypt {keys_string} "{audio_file}" "{decrypted_audio}"', shell=True)

        video_file.unlink(missing_ok=True)
        audio_file.unlink(missing_ok=True)

        # Step 4: Merge
        final_file = output_path / f"{output_name}.mp4"
        subprocess.run(f'ffmpeg -y -i "{decrypted_video}" -i "{decrypted_audio}" -c copy "{final_file}"', shell=True)

        decrypted_video.unlink(missing_ok=True)
        decrypted_audio.unlink(missing_ok=True)

        if not final_file.exists():
            raise FileNotFoundError("❌ Merged video file not found.")

        print(f"✅ Final video ready: {final_file}")
        return str(final_file)

    except Exception as e:
        print(f"🔥 Error in decrypt_and_merge_video: {e}")
        return None

async def run(cmd):
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)

    stdout, stderr = await proc.communicate()

    print(f'[{cmd!r} exited with {proc.returncode}]')
    if proc.returncode == 1:
        return False
    if stdout:
        return f'[stdout]\n{stdout.decode()}'
    if stderr:
        return f'[stderr]\n{stderr.decode()}'

    

def old_download(url, file_name, chunk_size = 1024 * 10):
    if os.path.exists(file_name):
        os.remove(file_name)
    r = requests.get(url, allow_redirects=True, stream=True)
    with open(file_name, 'wb') as fd:
        for chunk in r.iter_content(chunk_size=chunk_size):
            if chunk:
                fd.write(chunk)
    return file_name

# appx zip ke liye 
# helper.py
import os
import requests
import zipfile
import subprocess
import tempfile
import shutil

FIXED_REFERER = "https://player.akamai.net.in/"

def process_zip_to_video(url, name):
    temp_dir = tempfile.mkdtemp(prefix="zip_")

    zip_path = os.path.join(temp_dir, "file.zip")
    extract_dir = os.path.join(temp_dir, "extract")
    output_path = os.path.join(temp_dir, f"{name}.mp4")

    headers = {
        "User-Agent": "Mozilla/5.0 (Android)",
        "Referer": FIXED_REFERER,
        "Range": "bytes=0-"
    }

    # 1️⃣ ZIP DOWNLOAD (FIXED REFERER)
    with requests.get(url, headers=headers, stream=True, timeout=20) as r:
        r.raise_for_status()
        with open(zip_path, "wb") as f:
            for chunk in r.iter_content(1024 * 1024):
                if chunk:
                    f.write(chunk)

    # 2️⃣ EXTRACT ZIP
    os.makedirs(extract_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(extract_dir)

    # 3️⃣ FIND m3u8
    m3u8_path = None
    for root, _, files in os.walk(extract_dir):
        for f in files:
            if f.endswith(".m3u8"):
                m3u8_path = os.path.join(root, f)
                break

    if not m3u8_path:
        shutil.rmtree(temp_dir)
        raise Exception("❌ m3u8 file nahi mili")

    # 4️⃣ m3u8 → MP4 (same referer ffmpeg me bhi)
    cmd = [
        "ffmpeg",
        "-y",
        "-headers", f"Referer: {FIXED_REFERER}\r\n",
        "-allowed_extensions", "ALL",
        "-i", m3u8_path,
        "-c", "copy",
        output_path
    ]

    subprocess.run(cmd)

    return output_path, temp_dir

import os, requests, zipfile, subprocess

import zipfile

def extract_zip(zip_path: str) -> str:
    extract_dir = zip_path.replace(".zip", "")
    os.makedirs(extract_dir, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(extract_dir)

    return extract_dir


import subprocess

def merge_ts_files(folder: str, output: str):
    ts_files = sorted(
        f for f in os.listdir(folder)
        if f.endswith((".ts", ".tse"))
    )

    list_file = os.path.join(folder, "list.txt")
    with open(list_file, "w") as f:
        for ts in ts_files:
            f.write(f"file '{os.path.join(folder, ts)}'\n")

    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_file,
        "-c", "copy",
        output
    ], check=True)

    return output


def download_drago_mkv(url: str, filename: str, ext: str) -> str | None:
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 13)",
        "Referer": "https://akstechnicalclasses.classx.co.in/",
        "Origin": "https://akstechnicalclasses.classx.co.in",
        "Accept": "*/*",
        "Connection": "keep-alive"
    }

    os.makedirs("downloads", exist_ok=True)
    file_path = f"downloads/{filename}.{ext}"

    session = create_session()
    downloaded = 0

    if os.path.exists(file_path):
        downloaded = os.path.getsize(file_path)
        headers["Range"] = f"bytes={downloaded}-"

    try:
        with session.get(url, headers=headers, stream=True, timeout=(10, 180)) as r:
            if r.status_code not in (200, 206):
                print(f"❌ Bad status: {r.status_code}")
                return None

            total = int(r.headers.get("content-length", 0)) + downloaded
            chunk_size = 256 * 1024

            with open(file_path, "ab") as f, tqdm(
                total=total,
                initial=downloaded,
                unit="B",
                unit_scale=True,
                desc=filename,
                ncols=80
            ) as bar:
                for chunk in r.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        bar.update(len(chunk))

        return file_path

    except Exception as e:
        print(f"⚠️ Download interrupted (resume enabled): {e}")
        return file_path if os.path.exists(file_path) else None

def download_drago_mkv(url: str, name: str) -> str | None:

    # 🔹 resolve redirect
    r = requests.get(url, allow_redirects=True, timeout=15)
    final_url = r.url

    # 🔹 ZIP case
    if final_url.endswith(".zip"):
        zip_path = download_raw_file(final_url, name, "zip")
        folder = extract_zip(zip_path)
        return merge_ts_files(folder, f"downloads/{name}.mp4")

    # 🔹 MKV (encrypted) case
    else:
        return download_raw_file(final_url, name, "mkv")
    
def human_readable_size(size, decimal_places=2):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
        if size < 1024.0 or unit == 'PB':
            break
        size /= 1024.0
    return f"{size:.{decimal_places}f} {unit}"


def time_name():
    date = datetime.date.today()
    now = datetime.datetime.now()
    current_time = now.strftime("%H%M%S")
    return f"{date} {current_time}.mp4"

import os, re, asyncio, aiohttp
from urllib.parse import urljoin

async def fetch_segment(session, seg_url, headers):
    async with session.get(seg_url, headers=headers, timeout=30) as resp:
        resp.raise_for_status()
        return await resp.read()

import aiohttp
import asyncio
import os
from urllib.parse import urljoin

async def fetch_segment(session, seg_url, f):
    async with session.get(seg_url) as resp:
        resp.raise_for_status()
        while True:
            chunk = await resp.content.read(1024*1024)
            if not chunk:
                break
            f.write(chunk)

async def download_m3u8_async(url: str, filename: str):
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 13)",
        "Referer": "https://player.akamai.net.in/",
        "Origin": "https://player.akamai.net.in",
        "Accept": "*/*"
    }
    os.makedirs("downloads", exist_ok=True)
    final_file = f"downloads/{filename}.mp4"

    async with aiohttp.ClientSession(headers=headers) as session:
        r = await session.get(url)
        text = await r.text()
        playlist_lines = text.splitlines()
        segments = [urljoin(url, line) for line in playlist_lines if line and not line.startswith("#")]

        if not segments:
            print("❌ No segments found!")
            return None

        print(f"🚀 Downloading {len(segments)} segments for {filename}...")

        with open(final_file, "wb") as f:
            tasks = [fetch_segment(session, seg_url, f) for seg_url in segments]
            await asyncio.gather(*tasks)

        print(f"\n✅ Full video downloaded: {final_file}")
        return final_file

# Run
# asyncio.run(download_m3u8_async("your_m3u8_url", "video_name"))
import os
import asyncio
import subprocess
import logging

async def download_video(url, cmd, name):
    if "transcoded" in url.lower():
        print(f"⚡ Transcoded URL detected → using download_m3u8 for {name}")
        return download_m3u8(url, name)
    
    download_cmd = f'{cmd} -R 25 --fragment-retries 25 --external-downloader aria2c --downloader-args "aria2c: -x 16 -j 32"'
    global failed_counter
    print(download_cmd)
    logging.info(download_cmd)

    k = subprocess.run(download_cmd, shell=True)

    if "visionias" in cmd and k.returncode != 0 and failed_counter <= 10:
        failed_counter += 1
        await asyncio.sleep(5)
        return await download_video(url, cmd, name)

    failed_counter = 0

    try:
        if os.path.isfile(name):
            return name
        elif os.path.isfile(f"{name}.webm"):
            return f"{name}.webm"

        base = name.split(".")[0]

        if os.path.isfile(f"{base}.mkv"):
            return f"{base}.mkv"
        elif os.path.isfile(f"{base}.mp4"):
            return f"{base}.mp4"
        elif os.path.isfile(f"{base}.mp4.webm"):
            return f"{base}.mp4.webm"

        return name

    except FileNotFoundError:
        return os.path.splitext(name)[0] + ".mp4"
import os
import os
import time
import mmap
import asyncio
import requests
import subprocess

from tqdm import tqdm
from pyrogram import Client
from pyrogram.types import Message
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import requests
import os
from tqdm import tqdm
import os
import requests
from tqdm import tqdm  # progress bar
def create_session():
    session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(
        max_retries=retries,
        pool_connections=10,
        pool_maxsize=10
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session
import os
import mmap
import requests
from tqdm import tqdm
from base64 import b64decode

# ==============================
# FILE DECRYPT FUNCTION
# ==============================
def decrypt_file(file_path: str, key: str) -> bool:
    if not file_path or not os.path.exists(file_path):
        return False

    if not key:
        return True

    key_bytes = key.encode()
    size = min(28, os.path.getsize(file_path))

    with open(file_path, "r+b") as f:
        with mmap.mmap(f.fileno(), length=size, access=mmap.ACCESS_WRITE) as mm:
            for i in range(size):
                mm[i] ^= key_bytes[i] if i < len(key_bytes) else i

    return True
# ==============================
# RAW FILE DOWNLOAD
# ==============================
def download_raw_file(url: str, filename: str) -> str | None:
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 13)",
        "Referer": "https://akstechnicalclasses.classx.co.in/",
        "Origin": "https://akstechnicalclasses.classx.co.in",
        "Accept": "*/*",
        "Connection": "keep-alive"
    }

    os.makedirs("downloads", exist_ok=True)
    file_path = f"downloads/{filename}.mkv"

    session = create_session()
    downloaded = 0

    if os.path.exists(file_path):
        downloaded = os.path.getsize(file_path)
        headers["Range"] = f"bytes={downloaded}-"

    try:
        with session.get(url, headers=headers, stream=True, timeout=(10, 180)) as r:
            if r.status_code not in (200, 206):
                print(f"❌ Bad status: {r.status_code}")
                return None

            total = int(r.headers.get("content-length", 0)) + downloaded
            chunk_size = 256 * 1024

            with open(file_path, "ab") as f, tqdm(
                total=total,
                initial=downloaded,
                unit="B",
                unit_scale=True,
                desc=filename,
                ncols=80
            ) as bar:
                for chunk in r.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        bar.update(len(chunk))

        return file_path

    except Exception as e:
        print(f"⚠️ Download interrupted (resume enabled): {e}")
        return file_path if os.path.exists(file_path) else None
# ==============================
# DOWNLOAD + DECRYPT WRAPPER
# ==============================

def download_and_decrypt_video(url: str, name: str, key: str = None) -> str | None:
    video_path = None

    for _ in range(5):  # resume attempts
        video_path = download_raw_file(url, name)
        if video_path and os.path.getsize(video_path) > 10 * 1024 * 1024:
            break

    if not video_path:
        return None

    if decrypt_file(video_path, key):
        return video_path

    return None

# ==============================
# EXAMPLE USAGE
# ==============================


async def send_doc(bot: Client, m: Message, cc, ka, cc1, prog, count, name, channel_id):
    reply = await bot.send_message(channel_id, f"Downloading pdf:\n<pre><code>{name}</code></pre>")
    time.sleep(1)
    start_time = time.time()
    await bot.send_document(ka, caption=cc1)
    count+=1
    await reply.delete (True)
    time.sleep(1)
    os.remove(ka)
    time.sleep(3) 



import asyncio

import asyncio

import asyncio

import os




    
import os
import time
import asyncio

# 🔹 Async ffmpeg runner (NO BLOCKING)
async def run_cmd(cmd: str):
    process = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL
    )
    await process.communicate()


async def send_vid(
    bot: Client,
    m: Message,
    cc,
    filename,
    vidwatermark,
    thumb,
    name,
    prog,
    channel_id
):
    # ==========================
    # THUMBNAIL GENERATION
    # ==========================
    thumb_path = f"{filename}.jpg"
    await run_cmd(
        f'ffmpeg -y -i "{filename}" -ss 00:00:10 -vframes 1 "{thumb_path}"'
    )

    await prog.delete(True)

    reply1 = await bot.send_message(
        channel_id,
        f"**📩 Uploading Video 📩:-**\n<blockquote>**{name}**</blockquote>"
    )

    reply = await m.reply_text(
        f"**Generate Thumbnail:**\n<blockquote>**{name}**</blockquote>"
    )

    # ==========================
    # THUMB SELECTION
    # ==========================
    thumbnail = thumb_path if thumb == "/d" else thumb

    # ==========================
    # WATERMARK PROCESS
    # ==========================
    if vidwatermark == "/d":
        w_filename = filename
    else:
        w_filename = f"w_{os.path.basename(filename)}"
        font_path = "vidwater.ttf"

        await run_cmd(
            f'ffmpeg -y -i "{filename}" -vf '
            f'"drawtext=fontfile={font_path}:text=\'{vidwatermark}\':'
            f'fontcolor=white@0.3:fontsize=h/6:'
            f'x=(w-text_w)/2:y=(h-text_h)/2" '
            f'-codec:a copy "{w_filename}"'
        )

    # ==========================
    # SAFETY CHECK
    # ==========================
    if not os.path.exists(w_filename):
        await m.reply_text("❌ Video processing failed")
        return

    dur = int(duration(w_filename))
    start_time = time.time()

    # ==========================
    # UPLOAD (VIDEO → DOC FALLBACK)
    # ==========================
    try:
        await bot.send_video(
            chat_id=channel_id,
            video=w_filename,
            caption=cc,
            supports_streaming=True,
            height=720,
            width=1280,
            thumb=thumbnail,
            duration=dur,
            progress=progress_bar,
            progress_args=(reply, start_time)
        )
    except Exception:
        await bot.send_document(
            chat_id=channel_id,
            document=w_filename,
            caption=cc,
            progress=progress_bar,
            progress_args=(reply, start_time)
        )

    # ==========================
    # CLEANUP
    # ==========================
    
    except Exception:
        await bot.send_document(channel_id, w_filename, caption=cc, progress=progress_bar, progress_args=(reply, start_time))
    os.remove(w_filename)
    await reply.delete(True)
    await reply1.delete(True)
    os.remove(f"{filename}.jpg")
