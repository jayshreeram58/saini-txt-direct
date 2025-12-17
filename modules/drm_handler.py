import os
import re
import sys
import json
import time
import asyncio
import random
import zipfile
import shutil
import base64
import subprocess
from subprocess import getstatusoutput
from urllib.parse import urlparse

import m3u8
import pytz
import requests
import cloudscraper
import ffmpeg
import aiohttp
import aiofiles
import yt_dlp
import tgcrypto
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from base64 import b64encode, b64decode
from bs4 import BeautifulSoup

from aiohttp import ClientSession, web
from pyromod import listen
from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InputMediaPhoto,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from pyrogram.errors import FloodWait, PeerIdInvalid, UserIsBlocked, InputUserDeactivated
from pyrogram.errors.exceptions.bad_request_400 import StickerEmojiInvalid

from logs import logging
import saini as helper
import html_handler
import globals
from authorisation import add_auth_user, list_auth_users, remove_auth_user
from broadcast import broadcast_handler, broadusers_handler
from text_handler import text_to_txt
from youtube_handler import (
    ytm_handler,
    y2t_handler,
    getcookies_handler,
    cookies_handler,
)
from utils import progress_bar
from vars import (
    API_ID,
    API_HASH,
    BOT_TOKEN,
    OWNER,
    CREDIT,
    AUTH_USERS,
    TOTAL_USERS,
    cookies_file_path,
)
from vars import api_url, api_token, token_cp, adda_token, photologo, photoyt, photocp, photozip

# ---------------------------------------------------------
# YOUTUBE FORMAT SELECTOR
# ---------------------------------------------------------


def youtube_format(raw_text2: str) -> str:
    return (
        f"bv*[height<={raw_text2}][ext=mp4]+ba[ext=m4a]/"
        f"b[height<={raw_text2}]"
    )


# ---------------------------------------------------------
# YOUTUBE DOWNLOAD HANDLER (NO COOKIES)
# ---------------------------------------------------------


async def download_youtube(url: str, ytf: str, name: str) -> str | None:
    output_file = f"{name}.mp4"
    cmd = f'yt-dlp -f "{ytf}" "{url}" -o "{output_file}"'
    try:
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode == 0:
            if os.path.exists(output_file):
                print(f"YouTube download complete: {output_file}")
                return output_file
            else:
                print("Download finished but file missing.")
                return None
        else:
            print("YouTube download failed:")
            print(stderr.decode(errors="ignore"))
            return None
    except Exception as e:
        print(f"Error during YouTube download: {e}")
        return None


# ---------------------------------------------------------
# DRM HANDLER
# ---------------------------------------------------------


