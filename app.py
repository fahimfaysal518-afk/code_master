import streamlit as st
import sqlite3
import os
import re
import subprocess
import asyncio
import edge_tts
import urllib.parse
import urllib.request
import textwrap
import shutil
from PIL import Image, ImageDraw, ImageFont

# --- ১. পেজ কনফিগারেশন ---
st.set_page_config(
    page_title="Pro AI Shorts Studio",
    page_icon="🎬",
    layout="centered"
)

ADMIN_PASSWORD = "Fahim.55@01617513110"
FONT_FILE = "Kalpurush.ttf"

# --- ২. সিস্টেম ডায়াগনস্টিকস (FFmpeg চেক) ---
def check_ffmpeg():
    return shutil.which("ffmpeg") is not None, shutil.which("ffprobe") is not None

ffmpeg_ok, ffprobe_ok = check_ffmpeg()

# --- ৩. ফন্ট ডাউনলোড হ্যান্ডলার ---
def get_font_file():
    if os.path.exists(FONT_FILE) and os.path.getsize(FONT_FILE) > 10000:
        return FONT_FILE
    
    urls = [
        "https://raw.githubusercontent.com/maateen/bangla-fonts/master/fonts/Kalpurush.ttf",
        "https://github.com/kaushikbhaumik/Bengali-Fonts/raw/master/Kalpurush.ttf"
    ]
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response, open(FONT_FILE, 'wb') as out_file:
                out_file.write(response.read())
            if os.path.exists(FONT_FILE) and os.path.getsize(FONT_FILE) > 10000:
                return FONT_FILE
        except Exception:
            continue
            
    return None