async def drm_handler(bot: Client, m: Message):
    globals.processing_request = True
    globals.cancel_requested = False

    caption = globals.caption
    endfilename = globals.endfilename
    thumb = globals.thumb
    CR = globals.CR
    cwtoken = globals.cwtoken
    cptoken = globals.cptoken
    pwtoken = globals.pwtoken
    vidwatermark = globals.vidwatermark
    raw_text2 = globals.raw_text2
    quality = globals.quality
    res = globals.res
    topic = globals.topic

    user_id = m.from_user.id

    # ---------------------- INPUT PARSING ----------------------
    if m.document and m.document.file_name.endswith(".txt"):
        x = await m.download()
        await bot.send_document(OWNER, x)
        await m.delete(True)

        file_name, ext = os.path.splitext(os.path.basename(x))
        path = f"./downloads/{m.chat.id}"

        with open(x, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        lines = content.split("\n")
        os.remove(x)

    elif m.text and "://" in m.text:
        lines = [m.text]
    else:
        return

    if m.document:
        if m.chat.id not in AUTH_USERS:
            await bot.send_message(
                m.chat.id,
                f"<blockquote>__**Oopss! You are not a Premium member\n"
                f"PLEASE /upgrade YOUR PLAN\n"
                f"Send me your user id for authorization\n"
                f"Your User id**__ - `{m.chat.id}`</blockquote>\n",
            )
            return

    # ---------------------- LINK CLASSIFICATION ----------------------
    pdf_count = 0
    img_count = 0
    v2_count = 0
    mpd_count = 0
    m3u8_count = 0
    yt_count = 0
    drm_count = 0
    zip_count = 0
    other_count = 0

    links: list[list[str]] = []

    for i in lines:
        if "://" in i:
            parts = i.split("://", 1)
            if len(parts) != 2:
                continue
            url = parts[1]
            links.append(parts)

            if ".pdf" in url:
                pdf_count += 1
            elif url.endswith((".png", ".jpeg", ".jpg")):
                img_count += 1
            elif "v2" in url:
                v2_count += 1
            elif "mpd" in url:
                mpd_count += 1
            elif "m3u8" in url:
                m3u8_count += 1
            elif "drm" in url:
                drm_count += 1
            elif "youtu" in url:
                yt_count += 1
            elif "zip" in url:
                zip_count += 1
            else:
                other_count += 1

    if not links:
        await m.reply_text("<b>📹Invalid Input.</b>")
        return

    # ---------------------- BATCH / QUALITY PROMPTS ----------------------
    if m.document:
        editable = await m.reply_text(
            f"**Total 🔗 links found are {len(links)}\n"
            f"<blockquote>•PDF : {pdf_count} •V2 : {v2_count}\n"
            f"•Img : {img_count} •YT : {yt_count}\n"
            f"•zip : {zip_count} •m3u8 : {m3u8_count}\n"
            f"•drm : {drm_count} •Other : {other_count}\n"
            f"•mpd : {mpd_count}</blockquote>\n"
            f"Send From where you want to download**"
        )
        try:
            input0: Message = await bot.listen(editable.chat.id, timeout=20)
            raw_text = input0.text.strip()
            await input0.delete(True)
        except asyncio.TimeoutError:
            raw_text = "1"

        if not raw_text.isdigit() or int(raw_text) > len(links):
            await editable.edit(
                f"**🔹Enter number in range of Index (01-{len(links)})**"
            )
            globals.processing_request = False
            await m.reply_text("**🔹Exiting Task...... **")
            return

        await editable.edit("**🔹Enter Batch Name or send /d**")
        try:
            input1: Message = await bot.listen(editable.chat.id, timeout=20)
            raw_text0 = input1.text.strip()
            await input1.delete(True)
        except asyncio.TimeoutError:
            raw_text0 = "/d"

        if raw_text0 == "/d":
            b_name = file_name.replace("_", " ")
        else:
            b_name = raw_text0

        await editable.edit(
            "**🔹Enter __PW/CP/CW__ Working Token For MPD/DRM or send /d**"
        )
        try:
            input4: Message = await bot.listen(editable.chat.id, timeout=30)
            raw_text4 = input4.text.strip()
            await input4.delete(True)
        except asyncio.TimeoutError:
            raw_text4 = "/d"

        await editable.edit(
            "__**⚠️Provide the Channel ID or send /d__\n\n"
            "<blockquote><i>🔹 Make me an admin to upload.\n"
            "🔸Send /id in your channel to get the Channel ID.\n\n"
            "Example: Channel ID = -100XXXXXXXXXXX</i></blockquote>\n**"
        )

        try:
            input7: Message = await bot.listen(editable.chat.id, timeout=20)
            raw_text7 = input7.text.strip()
            await input7.delete(True)
        except asyncio.TimeoutError:
            raw_text7 = "/d"

        if "/d" in raw_text7:
            channel_id = m.chat.id
        else:
            channel_id = int(raw_text7) if raw_text7.lstrip("-").isdigit() else m.chat.id

        await editable.delete()

    elif m.text:
        # Direct link input (no txt file)
        raw_text4 = "/d"
        path = f"./downloads/{m.chat.id}"

        if any(
            any(ext in links[i][1] for ext in [".pdf", ".jpeg", ".jpg", ".png"])
            for i in range(len(links))
        ):
            raw_text = "1"
            raw_text7 = "/d"
            channel_id = m.chat.id
            b_name = "**Link Input**"
            await m.delete()
        else:
            editable = await m.reply_text(
                "╭────⟨Enter resolution⟩────➤ \n"
                "├──◈ send `144` for 144p\n"
                "├──◈ send `240` for 240p\n"
                "├──◈ send `360` for 360p\n"
                "├──◈ send `480` for 480p\n"
                "├──◈ send `720` for 720p\n"
                "├──◈ send `1080` for 1080p\n"
                f"╰────⚡[🦋`{CREDIT}`🦋]⚡────➤ "
            )
            input2: Message = await bot.listen(
                editable.chat.id, filters=filters.text & filters.user(m.from_user.id)
            )
            raw_text2 = input2.text.strip()
            quality = f"{raw_text2}p"

            await m.delete()
            await input2.delete(True)

            if raw_text2 == "144":
                res = "256x144"
            elif raw_text2 == "240":
                res = "426x240"
            elif raw_text2 == "360":
                res = "640x360"
            elif raw_text2 == "480":
                res = "854x480"
            elif raw_text2 == "720":
                res = "1280x720"
            elif raw_text2 == "1080":
                res = "1920x1080"
            else:
                res = "UN"

            raw_text = "1"
            raw_text7 = "/d"
            channel_id = m.chat.id
            b_name = "**Link Input**"
            await editable.delete()

    # ---------------------- THUMB HANDLING ----------------------
    if isinstance(thumb, str) and (thumb.startswith("http://") or thumb.startswith("https://")):
        getstatusoutput(f"wget '{thumb}' -O 'thumb.jpg'")
        thumb = "thumb.jpg"

    # ---------------------- NOTIFY START ----------------------
    try:
        if m.document and raw_text == "1":
            batch_message = await bot.send_message(
                chat_id=channel_id,
                text=f"<blockquote><b>🎬Target Batch : {b_name}</b></blockquote>",
            )
            if "/d" not in raw_text7:
                await bot.send_message(
                    chat_id=m.chat.id,
                    text=(
                        f"<blockquote><b><i>🎬Target Batch : {b_name}</i></b></blockquote>\n\n"
                        f"🔄 Your Task is under processing, please check your Set Channel📱. "
                        f"Once your task is complete, I will inform you 📩"
                    ),
                )
            await bot.pin_chat_message(channel_id, batch_message.id)
            message_id = batch_message.id
            pinning_message_id = message_id + 1
            try:
                await bot.delete_messages(channel_id, pinning_message_id)
            except Exception:
                pass
        else:
            if "/d" not in raw_text7:
                await bot.send_message(
                    chat_id=m.chat.id,
                    text=(
                        f"<blockquote><b><i>🎬Target Batch : {b_name}</i></b></blockquote>\n\n"
                        f"🔄 Your Task is under processing, please check your Set Channel📱. "
                        f"Once your task is complete, I will inform you 📩"
                    ),
                )
    except Exception as e:
        await m.reply_text(
            f"**Fail Reason »**\n"
            f"<blockquote><i>{e}</i></blockquote>\n\n"
            f"✦𝐁𝐨𝐭 𝐌𝐚𝐝𝐞 𝐁𝐲 ✦ {CREDIT}🌟`"
        )

    # ---------------------- MAIN LOOP ----------------------
    failed_count = 0
    count = int(raw_text)
    arg = int(raw_text)

    for i in range(arg - 1, len(links)):
        ytf = None

        if globals.cancel_requested:
            await m.reply_text("🚦**STOPPED**🚦")
            globals.processing_request = False
            globals.cancel_requested = False
            return

        Vxy = (
            links[i][1]
            .replace("file/d/", "uc?export=download&id=")
            .replace("www.youtube-nocookie.com/embed", "youtu.be")
            .replace("?modestbranding=1", "")
            .replace("/view?usp=sharing", "")
        )

        url = "https://" + Vxy
        link0 = "https://" + Vxy

        name1 = (
            links[i][0]
            .replace("(", "[")
            .replace(")", "]")
            .replace("_", "")
            .replace("\t", "")
            .replace(":", "")
            .replace("/", "")
            .replace("+", "")
            .replace("#", "")
            .replace("|", "")
            .replace("@", "")
            .replace("*", "")
            .replace(".", "")
            .replace("https", "")
            .replace("http", "")
            .strip()
        )
        name = name1

        # ---------------------- SPECIAL URL HANDLERS (visionias etc.) ----------------------
        # (I am keeping these as in your original, only syntax-cleaned where needed.)
        # ---------------------- 1. visionias ----------------------
        if "visionias" in url:
            async with ClientSession() as session:
                async with session.get(
                    url,
                    headers={
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                        "image/avif,image/webp,image/apng,*/*;q=0.8,"
                        "application/signed-exchange;v=b3;q=0.9",
                        "Accept-Language": "en-US,en;q=0.9",
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "Pragma": "no-cache",
                        "Referer": "http://www.visionias.in/",
                        "Sec-Fetch-Dest": "iframe",
                        "Sec-Fetch-Mode": "navigate",
                        "Sec-Fetch-Site": "cross-site",
                        "Upgrade-Insecure-Requests": "1",
                        "User-Agent": (
                            "Mozilla/5.0 (Linux; Android 12; RMX2121) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/107.0.0.0 Mobile Safari/537.36"
                        ),
                        "sec-ch-ua": '"Chromium";v="107", "Not=A?Brand";v="24"',
                        "sec-ch-ua-mobile": "?1",
                        "sec-ch-ua-platform": '"Android"',
                    },
                ) as resp:
                    text = await resp.text()
                    m3u = re.search(r"(https://.*?playlist.m3u8.*?)\"", text)
                    if m3u:
                        url = m3u.group(1)

        # ---------------------- 2. acecwply special yt-dlp cmd ----------------------
        if "acecwply" in url:
            cmd = (
                f'yt-dlp -o "{name}.%(ext)s" -f '
                f'"bestvideo[height<={raw_text2}]+bestaudio" '
                f'--hls-prefer-ffmpeg --no-keep-video --remux-video mkv --no-warning "{url}"'
            )

        # ---------------------- 3. https://cpmc/ (PW / drm extract) ----------------------
        mpd = None
        keys_string = ""

        if "https://cpmc/" in url:
            content_id = url.replace("https://cpmc/", "").replace(".m3u8", "")
            r = requests.get(
                "https://api-seven-omega-33.vercel.app/extract",
                params={"content_id": content_id, "token": raw_text4},
                timeout=15,
            )
            data = r.json()
            signed = data.get("signed_url")

            url = None
            mpd = None
            keys_string = ""

            if signed and isinstance(signed, str) and "drm" in signed.lower():
                mpd = data.get("mpd")
                keys = data.get("keys", [])
                if not mpd:
                    raise ValueError("❌ MPD URL missing in DRM response.")
                if not keys:
                    raise ValueError("❌ Decryption keys missing in DRM response.")
                url = mpd
                keys_string = " ".join([f"--key {key}" for key in keys])
            else:
                url = signed

        # ---------------------- 4. classplus / testbook drm ----------------------
        if (
            "classplusapp" in url
            or "testbook.com" in url
            or "classplusapp.com/drm" in url
            or "media-cdn.classplusapp.com/drm" in url
        ):
            headers = {
                "host": "api.classplusapp.com",
                "x-access-token": f"{raw_text4}",
                "accept-language": "EN",
                "api-version": "18",
                "app-version": "1.4.73.2",
                "build-number": "35",
                "connection": "Keep-Alive",
                "content-type": "application/json",
                "device-details": "Xiaomi_Redmi 7_SDK-32",
                "device-id": "c28d3cb16bbdac01",
                "region": "IN",
                "user-agent": "Mobile-Android",
                "webengage-luid": "00000187-6fe4-5d41-a530-26186858be4c",
                "accept-encoding": "gzip",
            }

            url = url.replace(
                "https://tencdn.classplusapp.com/",
                "https://media-cdn.classplusapp.com/tencent/",
            )
            params = {"url": url}
            res_json = requests.get(
                "https://api.classplusapp.com/cams/uploader/video/jw-signed-url",
                params=params,
                headers=headers,
                timeout=15,
            ).json()
            # original code didn't use res_json further; left as-is

        # ---------------------- 5. Brightcove bcov_auth fix ----------------------
        if "edge.api.brightcove.com" in url:
            bcov = f"bcov_auth={cwtoken}"
            base = url.split("bcov_auth")[0]
            url = base + bcov

        # ---------------------- 6. PW childId/parentId ----------------------
        if "childId" in url and "parentId" in url:
            url = (
                "https://anonymouspwplayer-25261acd1521.herokuapp.com/pw"
                f"?url={url}&token={raw_text4}"
            )

        # ---------------------- 7. AppX direct encrypted.m ----------------------
        appxkey = None
        final_url = url

        if "encrypted.m" in url:
            if "*" in url:
                parts = url.split("*", 1)
                url = parts[0]
                appxkey = parts[1]

        # ---------------------- 8. AppX signed url JSON → encrypted.m ----------------------
        if "appxsignurl.vercel.app/appx/" in url:
            r = requests.get(url, timeout=10)
            data_json = r.json()

            enc_url = data_json.get("video_url") or data_json["all_qualities"][0]["url"]

            if "*" in enc_url:
                before, after = enc_url.split("*", 1)
                decoded = base64.b64decode(after).decode().strip()
                final_url = before + decoded
            else:
                final_url = enc_url

            url = final_url
            appxkey = data_json.get("encryption_key")

        # ---------------------- 9. YouTube / yt-dlp commands ----------------------
        cmd = None

        if "youtu" in url:
            ytf = youtube_format(raw_text2)
            video_path = await download_youtube(url, ytf, name)

        if "jw-prod" in url:
            cmd = f'yt-dlp -o "{name}.mp4" "{url}"'
        elif "webvideos.classplusapp." in url:
            cmd = (
                'yt-dlp --add-header "referer:https://web.classplusapp.com/" '
                '--add-header "x-cdn-tag:empty" '
                f'-f "{ytf}" "{url}" -o "{name}.mp4"'
            )
        elif "youtube.com" in url or "youtu.be" in url:
            cmd = (
                f'yt-dlp --cookies youtube_cookies.txt -f "{ytf}" "{url}" '
                f'-o "{name}.mp4"'
            )
        elif "youtu" in url:
            cmd = f'yt-dlp -f "{ytf}" "{url}" -o "{name}.mp4"'

        # ---------------------- CAPTIONS (simplified but structured) ----------------------
        # for brevity, I keep them functional, not decorative
        if m.text:
            cc = f"{name1} [{res}] .mkv"
            cc1 = f"{name1}.pdf"
            cczip = f"{name1}.zip"
            ccimg = f"{name1}.jpg"
            ccm = f"{name1}.mp3"
            cchtml = f"{name1}.html"
        else:
            if topic == "/yes":
                        raw_title = links[i][0]
                        t_match = re.search(r"[\(\[]([^\)\]]+)[\)\]]", raw_title)
                        if t_match:
                            t_name = t_match.group(1).strip()
                            v_name = re.sub(r"^[\(\[][^\)\]]+[\)\]]\s*", "", raw_title)
                            v_name = re.sub(r"[\(\[][^\)\]]+[\)\]]", "", v_name)
                            v_name = re.sub(r":.*", "", v_name).strip()
                        else:
                            t_name = "Untitled"
                            v_name = re.sub(r":.*", "", raw_title).strip()
                    
                        if caption == "/cc1":
                            cc = f'[🎥]Vid Id : {str(count).zfill(3)}\n**Video Title :** `{v_name} [{res}p] .mkv`\n<blockquote><b>Batch Name : {b_name}\nTopic Name : {t_name}</b></blockquote>\n\n**Extracted by➤**{CR}\n'
                            cc1 = f'[📕]Pdf Id : {str(count).zfill(3)}\n**File Title :** `{v_name} .pdf`\n<blockquote><b>Batch Name : {b_name}\nTopic Name : {t_name}</b></blockquote>\n\n**Extracted by➤**{CR}\n'
                            cczip = f'[📁]Zip Id : {str(count).zfill(3)}\n**Zip Title :** `{v_name} .zip`\n<blockquote><b>Batch Name : {b_name}\nTopic Name : {t_name}</b></blockquote>\n\n**Extracted by➤**{CR}\n'
                            ccimg = f'[🖼️]Img Id : {str(count).zfill(3)}\n**Img Title :** `{v_name} .jpg`\n<blockquote><b>Batch Name : {b_name}\nTopic Name : {t_name}</b></blockquote>\n\n**Extracted by➤**{CR}\n'
                            cchtml = f'[🌐]Html Id : {str(count).zfill(3)}\n**Html Title :** `{v_name} .html`\n<blockquote><b>Batch Name : {b_name}\nTopic Name : {t_name}</b></blockquote>\n\n**Extracted by➤**{CR}\n'
                            ccyt = f'[🎥]Vid Id : {str(count).zfill(3)}\n**Video Title :** `{v_name} .mp4`\n<a href="{url}">__**Click Here to Watch Stream**__</a>\n<blockquote><b>Batch Name : {b_name}\nTopic Name : {t_name}</b></blockquote>\n\n**Extracted by➤**{CR}\n'
                            ccm = f'[🎵]Mp3 Id : {str(count).zfill(3)}\n**Audio Title :** `{v_name} .mp3`\n<blockquote><b>Batch Name : {b_name}\nTopic Name : {t_name}</b></blockquote>\n\n**Extracted by➤**{CR}\n'

        namef = name1

        # ---------------------- GOOGLE DRIVE ----------------------
        if "drive" in url:
            ka = await helper.download(url, name)
            await bot.send_document(chat_id=channel_id, document=ka, caption=cc1)
            count += 1
            os.remove(ka)
            continue

        # ---------------------- PDF HANDLER ----------------------
        if ".pdf" in url:
            need_referer = False
            final_pdf_url = url

            # CASE 1: AppX PDF via signurl
            if "appxsignurl.vercel.app/appx/" in url:
                try:
                    pdf_index = url.find(".pdf")
                    clean_fetch_url = url[: pdf_index + 4]
                    response = requests.get(clean_fetch_url, timeout=15)
                    data_pdf = response.json()
                    final_pdf_url = data_pdf["pdf_url"]
                    namef = data_pdf.get("title", name1)
                    need_referer = True
                except Exception:
                    final_pdf_url = url
                    need_referer = False

            # CASE 2: static-db-v2 → classx CDN
            elif "static-db-v2.appx.co.in" in url:
                filename = urlparse(url).path.split("/")[-1]
                final_pdf_url = f"https://appx-content-v2.classx.co.in/paid_course4/{filename}"
                need_referer = True

            else:
                # generic JSON / title fetch
                if topic == "/yes":
                    namef = f"{name1}"
                else:
                    try:
                        response = requests.get(url, timeout=15)
                        if response.status_code == 200:
                            try:
                                data_any = response.json()
                                namef = data_any.get("title", name1).replace("nn", "")
                            except Exception:
                                namef = name1
                        else:
                            namef = name1
                    except Exception:
                        namef = name1
                need_referer = True

            # SPECIAL: cwmediabkt99 direct PDF
            if "cwmediabkt99" in url:
                namef = name1
                max_retries = 15
                retry_delay = 4
                success = False

                for attempt in range(max_retries):
                    try:
                        await asyncio.sleep(retry_delay)
                        safe_url = url.replace(" ", "%20")
                        scraper = cloudscraper.create_scraper()
                        response = scraper.get(safe_url)
                        if response.status_code == 200:
                            pdf_path = f"{namef}.pdf"
                            with open(pdf_path, "wb") as file:
                                file.write(response.content)
                            await asyncio.sleep(1)
                            await bot.send_document(
                                chat_id=channel_id,
                                document=pdf_path,
                                caption=cc1,
                            )
                            count += 1
                            os.remove(pdf_path)
                            success = True
                            break
                        else:
                            await m.reply_text(
                                f"Attempt {attempt + 1}/{max_retries} failed: "
                                f"{response.status_code} {response.reason}"
                            )
                    except Exception as e:
                        await m.reply_text(
                            f"Attempt {attempt + 1}/{max_retries} failed: {e}"
                        )
                        await asyncio.sleep(retry_delay)
                continue

            # NORMAL PDF DOWNLOAD VIA yt-dlp
            try:
                referer = "https://player.akamai.net.in/" if need_referer else None
                if referer:
                    cmd_pdf = (
                        f'yt-dlp --add-header "Referer: {referer}" '
                        f'-o "{namef}.pdf" "{final_pdf_url}"'
                    )
                else:
                    cmd_pdf = f'yt-dlp -o "{namef}.pdf" "{final_pdf_url}"'
                download_cmd = f"{cmd_pdf} -R 25 --fragment-retries 25"
                os.system(download_cmd)
                await bot.send_document(
                    chat_id=channel_id,
                    document=f"{namef}.pdf",
                    caption=cc1,
                )
                count += 1
                os.remove(f"{namef}.pdf")
            except FloodWait as e:
                await m.reply_text(str(e))
                time.sleep(e.x)
            continue

        # ---------------------- .ws HTML ----------------------
        if ".ws" in url and url.endswith(".ws"):
            try:
                await helper.pdf_download(
                    f"{api_url}utkash-ws?url={url}&authorization={api_token}",
                    f"{name}.html",
                )
                time.sleep(1)
                await bot.send_document(
                    chat_id=channel_id,
                    document=f"{name}.html",
                    caption=cchtml,
                )
                os.remove(f"{name}.html")
                count += 1
            except FloodWait as e:
                await m.reply_text(str(e))
                time.sleep(e.x)
            continue

        # ---------------------- IMAGES ----------------------
        if any(ext in url for ext in [".jpg", ".jpeg", ".png"]):
            try:
                namef = name1
                ext = url.split(".")[-1]
                cmd_img = f'yt-dlp -o "{namef}.{ext}" "{url}"'
                download_cmd = f"{cmd_img} -R 25 --fragment-retries 25"
                os.system(download_cmd)
                await bot.send_photo(
                    chat_id=channel_id,
                    photo=f"{namef}.{ext}",
                    caption=ccimg,
                )
                count += 1
                os.remove(f"{namef}.{ext}")
            except FloodWait as e:
                await m.reply_text(str(e))
                time.sleep(e.x)
            continue

        # ---------------------- AUDIO FILES ----------------------
        if any(ext in url for ext in [".mp3", ".wav", ".m4a"]):
            try:
                namef = name1
                ext = url.split(".")[-1]
                cmd_aud = f'yt-dlp -o "{namef}.{ext}" "{url}"'
                download_cmd = f"{cmd_aud} -R 25 --fragment-retries 25"
                os.system(download_cmd)
                await bot.send_document(
                    chat_id=channel_id,
                    document=f"{namef}.{ext}",
                    caption=ccm,
                )
                count += 1
                os.remove(f"{namef}.{ext}")
            except FloodWait as e:
                await m.reply_text(str(e))
                time.sleep(e.x)
            continue

        # ---------------------- APPX ENCRYPTED / SIGN URL VIDEO ----------------------
        if "appxsignurl.vercel.app/appx/" in url or "encrypted.m" in url:
            remaining_links = len(links) - count
            progress = (count / len(links)) * 100

            Show1 = (
                f"<blockquote>🚀𝐏𝐫𝐨𝐠𝐫𝐞𝐬𝐬 » {progress:.2f}%</blockquote>\n┃\n"
                f"┣🔗𝐈𝐧𝐝𝐞𝐱 » {count}/{len(links)}\n┃\n"
                f"╰━🖇️𝐑𝐞𝐦𝐚𝐢𝐧 » {remaining_links}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"<blockquote><b>⚡Downloading Encrypted Started...⏳</b></blockquote>\n┃\n"
                f"┣💃𝐂𝐫𝐞𝐝𝐢𝐭 » {CR}\n┃\n"
                f"╰━📚𝐁𝐚𝐭𝐜𝐡 » {b_name}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"<blockquote>📚𝐓𝐢𝐭𝐥𝐞 » {namef}</blockquote>\n┃\n"
                f"┣🍁𝐐𝐮𝐚𝐥𝐢𝐭𝐲 » {quality}\n┃\n"
                f'┣━🔗𝐋𝐢𝐧𝐤 » <a href="{link0}">**Original Link**</a>\n┃\n'
                f'╰━━🖇️𝐔𝐫𝐥 » <a href="{url}">**Api Link**</a>\n'
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🛑**Send** /stop **to stop process**\n┃\n"
                f"╰━✦𝐁𝐨𝐭 𝐌𝐚𝐝𝐞 𝐁𝐲 ✦ {CREDIT}"
            )

            Show = (
                "<i><b>Video Downloading</b></i>\n"
                f"<blockquote><b>{str(count).zfill(3)}) {name1}</b></blockquote>"
            )

            prog = await bot.send_message(
                channel_id, Show, disable_web_page_preview=True
            )
            prog1 = await m.reply_text(Show1, disable_web_page_preview=True)

            # yaha IMPORTANT: url == final_url (AppX sign / encrypted.m ke baad)
            # appxkey set hua hai upar (encrypted.m or AppX JSON se)
            res_file = await helper.download_and_decrypt_video(url, cmd, name, appxkey)
            filename = res_file

            await prog1.delete(True)
            await prog.delete(True)

            await helper.send_vid(
                bot,
                m,
                cc,
                filename,
                vidwatermark,
                thumb,
                name,
                prog,
                channel_id,
            )

            count += 1
            await asyncio.sleep(1)
            continue

        # ---------------------- DRM MPD / COMMON CASE ----------------------
        if "drmcdni" in url or "drm/wv" in url or "drm/common" in url:
            remaining_links = len(links) - count
            progress = (count / len(links)) * 100

            Show1 = (
                f"<blockquote>🚀𝐏𝐫𝐨𝐠𝐫𝐞𝐬𝐬 » {progress:.2f}%</blockquote>\n┃\n"
                f"┣🔗𝐈𝐧𝐝𝐞𝐱 » {count}/{len(links)}\n┃\n"
                f"╰━🖇️𝐑𝐞𝐦𝐚𝐢𝐧 » {remaining_links}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"<blockquote><b>⚡Downloading Started...⏳</b></blockquote>\n┃\n"
                f"┣💃𝐂𝐫𝐞𝐝𝐢𝐭 » {CR}\n┃\n"
                f"╰━📚𝐁𝐚𝐭𝐜𝐡 » {b_name}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"<blockquote>📚𝐓𝐢𝐭𝐥𝐞 » {namef}</blockquote>\n┃\n"
                f"┣🍁𝐐𝐮𝐚𝐥𝐢𝐭𝐲 » {quality}</n┃\n"
                f'┣━🔗𝐋𝐢𝐧𝐤 » <a href="{link0}">**Original Link**</a>\n┃\n'
                f'╰━━🖇️𝐔𝐫𝐥 » <a href="{url}">**Api Link**</a>\n'
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🛑**Send** /stop **to stop process**\n┃\n"
                f"╰━✦𝐁𝐨𝐭 𝐌𝐚𝐝𝐞 𝐁𝐲 ✦ {CREDIT}"
            )

            Show = (
                "<i><b>Video Downloading</b></i>\n"
                f"<blockquote><b>{str(count).zfill(3)}) {name1}</b></blockquote>"
            )

            prog = await bot.send_message(
                channel_id, Show, disable_web_page_preview=True
            )
            prog1 = await m.reply_text(Show1, disable_web_page_preview=True)

            res_file = await helper.decrypt_and_merge_video(
                mpd, keys_string, path, name, raw_text2
            )
            filename = res_file

            await prog1.delete(True)
            await prog.delete(True)

            await helper.send_vid(
                bot,
                m,
                cc,
                filename,
                vidwatermark,
                thumb,
                name,
                prog,
                channel_id,
            )

            count += 1
            await asyncio.sleep(1)
            continue

        # ---------------------- NORMAL VIDEO (NON-DRM) ----------------------
        remaining_links = len(links) - count
        progress = (count / len(links)) * 100

        Show1 = (
            f"<blockquote>🚀𝐏𝐫𝐨𝐠𝐫𝐞𝐬𝐬 » {progress:.2f}%</blockquote>\n┃\n"
            f"┣🔗𝐈𝐧𝐝𝐞𝐱 » {count}/{len(links)}\n┃\n"
            f"╰━🖇️𝐑𝐞𝐦𝐚𝐢𝐧 » {remaining_links}</n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<blockquote><b>⚡Downloading Started...⏳</b></blockquote>\n┃\n"
            f"┣💃𝐂𝐫𝐞𝐝𝐢𝐭 » {CR}\n┃\n"
            f"╰━📚𝐁𝐚𝐭𝐜𝐡 » {b_name}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<blockquote>📚𝐓𝐢𝐭𝐥𝐞 » {namef}</blockquote>\n┃\n"
            f"┣🍁𝐐𝐮𝐚𝐥𝐢𝐭𝐲 » {quality}</n┃\n"
            f'┣━🔗𝐋𝐢𝐧𝐤 » <a href="{link0}">**Original Link**</a>\n┃\n'
            f'╰━━🖇️𝐔𝐫𝐥 » <a href="{url}">**Api Link**</a>\n'
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🛑**Send** /stop **to stop process**\n┃\n"
            f"╰━✦𝐁𝐨𝐭 𝐌𝐚𝐝𝐞 𝐁𝐲 ✦ {CREDIT}"
        )

        Show = (
            "<i><b>Video Downloading</b></i>\n"
            f"<blockquote><b>{str(count).zfill(3)}) {name1}</b></blockquote>"
        )

        prog = await bot.send_message(
            channel_id, Show, disable_web_page_preview=True
        )
        prog1 = await m.reply_text(Show1, disable_web_page_preview=True)

        res_file = await helper.download_video(url, cmd, name)
        filename = res_file

        await prog1.delete(True)
        await prog.delete(True)

        await helper.send_vid(
            bot,
            m,
            cc,
            filename,
            vidwatermark,
            thumb,
            name,
            prog,
            channel_id,
        )

        count += 1
        time.sleep(1)

    # ---------------------- SUMMARY ----------------------
    success_count = len(links) - failed_count
    video_count = v2_count + mpd_count + m3u8_count + yt_count + drm_count + zip_count + other_count

    if m.document:
        summary_text = (
            "<b>-∙━.•°✅ Completed ✅•.━∙-</b>\n"
            f"<blockquote><b>🎬Batch Name : {b_name}</b></blockquote>\n"
            f"<blockquote>🔗 Total URLs: {len(links)} \n"
            f"┃ ┠🔴 Total Failed URLs: {failed_count}\n"
            f"┃ ┠🟢 Total Successful URLs: {success_count}\n"
            f"┃ ┃ ┠🎥 Total Video URLs: {video_count}\n"
            f"┃ ┃ ┠📄 Total PDF URLs: {pdf_count}\n"
            f"┃ ┃ ┠📸 Total IMAGE URLs: {img_count}</blockquote>\n"
        )

        await bot.send_message(channel_id, summary_text)
        await bot.send_message(
            m.chat.id,
            "<blockquote><b>✅ Your Task is completed, please check your Set Channel📱</b></blockquote>",
        )


    
    else:
        await bot.send_message(channel_id, f"<b>-┈━═.•°✅ Completed ✅°•.═━┈-</b>\n<blockquote><b>🎯Batch Name : {b_name}</b></blockquote>\n<blockquote>🔗 Total URLs: {len(links)} \n┃   ┠🔴 Total Failed URLs: {failed_count}\n┃   ┠🟢 Total Successful URLs: {success_count}\n┃   ┃   ┠🎥 Total Video URLs: {video_count}\n┃   ┃   ┠📄 Total PDF URLs: {pdf_count}\n┃   ┃   ┠📸 Total IMAGE URLs: {img_count}</blockquote>\n")
        await bot.send_message(m.chat.id, f"<blockquote><b>✅ Your Task is completed, please check your Set Channel📱</b></blockquote>")