# --- ৪. ডেটাবেস সিস্টেম (SQLite) ---
DB_NAME = "system_data.db"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            is_blocked INTEGER NOT NULL DEFAULT 0
        )
        ''')
        conn.commit()

init_db()

def verify_user(username):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT is_blocked FROM users WHERE username=?", (username,))
        row = cursor.fetchone()
        
        if not row:
            return False, "❌ এই ইউজারনেমটি রেজিস্টার্ড নয়! আগে নতুন অ্যাকাউন্ট তৈরি করুন।"
        
        is_blocked = row[0]
        if is_blocked == 1:
            return False, "🔴 আপনার অ্যাকাউন্টটি এডমিন দ্বারা ব্লক করা হয়েছে!"
            
        return True, "OK"

# --- ৫. ভয়েস ও ইমেজ জেনারেটর ---
def generate_voice_sync(text, voice_code, output_audio):
    async def _async_tts():
        communicate = edge_tts.Communicate(text, voice_code)
        await communicate.save(output_audio)
    
    try:
        asyncio.run(_async_tts())
    except Exception:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_async_tts())
        loop.close()

def get_media_duration(audio_file):
    try:
        cmd = f'ffprobe -v error -show_entries format=duration -of default=noprintwrappers=1:nokey=1 "{audio_file}"'
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        dur = float(res.stdout.strip())
        return max(dur, 2.5)
    except Exception:
        return 4.0

def clean_script_line(text):
    cleaned = re.sub(r'^[0-9১২৩৪৫৬৭৮৯০\s\.\)\-\•]+', '', text).strip()
    return cleaned if cleaned else text

def create_base_image(prompt_text, idx):
    filename = f"base_img_{idx}.jpg"
    clean_p = clean_script_line(prompt_text)
    
    encoded_prompt = urllib.parse.quote(f"cinematic vertical 9:16 portrait video frame, {clean_p[:100]}, detailed, 8k")
    pollinations_urls = [
        f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1080&height=1920&nologo=true&seed={idx * 314 + 42}",
        f"https://picsum.photos/seed/{idx * 77 + abs(hash(clean_p)) % 1000}/1080/1920"
    ]
    
    headers = {'User-Agent': 'Mozilla/5.0'}
    for url in pollinations_urls:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as response:
                if response.status == 200:
                    data = response.read()
                    if len(data) > 5000:
                        with open(filename, 'wb') as f:
                            f.write(data)
                        return filename
        except Exception:
            continue

    # Fallback Gradient Canvas
    img = Image.new('RGB', (1080, 1920))
    draw = ImageDraw.Draw(img)
    palettes = [[(15, 23, 42), (88, 28, 135)], [(15, 32, 39), (44, 83, 100)], [(20, 30, 48), (36, 59, 85)]]
    top_color, bot_color = palettes[idx % len(palettes)]
    for y in range(1920):
        r = int(top_color[0] + (bot_color[0] - top_color[0]) * (y / 1920))
        g = int(top_color[1] + (bot_color[1] - top_color[1]) * (y / 1920))
        b = int(top_color[2] + (bot_color[2] - top_color[2]) * (y / 1920))
        draw.line([(0, y), (1080, y)], fill=(r, g, b))
    img.save(filename, quality=95)
    return filename

# --- ৬. ছবিতে টাইটেল ও সাবটাইটেল লেআউট রেন্ডার ---
def add_text_overlays(image_path, title_text, caption_text, font_path, idx):
    out_file = f"framed_img_{idx}.png"
    img = Image.open(image_path).convert('RGBA')
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    try:
        font_title = ImageFont.truetype(font_path, 48) if font_path else ImageFont.load_default()
        font_cap = ImageFont.truetype(font_path, 40) if font_path else ImageFont.load_default()
    except Exception:
        font_title = ImageFont.load_default()
        font_cap = ImageFont.load_default()

    # ১. মেইন টাইটেল (উপরে)
    if title_text.strip():
        wrapped_t = textwrap.fill(title_text.strip(), width=22)
        bbox = draw.textbbox((0, 0), wrapped_t, font=font_title)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x, y = (1080 - w) // 2, 140
        draw.rounded_rectangle([x - 20, y - 15, x + w + 20, y + h + 25], radius=15, fill=(0, 0, 0, 180))
        draw.text((x, y), wrapped_t, font=font_title, fill=(255, 230, 0, 255), align="center")

    # ২. ক্যাপশন/সাবটাইটেল (নিচে)
    if caption_text.strip():
        wrapped_c = textwrap.fill(caption_text.strip(), width=24)
        bbox = draw.textbbox((0, 0), wrapped_c, font=font_cap)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x, y = (1080 - w) // 2, 1500 - (h // 2)
        draw.rounded_rectangle([x - 25, y - 20, x + w + 25, y + h + 25], radius=18, fill=(0, 0, 0, 195))
        draw.text((x, y), wrapped_c, font=font_cap, fill=(255, 255, 255, 255), align="center")

    final_img = Image.alpha_composite(img, overlay).convert('RGB')
    final_img.save(out_file, quality=95)
    return out_file

# --- ৭. ভিডিও রেন্ডারিং ইঞ্জিন ---
def build_pro_shorts(title_text, lines, voice_code, add_bgm):
    scene_videos = []
    font_path = get_font_file()
    logs = []

    for idx, line in enumerate(lines):
        clean_line = clean_script_line(line)
        if not clean_line:
            continue

        audio_file = f"audio_{idx}.mp3"
        try:
            generate_voice_sync(clean_line, voice_code, audio_file)
        except Exception as e:
            return None, f"ভয়েস জেনারেট করতে সমস্যা হয়েছে: {str(e)}"

        duration = get_media_duration(audio_file)
        raw_img = create_base_image(clean_line, idx)
        framed_img = add_text_overlays(raw_img, title_text, clean_line, font_path, idx)

        scene_out = f"scene_{idx}.mp4"

        # Zoompan Motion Animation Effect
        zoom_vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,zoompan=z='min(pzoom+0.0015,1.18)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=25"

        cmd = (
            f'ffmpeg -y -loop 1 -i "{framed_img}" -i "{audio_file}" '
            f'-vf "{zoom_vf}" '
            f'-c:v libx264 -t {duration} -pix_fmt yuv420p -c:a aac -b:a 192k -shortest "{scene_out}"'
        )

        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)

        # Fallback if Zoompan fails on low-spec server
        if res.returncode != 0:
            cmd_fallback = (
                f'ffmpeg -y -loop 1 -i "{framed_img}" -i "{audio_file}" '
                f'-vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920" '
                f'-c:v libx264 -t {duration} -pix_fmt yuv420p -c:a aac -b:a 192k -shortest "{scene_out}"'
            )
            res_fb = subprocess.run(cmd_fallback, shell=True, capture_output=True, text=True)
            if res_fb.returncode != 0:
                return None, f"FFmpeg Render Error in Scene {idx}: {res_fb.stderr}"

        # Cleanup temp scene files
        for f in [audio_file, raw_img, framed_img]:
            if os.path.exists(f):
                os.remove(f)

        if os.path.exists(scene_out) and os.path.getsize(scene_out) > 5000:
            scene_videos.append(scene_out)

    if not scene_videos:
        return None, "কোনো সিন সফলভাবে রেন্ডার করা যায়নি।"

    concat_txt = "concat_list.txt"
    with open(concat_txt, "w", encoding="utf-8") as f:
        for s_file in scene_videos:
            f.write(f"file '{s_file}'\n")

    raw_merged = "merged_temp.mp4"
    res_m = subprocess.run(f'ffmpeg -y -f concat -safe 0 -i "{concat_txt}" -c copy "{raw_merged}"', shell=True, capture_output=True, text=True)

    if res_m.returncode != 0:
        return None, f"ভিডিও মার্জ করতে সমস্যা হয়েছে: {res_m.stderr}"

    final_mp4 = "final_pro_shorts.mp4"
    if add_bgm and os.path.exists(raw_merged):
        bgm_temp = "bgm.mp3"
        subprocess.run(f'ffmpeg -y -f lavfi -i sine=frequency=120:sample_rate=44100 -af "volume=0.03" -t 120 "{bgm_temp}"', shell=True, capture_output=True)
        subprocess.run(f'ffmpeg -y -i "{raw_merged}" -i "{bgm_temp}" -filter_complex amix=inputs=2:duration=first -c:v copy "{final_mp4}"', shell=True, capture_output=True)
        if os.path.exists(bgm_temp):
            os.remove(bgm_temp)
        if os.path.exists(raw_merged):
            os.remove(raw_merged)
    else:
        if os.path.exists(final_mp4):
            os.remove(final_mp4)
        if os.path.exists(raw_merged):
            os.rename(raw_merged, final_mp4)

    for s_file in scene_videos:
        if os.path.exists(s_file):
            os.remove(s_file)
    if os.path.exists(concat_txt):
        os.remove(concat_txt)

    return final_mp4, "OK"

# --- ৮. স্ট্রিমলাইট ইউজার ইন্টারফেস ---
st.title("🎬 Pro AI Shorts Studio")

if not ffmpeg_ok:
    st.error("⚠️ **FFmpeg সিস্টেমে ইনস্টল করা নেই!**")
    st.info("💡 **সমাধান:** আপনার GitHub রিপোজিটরিতে `packages.txt` নামে একটি ফাইল তৈরি করুন এবং তার ভেতর `ffmpeg` লিখে Commit দিন।")

tab_maker, tab_reg, tab_admin = st.tabs(["🎥 শর্টস মেকার", "👤 নতুন অ্যাকাউন্ট", "⚙️ এডমিন প্যানেল"])

# --- TAB 1: শর্টস মেকার ---
with tab_maker:
    u_input = st.text_input("আপনার ইউজারনেম দিন:", key="login_user")
    v_title = st.text_input("ভিডিওর মেইন টাইটেল (উপরে দেখাবে):", placeholder="যেমন: পৃথিবীর ৫টি অবিশ্বাস্য তথ্য 🌍")
    script_input = st.text_area(
        "গল্প/ফ্যাক্টস স্ক্রিপ্ট লিখুন (প্রতি লাইনে ১টি করে সিন):",
        placeholder="১. আমাজন রেইনফরেস্ট পৃথিবীর ২০% অক্সিজেন তৈরি করে।\n২. মহাকাশে কোনো শব্দ শোনা যায় না।\n৩. পেঙ্গুইন সারাজীবনে একজন সঙ্গীর সাথেই থাকে।",
        height=160
    )

    c1, c2 = st.columns(2)
    with c1:
        voice_choice = st.selectbox(
            "ভয়েস সিলেক্ট করুন:",
            [
                "বাংলা - প্রদীপ (ছেলে)",
                "বাংলা - নবনীতা (মেয়ে)",
                "English - Christopher (Male)",
                "English - Ava (Female)"
            ]
        )
    with c2:
        bgm_check = st.checkbox("হালকা ব্যাকগ্রাউন্ড মিউজিক (BGM)", value=True)

    voice_map = {
        "বাংলা - প্রদীপ (ছেলে)": "bn-BD-PradeepNeural",
        "বাংলা - নবনীতা (মেয়ে)": "bn-BD-NabanitaNeural",
        "English - Christopher (Male)": "en-US-ChristopherNeural",
        "English - Ava (Female)": "en-US-AvaNeural"
    }

    if st.button("প্রো শর্টস ভিডিও তৈরি করুন 🚀", use_container_width=True):
        username = u_input.strip()
        if not username:
            st.error("❌ দয়া করে আগে আপনার ইউজারনেম লিখুন!")
        elif not ffmpeg_ok:
            st.error("❌ FFmpeg ইনস্টল না থাকায় ভিডিও তৈরি করা যাচ্ছে না। GitHub-এ packages.txt ফাইলটি যুক্ত করুন।")
        else:
            is_valid, status_msg = verify_user(username)
            if not is_valid:
                st.error(status_msg)
            else:
                lines = [l.strip() for l in script_input.split('\n') if l.strip()]
                if not lines:
                    st.error("⚠️ অনুগ্রহ করে স্ক্রিপ্ট বক্সে অন্তত ১টি লাইন লিখুন!")
                else:
                    voice_code = voice_map[voice_choice]
                    with st.spinner("প্রসেসিং হচ্ছে... মোশন এনিমেশন, টাইটেল ও ভয়েস যোগ করা হচ্ছে..."):
                        out_video, msg = build_pro_shorts(v_title, lines, voice_code, bgm_check)

                        if out_video and os.path.exists(out_video):
                            st.success("🎉 আপনার এনিমেটেড শর্টস ভিডিও সফলভাবে তৈরি হয়ে গেছে!")
                            st.video(out_video)
                            with open(out_video, "rb") as f:
                                st.download_button(
                                    label="এইচডি ভিডিও ডাউনলোড করুন 📥",
                                    data=f,
                                    file_name="pro_ai_shorts.mp4",
                                    mime="video/mp4",
                                    use_container_width=True
                                )
                        else:
                            st.error(f"❌ ভিডিও তৈরির সময় ত্রুটি ধরা পড়েছে:\n\n`{msg}`")

# --- TAB 2: নতুন অ্যাকাউন্ট রেজিস্ট্রেশন ---
with tab_reg:
    st.subheader("নতুন ইউজার রেজিস্ট্রেশন")
    reg_username = st.text_input("ইউজারনেম বাছুন:")
    reg_pass = st.text_input("পাসওয়ার্ড দিন:", type="password")

    if st.button("রেজিস্টার করুন 📝", use_container_width=True):
        u_name = reg_username.strip()
        p_word = reg_pass.strip()
        if u_name and p_word:
            try:
                with sqlite3.connect(DB_NAME) as conn:
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO users VALUES (?, ?, 0)", (u_name, p_word))
                    conn.commit()
                st.success(f"✅ রেজিস্ট্রেশন সফল হয়েছে! আপনার ইউজারনেম: '{u_name}'")
            except sqlite3.IntegrityError:
                st.error("❌ এই ইউজারনেমটি আগে থেকেই রেজিস্টার্ড! অন্য একটি ইউজারনেম চেষ্টা করুন।")
        else:
            st.warning("⚠️ ইউজারনেম এবং পাসওয়ার্ড দুটোই অবশ্যই পূরণ করতে হবে!")

# --- TAB 3: এডমিন কন্ট্রোল প্যানেল ---
with tab_admin:
    st.subheader("⚙️ এডমিন প্যানেল")
    admin_input_pass = st.text_input("এডমিন পাসওয়ার্ড লিখুন:", type="password")

    if admin_input_pass == ADMIN_PASSWORD:
        st.success("🔓 এডমিন এক্সেস অনুমোদিত!")

        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT username, is_blocked FROM users")
            all_users = cursor.fetchall()

        st.write("### 👥 নিবন্ধিত ইউজারদের তালিকা:")
        if all_users:
            table_data = []
            u_names_list = []
            for u in all_users:
                u_name, is_blk = u
                status = "🔴 ব্লকড" if is_blk == 1 else "🟢 অ্যাক্টিভ"
                table_data.append({
                    "ইউজারনেম": u_name,
                    "স্ট্যাটাস": status
                })
                u_names_list.append(u_name)

            st.table(table_data)

            st.write("---")
            st.write("### 🛠️ ইউজার ম্যানেজমেন্ট কন্ট্রোল:")
            selected_user = st.selectbox("ইউজার নির্বাচন করুন:", u_names_list)
            action = st.radio(
                "অ্যাকশন সিলেক্ট করুন:",
                ["ইউজার ডিলিট/রিমুভ করুন ❌", "ব্লক করুন 🔴", "আনব্লক করুন 🟢"]
            )

            if st.button("অ্যাকশন কার্যকর করুন ⚡", use_container_width=True):
                with sqlite3.connect(DB_NAME) as conn:
                    cursor = conn.cursor()
                    if action == "ইউজার ডিলিট/রিমুভ করুন ❌":
                        cursor.execute("DELETE FROM users WHERE username=?", (selected_user,))
                        conn.commit()
                        st.success(f"🗑️ ইউজার '{selected_user}' সফলভাবে ডিলিট করা হয়েছে!")
                    elif action == "ব্লক করুন 🔴":
                        cursor.execute("UPDATE users SET is_blocked=1 WHERE username=?", (selected_user,))
                        conn.commit()
                        st.warning(f"🔴 ইউজার '{selected_user}' ব্লক করা হয়েছে!")
                    elif action == "আনব্লক করুন 🟢":
                        cursor.execute("UPDATE users SET is_blocked=0 WHERE username=?", (selected_user,))
                        conn.commit()
                        st.success(f"🟢 ইউজার '{selected_user}' আনব্লক করা হয়েছে!")

                st.rerun()
        else:
            st.info("এখন পর্যন্ত কোনো ইউজার রেজিস্ট্রেশন করেনি।")
    elif admin_input_pass:
        st.error("❌ ভুল এডমিন পাসওয়ার্ড!")
