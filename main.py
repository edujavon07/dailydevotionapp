import os
import sys
import json
import random
import re
import warnings
import traceback
import datetime
import time
import requests
import base64
import urllib.parse
import threading
import inspect
import asyncio
import shutil
import platform
import hashlib

# Suppress annoying Flet deprecation warnings from the console
warnings.filterwarnings("ignore", category=DeprecationWarning)

# ==========================================
# 1. APP ENVIRONMENT SETUP & SAFE IMPORTS
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
FAVORITES_FILE = os.path.join(DATA_DIR, "favorites.json")

# Ensure the data directory exists for saving files safely
os.makedirs(DATA_DIR, exist_ok=True)

# OS Detector Helper
def is_android():
    return hasattr(sys, 'getandroidapilevel') or 'android' in sys.platform.lower()

# --- SAFE FLET IMPORT WITH AUTO-INSTALLER ---
try:
    import flet as ft
    import requests
except ImportError as e:
    print(f"Missing Library Error: {e}")
    if not is_android():
        print("\nAttempting to automatically install required libraries...")
        try:
            import tkinter as tk
            from tkinter import messagebox
            temp_root = tk.Tk()
            temp_root.withdraw()
            temp_root.attributes('-topmost', True)
            messagebox.showinfo("Installing Dependencies", "Required libraries (like 'flet' and 'requests') are missing on this PC.\n\nDownloading and installing them automatically. This will take a minute. Please wait...")
            temp_root.update()
        except Exception:
            pass
            
        try:
            import subprocess
            subprocess.check_call([sys.executable, "-m", "pip", "install", "setuptools", "flet", "requests", "flet-audio", "pygame-ce"])
            if 'temp_root' in locals():
                temp_root.destroy()
            print("Installation successful! Launching app...")
            import flet as ft
            import requests
        except Exception as ex:
            print(f"\nAuto-install failed: {ex}")
            input("\nPress Enter to close this window...")
            sys.exit(1)
    else:
        sys.exit(1)

# --- CROSS-PLATFORM AUDIO COMPATIBILITY ---
try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

try:
    # Explicit import to ensure Flet compiler sees the audio plugin
    import flet_audio as fta
    AudioControl = fta.Audio
except ImportError:
    AudioControl = None

# --- VIDEO RECORDING LIBRARIES (PC ONLY) ---
try:
    import mss
    import cv2
    import numpy as np
    import imageio_ffmpeg
    VIDEO_EXPORT_AVAILABLE = True
except ImportError as e:
    VIDEO_EXPORT_AVAILABLE = False

# --- EXACT AUDIO DURATION EXTRACTOR ---
def get_audio_duration(file_path, fallback_text):
    if not file_path or not os.path.exists(file_path):
        return len(fallback_text) / 15.0

    try:
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [exe, "-i", file_path]
        startupinfo = None
        if platform.system().lower() == "windows":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, startupinfo=startupinfo)
        match = re.search(r"Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})", result.stderr)
        if match:
            h, m, s = match.groups()
            return int(h)*3600 + int(m)*60 + float(s)
    except: pass
    
    if PYGAME_AVAILABLE:
        try:
            if not pygame.mixer.get_init(): pygame.mixer.init()
            sound = pygame.mixer.Sound(file_path)
            return sound.get_length()
        except: pass
        
    return len(fallback_text) / 15.0

def get_length_instruction(length_str):
    if "Short" in length_str: return "VERY SHORT body (strictly 1 paragraph, maximum of 3 to 4 sentences, keep it concise)"
    elif "Medium" in length_str: return "medium body (strictly 2 paragraphs)"
    elif "Long" in length_str: return "long body (3 to 4 paragraphs)"
    else: return "in-depth body (5 or more paragraphs)"

# ==========================================
# 2. BACKEND LOGIC (GROQ, GEMINI, OPENAI, LM STUDIO)
# ==========================================
class BaseBackend:
    def __init__(self, config_file, service_name):
        self.config_file = config_file
        self.service_name = service_name
        self.keys = self.load_keys()
        self.key_index = 0

    def load_keys(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    return data.get(f"{self.service_name}_keys", [])
            except json.JSONDecodeError: return []
        return []

    def save_keys(self, keys):
        self.keys = keys
        data = {}
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
            except json.JSONDecodeError: pass
        data[f"{self.service_name}_keys"] = self.keys
        try:
            with open(self.config_file, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Failed to save keys: {e}")

    def _build_base_prompt(self, bible_version, theme, custom_instruction, num_days=1, format_type="Standard Devotional"):
        seed_id = random.randint(100000, 999999)
        plural = "s" if num_days > 1 else ""
        
        if format_type == "Standard Devotional": item_name = "everyday Bible devotional"
        elif format_type == "Sermon Outline": item_name = "Sermon Outline"
        elif format_type == "Bible Study Guide": item_name = "Bible Study Guide"
        elif format_type == "Short Story / Parable": item_name = "Christian short story / parable"
        elif format_type == "Poem": item_name = "inspiring Christian poem"
        elif format_type == "Prayer Focus": item_name = "guided prayer session"
        elif format_type == "S.O.A.P. Method": item_name = "S.O.A.P. Bible study"
        elif format_type == "Understanding Format": item_name = "practical 'Understanding' devotional"
        elif format_type == "Declarative Style": item_name = "declarative truth devotion"
        elif format_type == "Journaling / Brain-Dump": item_name = "journaling / brain-dump session"
        elif format_type == "One-Verse Breath Focus": item_name = "one-verse breath focus"
        else: item_name = format_type
        
        base_prompt = f"[SYSTEM UNIQUE ID: {seed_id}]\nYou are a highly creative Christian guide. Generate {num_days} distinct {item_name}{plural} using the '{bible_version}' translation.\n"
        
        if custom_instruction:
            base_prompt += f"SPECIAL INSTRUCTION FROM USER: {custom_instruction}\nCRITICAL: Choose completely unique Bible verses that fit this instruction. DO NOT repeat verses across days.\n\n"
        else:
            if theme.lower() == "random":
                themes = ["hope", "faith", "God's love", "courage", "patience", "forgiveness", "joy", "peace", "grace", "mercy", "strength", "healing", "trusting God", "wisdom", "compassion", "humility", "perseverance", "gratitude", "kindness", "obedience", "overcoming fear", "guidance", "comfort in sorrow", "God's promises", "light in darkness", "fellowship", "worship", "praising God", "The Holy Spirit", "creation", "redemption", "serving Others"]
                selected_theme = random.choice(themes)
                base_prompt += f"Focus all content on the theme of '{selected_theme}'. CRITICAL INSTRUCTION: You MUST select unique verses for each day. Try selecting from different books of the Bible. DO NOT use commonly quoted verses like John 3:16, Jeremiah 29:11, Proverbs 3:5-6, or Philippians 4:13. Find hidden gems.\n\n"
            else:
                base_prompt += f"Focus all content on the theme of '{theme}'. CRITICAL INSTRUCTION: You MUST select completely unique verses for each day. DO NOT use the most commonly quoted verses. Dig deep for unique scriptures.\n\n"
        return base_prompt

    def _build_format_prompt(self, reflection_style, reflection_length, language, num_days=1, format_type="Standard Devotional"):
        lang_instruction = language
        if language == "Taglish":
            lang_instruction = "authentic conversational Filipino Taglish (speak like a modern Pinoy Christian. Mix English and everyday Tagalog naturally. VERY IMPORTANT: Do NOT use deep, archaic, or uncommon Tagalog words like 'saklaw'. If a Tagalog word is too deep or formal, use the English word instead or a very common modern Tagalog equivalent. Use warm terms like 'kapatid', 'Lord', 'Panginoon', and 'blessings')"
        elif language == "Conyo":
            lang_instruction = "stereotypical preppy Filipino 'conyo' speak (speak like a wealthy, preppy modern Pinoy Christian. Heavily mix English and Tagalog in a stereotypical 'conyo' accent. Use phrases like 'make pray', 'so blessed', 'super nice', 'like', 'literally', 'oh my gosh', 'yah', 'diba'. Keep it respectful but undeniably conyo.)"
        
        length_inst = get_length_instruction(reflection_length)
        dates = [(datetime.datetime.now() + datetime.timedelta(days=i)).strftime("%A, %B %d, %Y") for i in range(num_days)]
        format_str = f"For the output, carefully adopt a '{reflection_style}' tone and delivery style. The ENTIRE output MUST be written in {lang_instruction}.\n\n"
        
        if format_type == "Standard Devotional":
            format_rules = (
                "CRITICAL FORMATTING RULE: Provide exactly ONE devotional using these exact headers: 'Date:', 'Verse:', 'Reflection:', and 'Prayer:'.\n"
                "Your output MUST be formatted exactly as follows:\n\n"
                f"Date:\n{dates[0]}\n\n"
                "Verse:\n[Insert EXACTLY ONE Bible Verse and Reference Here]\n\n"
                f"Reflection:\n[Insert a {length_inst} here matching the requested style]\n\n"
                "Prayer:\n[Insert a short prayer here]"
            )
            multi_format_rules = f"CRITICAL FORMATTING RULE: Generate EXACTLY {num_days} devotionals. For EACH day, use these exact headers: 'Date:', 'Verse:', 'Reflection:', and 'Prayer:'. Separate each day with a divider line (---).\n"
        elif format_type == "Sermon Outline":
            format_rules = (
                "CRITICAL FORMATTING RULE: Provide a Sermon Outline using these exact headers: 'Date:', 'Title:', 'Main Text:', 'Introduction:', 'Key Points:', and 'Conclusion:'.\n"
                "Your output MUST be formatted exactly as follows:\n\n"
                f"Date:\n{dates[0]}\n\n"
                "Title:\n[Insert Catchy Sermon Title]\n\n"
                "Main Text:\n[Insert the core Bible verse(s)]\n\n"
                f"Introduction:\n[Insert a short intro]\n\n"
                f"Key Points:\n[Provide 3-4 key points with brief explanations, length should be roughly {length_inst}]\n\n"
                "Conclusion:\n[Insert a powerful closing]"
            )
            multi_format_rules = f"CRITICAL FORMATTING RULE: Generate EXACTLY {num_days} Sermon Outlines. For EACH day, use headers: 'Date:', 'Title:', 'Main Text:', 'Introduction:', 'Key Points:', and 'Conclusion:'. Separate each day with a divider line (---).\n"
        elif format_type == "Bible Study Guide":
            format_rules = (
                "CRITICAL FORMATTING RULE: Provide a Bible Study Guide using these exact headers: 'Date:', 'Passage:', 'Context & Background:', 'Observation Questions:', and 'Application Questions:'.\n"
                "Your output MUST be formatted exactly as follows:\n\n"
                f"Date:\n{dates[0]}\n\n"
                "Passage:\n[Insert Bible Passage]\n\n"
                f"Context & Background:\n[Explain the historical/biblical context briefly]\n\n"
                f"Observation Questions:\n[List 2-3 questions about the text]\n\n"
                f"Application Questions:\n[List 2-3 questions for personal reflection]"
            )
            multi_format_rules = f"CRITICAL FORMATTING RULE: Generate EXACTLY {num_days} Bible Study Guides. For EACH day, use headers: 'Date:', 'Passage:', 'Context & Background:', 'Observation Questions:', 'Application Questions:'. Separate each day with a divider line (---).\n"
        elif format_type == "Short Story / Parable":
            format_rules = (
                "CRITICAL FORMATTING RULE: Write a modern Christian short story or parable illustrating the theme using these exact headers: 'Date:', 'Story Title:', 'Inspired By Verse:', and 'Story:'.\n"
                "Your output MUST be formatted exactly as follows:\n\n"
                f"Date:\n{dates[0]}\n\n"
                "Story Title:\n[Insert Story Title]\n\n"
                "Inspired By Verse:\n[Insert the foundational Bible Verse]\n\n"
                f"Story:\n[Write a {length_inst} engaging short story illustrating the verse's meaning]"
            )
            multi_format_rules = f"CRITICAL FORMATTING RULE: Generate EXACTLY {num_days} Short Stories. For EACH day, use headers: 'Date:', 'Story Title:', 'Inspired By Verse:', and 'Story:'. Separate each day with a divider line (---).\n"
        elif format_type == "Poem":
            format_rules = (
                "CRITICAL FORMATTING RULE: Write an inspiring Christian poem based on the verse/theme using these exact headers: 'Date:', 'Poem Title:', 'Scripture Inspiration:', and 'Poem:'.\n"
                "Your output MUST be formatted exactly as follows:\n\n"
                f"Date:\n{dates[0]}\n\n"
                "Poem Title:\n[Insert Poem Title]\n\n"
                "Scripture Inspiration:\n[Insert the foundational Bible Verse]\n\n"
                f"Poem:\n[Write a touching, rhyming poem]"
            )
            multi_format_rules = f"CRITICAL FORMATTING RULE: Generate EXACTLY {num_days} Poems. For EACH day, use headers: 'Date:', 'Poem Title:', 'Scripture Inspiration:', and 'Poem:'. Separate each day with a divider line (---).\n"
        elif format_type == "Prayer Focus":
            format_rules = (
                "CRITICAL FORMATTING RULE: Provide a deep, guided prayer session using these exact headers: 'Date:', 'Focus Verse:', 'Adoration:', 'Confession:', 'Thanksgiving:', and 'Supplication:'.\n"
                "Your output MUST be formatted exactly as follows:\n\n"
                f"Date:\n{dates[0]}\n\n"
                "Focus Verse:\n[Insert Bible Verse]\n\n"
                "Adoration:\n[Praising God for who He is]\n\n"
                "Confession:\n[Acknowledging our shortcomings]\n\n"
                "Thanksgiving:\n[Thanking God for His blessings]\n\n"
                "Supplication:\n[Presenting requests to God]"
            )
            multi_format_rules = f"CRITICAL FORMATTING RULE: Generate EXACTLY {num_days} Prayer Focus sessions. For EACH day, use headers: 'Date:', 'Focus Verse:', 'Adoration:', 'Confession:', 'Thanksgiving:', 'Supplication:'. Separate each day with a divider line (---).\n"
        elif format_type == "S.O.A.P. Method":
            format_rules = (
                "CRITICAL FORMATTING RULE: Provide exactly ONE devotional using the S.O.A.P. method with these exact headers: 'Date:', 'S - Scripture:', 'O - Observation:', 'A - Application:', and 'P - Prayer:'.\n"
                "Your output MUST be formatted exactly as follows:\n\n"
                f"Date:\n{dates[0]}\n\n"
                "S - Scripture:\n[Insert EXACTLY ONE Bible Verse and Reference Here]\n\n"
                "O - Observation:\n[What is happening in this verse? What is the main message?]\n\n"
                f"A - Application:\n[How does this apply to life today? Provide a {length_inst} here]\n\n"
                "P - Prayer:\n[Write a short prayer asking God to help apply this truth]"
            )
            multi_format_rules = f"CRITICAL FORMATTING RULE: Generate EXACTLY {num_days} S.O.A.P. devotionals. For EACH day, use headers: 'Date:', 'S - Scripture:', 'O - Observation:', 'A - Application:', 'P - Prayer:'. Separate each day with a divider line (---).\n"
        elif format_type == "Understanding Format":
            format_rules = (
                "CRITICAL FORMATTING RULE: Provide exactly ONE devotional using these exact headers: 'Date:', 'The Verse:', 'The Understanding:', 'The Reflection:', and 'The Prayer:'.\n"
                "Your output MUST be formatted exactly as follows:\n\n"
                f"Date:\n{dates[0]}\n\n"
                "The Verse:\n[Insert EXACTLY ONE Bible Verse and Reference Here]\n\n"
                "The Understanding:\n[Break down what the verse actually means in plain English]\n\n"
                f"The Reflection:\n[Connect the meaning to an everyday struggle. Provide a {length_inst} here]\n\n"
                "The Prayer:\n[End with a targeted prayer surrendering that specific struggle to God]"
            )
            multi_format_rules = f"CRITICAL FORMATTING RULE: Generate EXACTLY {num_days} devotionals. For EACH day, use headers: 'Date:', 'The Verse:', 'The Understanding:', 'The Reflection:', 'The Prayer:'. Separate each day with a divider line (---).\n"
        elif format_type == "Declarative Style":
            format_rules = (
                "CRITICAL FORMATTING RULE: Provide exactly ONE declarative devotion using these exact headers: 'Date:', 'Focus Promise:', and 'Declaration:'.\n"
                "Your output MUST be formatted exactly as follows:\n\n"
                f"Date:\n{dates[0]}\n\n"
                "Focus Promise:\n[Insert EXACTLY ONE Bible Verse containing a promise here]\n\n"
                f"Declaration:\n[Write out a powerful, first-person declaration speaking this truth over the day. No deep study, just speaking truth. Length: {length_inst}]"
            )
            multi_format_rules = f"CRITICAL FORMATTING RULE: Generate EXACTLY {num_days} declarative devotions. For EACH day, use headers: 'Date:', 'Focus Promise:', 'Declaration:'. Separate each day with a divider line (---).\n"
        elif format_type == "Journaling / Brain-Dump":
            format_rules = (
                "CRITICAL FORMATTING RULE: Provide exactly ONE journaling devotion using these exact headers: 'Date:', 'The Brain-Dump:', 'The Anchor Verse:', and 'The Exchange:'.\n"
                "Your output MUST be formatted exactly as follows:\n\n"
                f"Date:\n{dates[0]}\n\n"
                "The Brain-Dump:\n[Identify a relatable modern stressor, worry, or heavy thought as if dumping it on a page]\n\n"
                "The Anchor Verse:\n[Insert EXACTLY ONE comforting Bible Verse here]\n\n"
                f"The Exchange:\n[Write how God's truth directly answers the worries dumped above. Length: {length_inst}]"
            )
            multi_format_rules = f"CRITICAL FORMATTING RULE: Generate EXACTLY {num_days} journaling devotions. For EACH day, use headers: 'Date:', 'The Brain-Dump:', 'The Anchor Verse:', 'The Exchange:'. Separate each day with a divider line (---).\n"
        elif format_type == "One-Verse Breath Focus":
            format_rules = (
                "CRITICAL FORMATTING RULE: Provide exactly ONE breath focus devotion using these exact headers: 'Date:', 'Breath Verse:', and 'Actionable Focus:'.\n"
                "Your output MUST be formatted exactly as follows:\n\n"
                f"Date:\n{dates[0]}\n\n"
                "Breath Verse:\n[Insert ONE VERY SHORT Bible Verse here, e.g. Psalm 46:10]\n\n"
                f"Actionable Focus:\n[Provide a short, easy-to-remember focus or mantra for the day. {length_inst}]"
            )
            multi_format_rules = f"CRITICAL FORMATTING RULE: Generate EXACTLY {num_days} breath focus devotions. For EACH day, use headers: 'Date:', 'Breath Verse:', 'Actionable Focus:'. Separate each day with a divider line (---).\n"
        else:
            format_rules = ""
            multi_format_rules = ""

        if num_days == 1: format_str += format_rules
        else: format_str += multi_format_rules + "\nAssigned Dates to use in order:\n" + "\n".join(dates)
        return format_str

class OpenAICompatibleBackend(BaseBackend):
    def __init__(self, config_file, service_name, endpoint):
        super().__init__(config_file, service_name)
        self.endpoint = endpoint

    def _send_request(self, prompt, model, temperature=0.95):
        if not self.keys and self.service_name != "lmstudio":
            return False, f"No API keys found. Please add {self.service_name.capitalize()} API keys in the settings."

        last_error_msg = "Unknown error occurred."
        keys_to_try = self.keys if self.keys else ["dummy_key"]

        for attempt in range(len(keys_to_try)):
            if self.key_index >= len(keys_to_try): 
                self.key_index = 0
            
            current_key = keys_to_try[self.key_index]
            headers = {"Content-Type": "application/json"}
            if self.service_name != "lmstudio": headers["Authorization"] = f"Bearer {current_key.strip()}"
            
            data = {"model": model.strip(), "messages": [{"role": "user", "content": prompt}], "temperature": temperature}

            try:
                import requests
                response = requests.post(self.endpoint, headers=headers, json=data, timeout=25 if self.service_name != "lmstudio" else 300)
                
                if response.status_code == 200:
                    content = response.json()['choices'][0]['message']['content']
                    return True, content
                elif response.status_code == 429:
                    last_error_msg = f"Rate limit (429) hit on Key #{self.key_index + 1}. Auto-rotating..."
                    self.key_index = (self.key_index + 1) % len(keys_to_try)
                    time.sleep(0.5)
                    continue
                else:
                    try: api_err = response.json().get("error", {}).get("message", response.text)
                    except json.JSONDecodeError: api_err = response.text
                    last_error_msg = f"API Error (Status {response.status_code}):\n{api_err}"
                    if response.status_code in [400, 401, 403]:
                        self.key_index = (self.key_index + 1) % len(keys_to_try)
                        continue
                    if self.service_name == "lmstudio": return False, last_error_msg
                    break
            except Exception as e:
                last_error_msg = f"Network error: {e}"
                if self.service_name == "lmstudio": return False, "Could not connect to LM Studio. Ensure it is running on port 1234."
                self.key_index = (self.key_index + 1) % len(keys_to_try)
                continue
                
        return False, f"Failed to process request. All API keys exhausted.\n\nLast error:\n{last_error_msg}"

    def generate_devotional(self, style, version, theme, length, lang, custom_inst, model, duration="1 Day", format_type="Standard Devotional"):
        try: num_days = int(duration.split()[0])
        except: num_days = 1
        prompt = self._build_base_prompt(version, theme, custom_inst, num_days, format_type) + self._build_format_prompt(style, length, lang, num_days, format_type)
        return self._send_request(prompt, model, temperature=0.95)

    def revise_reflection(self, full_content, style, length, lang, custom_inst, model, format_type="Standard Devotional"):
        lang_instruction = lang
        if lang == "Taglish": lang_instruction = "authentic conversational Filipino Taglish"
        elif lang == "Conyo": lang_instruction = "stereotypical preppy Filipino 'conyo' speak"
        length_inst = get_length_instruction(length)
        
        prompt = (
            "You are an inspiring Christian guide.\n"
            f"Please rewrite ONLY the main body/reflection portion(s) of the following {format_type}. "
            f"Carefully adopt a '{style}' tone and provide {length_inst} for each section. "
            f"The ENTIRE output MUST be written in {lang_instruction}.\n\n"
        )
        if custom_inst: prompt += f"SPECIAL INSTRUCTION FROM USER: {custom_inst}\n\n"
        prompt += (
            "CRITICAL: Keep all structural headers exactly the same. Only change the content text. "
            "Output the full, updated document preserving all original formatting and separators.\n\n"
            f"CONTENT TO REVISE:\n{full_content}"
        )
        return self._send_request(prompt, model, temperature=0.8)

    def revise_verse(self, full_content, target_version, model, format_type="Standard Devotional"):
        prompt = (
            "You are a helpful Christian Bible scholar. "
            f"Please update ALL Bible verses in the following {format_type} to use ONLY the '{target_version}' translation.\n\n"
            "CRITICAL: Keep all reflection and structural headers exactly the same. Only change the Verse text and reference. "
            "Output the full, updated document preserving all original formatting and separators.\n\n"
            f"CONTENT TO REVISE:\n{full_content}"
        )
        return self._send_request(prompt, model, temperature=0.7)

    def generate_qa(self, full_content, lang, custom_inst, model, format_type="Standard Devotional"):
        lang_instruction = lang
        if lang == "Taglish": lang_instruction = "authentic conversational Filipino Taglish"
        elif lang == "Conyo": lang_instruction = "stereotypical preppy Filipino 'conyo' speak"
        
        prompt = (
            "You are an inspiring Christian guide.\n"
            f"Based on the following {format_type}, generate 2 to 3 thoughtful reflection questions and their suggested answers.\n"
            f"The ENTIRE output MUST be written in {lang_instruction}.\n\n"
        )
        if custom_inst: prompt += f"SPECIAL INSTRUCTION FROM USER: {custom_inst}\n\n"
        prompt += (
            "CRITICAL: Format your output cleanly with 'Question 1:', 'Answer:', etc. "
            "Output ONLY the questions and answers. Do not repeat the original document.\n\n"
            f"CONTENT:\n{full_content}"
        )
        return self._send_request(prompt, model, temperature=0.7)

class GroqBackend(OpenAICompatibleBackend):
    def __init__(self, config_file): super().__init__(config_file, "groq", "https://api.groq.com/openai/v1/chat/completions")
class OpenAIBackend(OpenAICompatibleBackend):
    def __init__(self, config_file): super().__init__(config_file, "openai", "https://api.openai.com/v1/chat/completions")
class LMStudioBackend(OpenAICompatibleBackend):
    def __init__(self, config_file): super().__init__(config_file, "lmstudio", "http://localhost:1234/v1/chat/completions")

class GeminiBackend(BaseBackend):
    def __init__(self, config_file): super().__init__(config_file, "gemini")

    def _send_request(self, prompt, model, temperature=0.95):
        if not self.keys: return False, "No API keys found. Please add Gemini API keys in the settings."
        last_error_msg = "Unknown error occurred."

        for attempt in range(len(self.keys)):
            if self.key_index >= len(self.keys): self.key_index = 0
            current_key = self.keys[self.key_index]
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model.strip()}:generateContent?key={current_key.strip()}"
            headers = {'Content-Type': 'application/json'}
            data = {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": temperature},
                "safetySettings": [
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
                ]
            }

            try:
                import requests
                response = requests.post(url, headers=headers, json=data, timeout=25)
                if response.status_code == 200:
                    try:
                        candidate = response.json()['candidates'][0]
                        if 'content' in candidate:
                            content = candidate['content']['parts'][0]['text']
                            return True, content
                        else:
                            last_error_msg = f"Gemini blocked the response. Reason: {candidate.get('finishReason', 'Unknown')}"
                            self.key_index = (self.key_index + 1) % len(self.keys)
                            continue
                    except (KeyError, IndexError) as e:
                        last_error_msg = f"Unexpected response format from Gemini: {e}"
                        self.key_index = (self.key_index + 1) % len(self.keys)
                        continue
                elif response.status_code == 429:
                    last_error_msg = f"Rate limit (429) hit on Key #{self.key_index + 1}. Auto-rotating to next key..."
                    self.key_index = (self.key_index + 1) % len(self.keys)
                    time.sleep(0.5)
                    continue 
                else:
                    try: api_err = response.json().get("error", {}).get("message", response.text)
                    except json.JSONDecodeError: api_err = response.text
                    last_error_msg = f"API Error (Status {response.status_code}):\n{api_err}"
                    if response.status_code in [400, 403]:
                        self.key_index = (self.key_index + 1) % len(self.keys)
                        continue
                    if response.status_code == 404: last_error_msg += f"\n\nHint: The model '{model}' may not be available for your region. Try 'gemini-2.5-flash'."
                    break 
            except Exception as e:
                last_error_msg = f"Network error: {e}"
                self.key_index = (self.key_index + 1) % len(self.keys)
                continue 
                
        return False, f"Failed to generate. All API keys exhausted or rate limited.\n\nLast error:\n{last_error_msg}"

    def generate_devotional(self, style, version, theme, length, lang, custom_inst, model, duration="1 Day", format_type="Standard Devotional"):
        try: num_days = int(duration.split()[0])
        except: num_days = 1
        prompt = self._build_base_prompt(version, theme, custom_inst, num_days, format_type) + self._build_format_prompt(style, length, lang, num_days, format_type)
        return self._send_request(prompt, model, temperature=0.95)

    def revise_reflection(self, full_content, style, length, lang, custom_inst, model, format_type="Standard Devotional"):
        lang_instruction = lang
        if lang == "Taglish": lang_instruction = "authentic conversational Filipino Taglish"
        elif lang == "Conyo": lang_instruction = "stereotypical preppy Filipino 'conyo' speak"
        length_inst = get_length_instruction(length)
        
        prompt = (
            "You are an inspiring Christian guide.\n"
            f"Please rewrite ONLY the main body/reflection portion(s) of the following {format_type}. "
            f"Carefully adopt a '{style}' tone and provide {length_inst} for each section. "
            f"The ENTIRE output MUST be written in {lang_instruction}.\n\n"
        )
        if custom_inst: prompt += f"SPECIAL INSTRUCTION FROM USER: {custom_inst}\n\n"
        prompt += (
            "CRITICAL: Keep all structural headers exactly the same. Only change the content text. "
            "Output the full, updated document preserving all original formatting and separators.\n\n"
            f"CONTENT TO REVISE:\n{full_content}"
        )
        return self._send_request(prompt, model, temperature=0.8)

    def revise_verse(self, full_content, target_version, model, format_type="Standard Devotional"):
        prompt = (
            "You are a helpful Christian Bible scholar. "
            f"Please update ALL Bible verses in the following {format_type} to use ONLY the '{target_version}' translation.\n\n"
            "CRITICAL: Keep all reflection and structural headers exactly the same. Only change the Verse text and reference. "
            "Output the full, updated document preserving all original formatting and separators.\n\n"
            f"CONTENT TO REVISE:\n{full_content}"
        )
        return self._send_request(prompt, model, temperature=0.7)

    def generate_qa(self, full_content, lang, custom_inst, model, format_type="Standard Devotional"):
        lang_instruction = lang
        if lang == "Taglish": lang_instruction = "authentic conversational Filipino Taglish"
        elif lang == "Conyo": lang_instruction = "stereotypical preppy Filipino 'conyo' speak"
        
        prompt = (
            "You are an inspiring Christian guide.\n"
            f"Based on the following {format_type}, generate 2 to 3 thoughtful reflection questions and their suggested answers.\n"
            f"The ENTIRE output MUST be written in {lang_instruction}.\n\n"
        )
        if custom_inst: prompt += f"SPECIAL INSTRUCTION FROM USER: {custom_inst}\n\n"
        prompt += (
            "CRITICAL: Format your output cleanly with 'Question 1:', 'Answer:', etc. "
            "Output ONLY the questions and answers. Do not repeat the original document.\n\n"
            f"CONTENT:\n{full_content}"
        )
        return self._send_request(prompt, model, temperature=0.7)

# ==========================================
# 3. TIKTOK TTS ENGINE, VOICEBOX & ELEVENLABS ROUTER
# ==========================================
TIKTOK_VOICES = {
    "US Female 1": "en_us_001", "US Female 2 (Jessie)": "en_us_002", "US Male 1": "en_us_006",
    "US Male 2": "en_us_007", "US Male 3": "en_us_009", "US Male 4": "en_us_010",
    "UK Male 1": "en_uk_001", "UK Male 2": "en_uk_003", "AU Female 1": "en_au_001", "AU Male 1": "en_au_002",
    "Char - Ghostface": "en_us_ghostface", "Char - Chewbacca": "en_us_chewbacca",
    "Char - C3PO": "en_us_c3po", "Char - Stitch": "en_us_stitch", "Char - Stormtrooper": "en_us_stormtrooper",
    "Char - Rocket": "en_us_rocket", "Special - Narrator": "en_male_narration",
    "Special - Funny / Wacky": "en_male_funny", "Special - Peaceful / Emotional": "en_female_emotional",
    "Singing - Alto": "en_female_ht_f08_wonderful_world", "Singing - Tenor": "en_male_m03_lobby",
    "Singing - Warm Breeze": "en_female_f08_salut_damour", "Singing - Sunshine Soon": "en_male_m03_sunshine_soon",
    "Intl - French Female": "fr_002", "Intl - French Male": "fr_001", "Intl - Spanish Male": "es_002",
    "Intl - Spanish (MX) Male": "es_mx_002", "Intl - Portuguese (BR) Female": "br_001",
    "Intl - Portuguese (BR) Male": "br_005", "Intl - German Female": "de_001", "Intl - German Male": "de_002",
    "Intl - Japanese Female": "jp_001", "Intl - Japanese Male": "jp_006", "Intl - Korean Male 1": "kr_002",
    "Intl - Korean Female 1": "kr_003"
}

def generate_tiktok_audio(text, voice_id, session_id, output_path):
    try:
        text = text.replace('\n', ' . ')
        words = text.split(' ')
        chunks, current_chunk = [], ""
        for word in words:
            if len(current_chunk) + len(word) > 200:
                chunks.append(current_chunk.strip())
                current_chunk = word + " "
            else: current_chunk += word + " "
        if current_chunk: chunks.append(current_chunk.strip())
            
        final_audio = b""
        headers = {
            'User-Agent': 'com.zhiliaoapp.musically/2022600030 (Linux; U; Android 7.1.2; en_US; Baidu; Build/N2G48H; Cronet/TTNetVersion:5c20c020 2020-04-23 QuicVersion:0144d358 2020-03-24)',
            'Cookie': f'sessionid={(session_id or "").strip()}'
        }
        for chunk in chunks:
            if not chunk: continue
            req_text = urllib.parse.quote(chunk)
            url = f"https://api16-normal-c-useast1a.tiktokv.com/media/api/text/speech/invoke/?text_speaker={voice_id}&req_text={req_text}&speaker_map_type=0&aid=1233"
            res = requests.post(url, headers=headers, timeout=15)
            if res.status_code == 200:
                data = res.json()
                if data.get("message") == "Couldn't load speech. Try again.": return False, "Invalid TikTok Session ID or Rate Limited."
                vstr = data.get("data", {}).get("v_str")
                if vstr: final_audio += base64.b64decode(vstr)
                else: return False, f"TikTok API error: {data.get('message', 'No audio data')}"
            elif res.status_code in [502, 503, 504]:
                return False, f"TikTok Server Error (HTTP {res.status_code}). The TikTok server is currently overloaded or down. Please wait a few moments and try again, or switch to Voicebox/ElevenLabs."
            else: return False, f"HTTP Error {res.status_code}"
        
        if final_audio:
            with open(output_path, "wb") as f: f.write(final_audio)
            return True, output_path
        return False, "No audio generated."
    except Exception as e: return False, str(e)


def generate_voicebox_audio(text, server_url, voice_preset, selected_engine, output_path, status_callback=None, cancel_callback=None):
    """
    FULLY UNCHUNKED VOICEBOX ENGINE
    Sends 100% of the text in one massive payload. No stitching, no loops.
    Added native cancellation support to instantly stop polling.
    """
    try:
        base_url = (server_url or "").strip().rstrip('/')
        actual_profile_id = (voice_preset or "").strip() if voice_preset else "default"
        actual_engine = selected_engine if selected_engine != "Auto" else None
        
        try:
            profiles_req = requests.get(f"{base_url}/profiles", timeout=5)
            if profiles_req.status_code == 200:
                p_data = profiles_req.json()
                
                items = []
                if isinstance(p_data, list):
                    items = p_data
                elif isinstance(p_data, dict) and "items" in p_data:
                    items = p_data["items"]
                    
                for p in items:
                    if str(p.get("name", "")).lower() == str(actual_profile_id).lower() or str(p.get("id", "")) == str(actual_profile_id):
                        actual_profile_id = p.get("id", actual_profile_id)
                        # Only auto-detect if the user left it on Auto
                        if selected_engine == "Auto" and p.get("engine"):
                            actual_engine = p.get("engine")
                        break
        except Exception: pass 

        endpoint = f"{base_url}/generate"
        
        import re
        vb_text = text.replace('*', '').replace('"', '').replace('[', '').replace(']', '').replace('(', '').replace(')', '').strip()
        
        payload = {"text": vb_text, "profile_id": actual_profile_id}
        if actual_engine: payload["engine"] = actual_engine
        
        is_waiting = [True]
        start_time = time.time()
        
        def progress_tracker():
            while is_waiting[0]:
                if cancel_callback and cancel_callback():
                    break
                elapsed = int(time.time() - start_time)
                if status_callback:
                    status_callback(f"⏳ Voicebox is rendering full audio... Please wait ({elapsed}s)")
                time.sleep(1)
        
        tracker = threading.Thread(target=progress_tracker, daemon=True)
        tracker.start()
        
        try:
            # Submit the ENTIRE script in one massive request (allow 30 mins)
            response = requests.post(endpoint, json=payload, timeout=1800)
            is_waiting[0] = False 
            
            if response.status_code == 200:
                if response.content.startswith(b'RIFF') or response.content.startswith(b'ID3') or response.headers.get('Content-Type', '').startswith('audio/'):
                    with open(output_path, "wb") as f: f.write(response.content)
                    return True, output_path
                
                try:
                    data = response.json()
                    
                    b64 = data.get("audio_base64") or data.get("audio") or data.get("data") or data.get("base64")
                    if b64 and isinstance(b64, str) and len(b64) > 100 and not b64.startswith("http") and not b64.startswith("/") and not b64.startswith("C:\\") and not b64.startswith("D:\\"):
                        import base64
                        with open(output_path, "wb") as f: f.write(base64.b64decode(b64))
                        return True, output_path
                        
                    audio_url = data.get("output_file_path") or data.get("output_file_url") or data.get("url") or data.get("path") or data.get("file_path") or data.get("audio_file") or data.get("file")
                    if not audio_url and isinstance(b64, str) and (b64.startswith("http") or b64.startswith("/") or ":" in b64):
                        audio_url = b64
                        
                    if audio_url:
                        audio_url = audio_url.strip('"').strip("'")
                        if os.path.exists(audio_url): 
                            import shutil
                            shutil.copy2(audio_url, output_path)
                            return True, output_path
                        
                        dl_url = audio_url if audio_url.startswith("http") else f"{base_url}/{audio_url.lstrip('/')}"
                        dl_res = requests.get(dl_url, timeout=120)
                        if dl_res.status_code == 200 and len(dl_res.content) > 100:
                            with open(output_path, "wb") as f: f.write(dl_res.content)
                            return True, output_path
                    
                    gen_id = data.get("id") or data.get("generation_id") or data.get("task_id")
                    if gen_id:
                        is_waiting[0] = True
                        start_time = time.time()
                        tracker = threading.Thread(target=progress_tracker, daemon=True)
                        tracker.start()
                        
                        for attempt in range(900): 
                            # Check if user clicked cancel during the polling loop!
                            if cancel_callback and cancel_callback():
                                is_waiting[0] = False
                                return False, "Canceled by user."
                                
                            try:
                                audio_res = requests.get(f"{base_url}/audio/{gen_id}", timeout=20)
                                if audio_res.status_code == 200 and len(audio_res.content) > 100:
                                    is_waiting[0] = False
                                    with open(output_path, "wb") as f: f.write(audio_res.content)
                                    return True, output_path
                            except requests.exceptions.RequestException: pass
                            time.sleep(2)
                            
                        is_waiting[0] = False
                        return False, "Voicebox Audio Error: Polling timed out after 30 minutes."
                        
                    return False, f"Voicebox Error: Unrecognized API JSON structure: {str(data)[:200]}"
                except Exception as e:
                    return False, f"Voicebox JSON Parse Error: {e}"
            else:
                is_waiting[0] = False
                return False, f"Voicebox API Error: {response.status_code} - {response.text[:100]}"
                
        except requests.exceptions.Timeout:
            is_waiting[0] = False
            return False, "Voicebox Server Error: Generation timed out after 30 minutes."
        except Exception as req_e:
            is_waiting[0] = False
            return False, f"Voicebox Request Error: {req_e}"
            
    except Exception as e:
        return False, f"Voicebox Engine Error: {e}"

def generate_elevenlabs_audio(text, presets, start_preset_name, output_path):
    if not presets: return False, "No ElevenLabs presets found. Please click '⚙️ Manage ElevenLabs Keys' to add your accounts.", start_preset_name

    preset_keys = list(presets.keys())
    start_index = preset_keys.index(start_preset_name) if start_preset_name in preset_keys else 0
    payload = {"text": text, "model_id": "eleven_multilingual_v2", "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}}
    last_error = "Unknown error."

    for attempt in range(len(preset_keys)):
        current_idx = (start_index + attempt) % len(preset_keys)
        active_preset_name = preset_keys[current_idx]
        preset_data = presets[active_preset_name]
        
        if isinstance(preset_data, str):
            active_voice_id, current_key = preset_data, "" 
        else:
            active_voice_id = preset_data.get("voice_id", "")
            current_key = preset_data.get("api_key", "")
            
        if not current_key or not active_voice_id: continue

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{active_voice_id}?output_format=mp3_44100_128"
        headers = {"Accept": "audio/mpeg", "Content-Type": "application/json", "xi-api-key": current_key}
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=300) 
            if response.status_code == 200:
                with open(output_path, "wb") as f: f.write(response.content)
                return True, output_path, active_preset_name 
            elif response.status_code in [401, 403, 429]: 
                last_error = f"Preset '{active_preset_name}' rejected (Out of limits)! Rotating..."
                continue 
            else:
                last_error = f"API Error {response.status_code}: {response.text}"
                break
        except requests.exceptions.ConnectionError:
            last_error = "Connection Refused. Check your internet."
            break
        except Exception as e:
            last_error = f"Network error on '{active_preset_name}': {e}. Trying next preset..."
            continue 

    return False, f"ElevenLabs Failed. All presets exhausted or invalid.\n\nLast error:\n{last_error}", start_preset_name

def generate_fish_speech_audio(text, server_url, presets, start_preset_name, output_path, status_callback=None, cancel_callback=None):
    """
    FULLY RESTORED RAW API INTEGRATION
    Connects to http://127.0.0.1:8080/v1/tts directly. No more Gradio errors!
    """
    if not presets: return False, "No Fish Speech presets found. Please configure them in 'Manage Fish Speech'.", start_preset_name
    if not server_url: return False, "Missing Fish Speech Server URL/Space.", start_preset_name

    base_url = (server_url or "").strip().rstrip('/')
    
    if "0.0.0.0" in base_url:
        base_url = base_url.replace("0.0.0.0", "127.0.0.1")
        
    preset_data = presets.get(start_preset_name, {})
    ref_audio_path = preset_data.get("audio", "")
    ref_text_path = preset_data.get("text", "")

    ref_audio_path = ref_audio_path.strip('\"\'')
    ref_text_path = ref_text_path.strip('\"\'')

    if not ref_audio_path or not os.path.exists(ref_audio_path):
        return False, f"Reference audio not found for preset '{start_preset_name}'. Please verify the path.", start_preset_name

    ref_text_content = ""
    if ref_text_path and os.path.exists(ref_text_path):
        try:
            with open(ref_text_path, "r", encoding="utf-8") as f:
                ref_text_content = f.read().strip()
        except Exception as e:
            pass

    endpoint = f"{base_url}/v1/tts"
    
    is_waiting = [True]
    start_time = time.time()
    
    def progress_tracker():
        while is_waiting[0]:
            if cancel_callback and cancel_callback():
                break
            elapsed = int(time.time() - start_time)
            if status_callback:
                status_callback(f"⏳ Fish Speech is rendering... Please wait ({elapsed}s)")
            time.sleep(1)
    
    tracker = threading.Thread(target=progress_tracker, daemon=True)
    tracker.start()
    
    try:
        import base64
        with open(ref_audio_path, 'rb') as f_audio:
            audio_b64 = base64.b64encode(f_audio.read()).decode('utf-8')
            
        payload = {
             "text": text,
             "format": "wav",
             "references": [
                 {
                     "audio": audio_b64,
                     "text": ref_text_content
                 }
             ],
             "normalize": True
        }
        
        print(f"[Fish Speech] 🌐 Connecting to RAW API Server at {endpoint}...")
        
        headers = {"Content-Type": "application/json"}
        response = requests.post(endpoint, json=payload, headers=headers, timeout=1800)
        is_waiting[0] = False
        
        if response.status_code == 200:
             if response.headers.get('Content-Type', '').startswith('audio/'):
                 with open(output_path, "wb") as out_f: 
                     out_f.write(response.content)
                 return True, output_path, start_preset_name
             else:
                 try:
                     data = response.json()
                     b64 = data.get("audio_base64") or data.get("audio") or data.get("data")
                     if b64:
                         with open(output_path, "wb") as out_f: 
                             out_f.write(base64.b64decode(b64))
                         return True, output_path, start_preset_name
                 except: pass
                 return False, "Fish Speech Error: Unknown API response format.", start_preset_name
        else:
             return False, f"Fish Speech Error: {response.status_code} - {response.text[:200]}", start_preset_name
                 
    except requests.exceptions.ConnectionError:
         is_waiting[0] = False
         return False, f"Connection Refused to {base_url}. Ensure your Fish Speech Server is running.", start_preset_name
    except requests.exceptions.Timeout:
         is_waiting[0] = False
         return False, "Connection Timed Out. The GPU server took more than 30 minutes to respond!", start_preset_name
    except Exception as e:
         is_waiting[0] = False
         return False, f"Fish Speech RAW API Error: {e}", start_preset_name


# ==========================================
# 4. FLET MOBILE GUI
# ==========================================
def format_and_clean(text):
    text = text.replace("**", "")
    text = re.sub(r'(?i)(date|petsa)\s*:', 'Date:', text)
    text = re.sub(r'(?i)(bible verse|verso|bersikulo|talata)\s*:', 'Verse:', text)
    text = re.sub(r'(?i)(pagninilay|repleksyon)\s*:', 'Reflection:', text)
    text = re.sub(r'(?i)(panalangin|dasal)\s*:', 'Prayer:', text)
    headers = ['Date:', 'Verse:', 'Reflection:', 'Prayer:', 'Title:', 'Main Text:', 'Introduction:', 'Key Points:', 'Conclusion:', 'Passage:', 'Context & Background:', 'Observation Questions:', 'Application Questions:', 'Story Title:', 'Inspired By Verse:', 'Story:', 'Poem Title:', 'Scripture Inspiration:', 'Poem:', 'Focus Verse:', 'Adoration:', 'Confession:', 'Thanksgiving:', 'Supplication:', 'Answer:', 'S - Scripture:', 'O - Observation:', 'A - Application:', 'P - Prayer:', 'The Verse:', 'The Understanding:', 'The Reflection:', 'The Prayer:', 'Focus Promise:', 'Declaration:', 'The Brain-Dump:', 'The Anchor Verse:', 'The Exchange:', 'Breath Verse:', 'Actionable Focus:']
    for h in headers:
        text = re.sub(r'([^\n])\s*(' + h + r')', r'\1\n\n\2', text)
        text = re.sub(r'(' + h + r')\s*([^\n])', r'\1\n\2', text)
    text = re.sub(r'([^\n])\s*(Question \d+:)', r'\1\n\n\2', text)
    text = re.sub(r'(Question \d+:)\s*([^\n])', r'\1\n\2', text)
    return text.strip()

def extract_title(content):
    lines = [line.strip() for line in content.split('\n') if line.strip() and not line.startswith('---')]
    for i, line in enumerate(lines):
        if line.startswith("Date:"): return lines[i+1][:37] + "..." if i + 1 < len(lines) and len(lines[i+1]) > 40 else lines[i+1] if i + 1 < len(lines) else ""
        elif line.startswith("Title:") or line.startswith("Story Title:") or line.startswith("Poem Title:"):
            v = line.split(":", 1)[-1].strip()
            return v[:37] + "..." if len(v) > 40 else v
        elif line.startswith("Verse:") or line.startswith("Main Text:") or line.startswith("Passage:") or line.startswith("Focus Verse:") or line.startswith("S - Scripture:") or line.startswith("The Verse:") or line.startswith("Focus Promise:") or line.startswith("The Anchor Verse:") or line.startswith("Breath Verse:"):
            if i + 1 < len(lines):
                v = lines[i+1]
                return v[:37] + "..." if len(v) > 40 else v
    if lines: return lines[0][:37] + "..." if len(lines[0]) > 40 else lines[0]
    return "Saved Document"

def set_window_size(page, w, h):
    if is_android(): return
    try:
        if page.platform == ft.PagePlatform.ANDROID or page.platform == ft.PagePlatform.IOS:
            return
    except: pass
    
    try:
        page.window.width = w
        page.window.height = h
    except:
        try:
            page.window_width = w
            page.window_height = h
        except: pass

def main(page: ft.Page):
    page.title = "Daily Devotional"
    
    # --- THE SAFE AREA / NOTCH FIX ---
    if is_android():
        page.padding = ft.padding.only(top=40, left=5, right=5, bottom=10)
    else:
        try:
            if page.platform == ft.PagePlatform.ANDROID or page.platform == ft.PagePlatform.IOS:
                page.padding = ft.padding.only(top=40, left=5, right=5, bottom=10)
        except: pass
    
    # UI State Dictionary
    app_state = {
        "last_audio_path": "",
        "last_audio_hash": "",
        "is_rendering_audio": False,
        "cancel_render": False,
        "current_render_id": 0
    }
    
    set_window_size(page, 450, 850)
    try:
        if page.platform != ft.PagePlatform.ANDROID and page.platform != ft.PagePlatform.IOS:
            page.window.resizable = False 
            page.window.maximizable = False
            page.window.always_on_top = False
    except Exception: pass
        
    page.scroll = None
    is_audio_playing = [False]
    is_video_recording = [False]
    is_fullscreen = [False]
    current_fullscreen_mode = ["none"]
    selected_fav_idx = [None]
    
    # --- THE DARK THEME FIX ---
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#121212"

    # ==========================================
    # PRE-DECLARE UI ELEMENTS
    # ==========================================
    top_play_btn = ft.TextButton("▶️", tooltip="Play / Stop Audio")
    top_rec_btn = ft.TextButton("⏺️ Rec", tooltip="Record Screen to MP4", style=ft.ButtonStyle(color=ft.Colors.RED_400))
    copy_btn = ft.TextButton("📋", tooltip="Copy Text")

    generate_btn = ft.TextButton("✨ 1 Click Generate Content", width=float('inf'), style=ft.ButtonStyle(bgcolor="#2563EB", color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=8)))
    prompt_gen_btn = ft.TextButton("🧠 Prompt Generate", width=float('inf'), style=ft.ButtonStyle(bgcolor="#374151", color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=8)))
    revise_btn = ft.TextButton("🔄 Revise", width=float('inf'), style=ft.ButtonStyle(bgcolor="#D97706", color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=8)))
    prompt_rev_btn = ft.TextButton("✍️ Prompt Revise", width=float('inf'), style=ft.ButtonStyle(bgcolor="#D97706", color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=8)))
    translate_btn = ft.TextButton("📖 Translate Verse", width=float('inf'), style=ft.ButtonStyle(bgcolor="#059669", color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=8)))
    qa_btn = ft.TextButton("❓ Generate Q&A", width=float('inf'), style=ft.ButtonStyle(bgcolor="#6D28D9", color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=8)))
    tts_btn = ft.TextButton("🔊 Read Aloud", width=float('inf'), style=ft.ButtonStyle(bgcolor="#0284C7", color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=8)))
    save_btn = ft.TextButton("❤️ Save", width=float('inf'), style=ft.ButtonStyle(bgcolor="#B91C1C", color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=8)))
    backup_btn = ft.TextButton("💾 Backup Data", width=float('inf'), style=ft.ButtonStyle(bgcolor="#0F766E", color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=8)))
    restore_btn = ft.TextButton("📂 Restore Data", width=float('inf'), style=ft.ButtonStyle(bgcolor="#0F766E", color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=8)))
    link_audio_btn = ft.TextButton("🔗 Link Existing Audio", width=float('inf'), style=ft.ButtonStyle(bgcolor="#4F46E5", color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=8)))
    
    el_manage_btn = ft.TextButton("⚙️ Manage ElevenLabs Keys", style=ft.ButtonStyle(bgcolor=ft.Colors.GREY_800, color=ft.Colors.WHITE))
    fish_manage_btn = ft.TextButton("🐟 Manage Fish Speech", style=ft.ButtonStyle(bgcolor=ft.Colors.GREY_800, color=ft.Colors.WHITE))
    test_vb_btn = ft.TextButton("🔌 Test PC Voicebox Link", style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE))
    btn_browse_cache = ft.TextButton("📂 Browse")
    btn_clear_cache = ft.TextButton("🗑️ Clear Cache", style=ft.ButtonStyle(color=ft.Colors.RED_400))

    chk_autoplay = ft.Checkbox(label="Auto-Play Audio", value=True)
    chk_force_cache = ft.Checkbox(label="Force Cache Only (Silent if missing)", value=False)
    
    scroll_speed_slider = ft.Slider(min=0, max=100, divisions=100, value=20)
    slider_label = ft.Text(f"{20 / 20.0:.1f}x", size=14, weight="bold", color=ft.Colors.BLUE_400)
    
    fav_list = ft.ListView(spacing=5, expand=True)

    default_welcome_txt = "Welcome!\n\nTap '✨ 1 Click Generate Content' below to receive your daily Verse, Reflection, and Prayer.\n\nYou can also type your own document here manually and tap 'Save ❤️' to keep it."
    
    loaded_text = ""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                loaded_text = json.load(f).get("last_devotion_text", "")
        except Exception: pass
        
    if not loaded_text or not loaded_text.strip():
        loaded_text = default_welcome_txt

    text_area = ft.TextField(
        multiline=True, border_radius=10, border_color=ft.Colors.BLUE_600, border_width=1.5,
        width=float('inf'), expand=True,
        value=loaded_text
    )
    
    fav_text_area = ft.TextField(
        multiline=True, read_only=True, border_radius=10, border_color=ft.Colors.BLUE_600, border_width=1.5,
        width=float('inf'), expand=True, 
        value="Select a favorite document to read here..."
    )
    
    reading_text = ft.Text(value="", size=16, selectable=True, color=ft.Colors.WHITE)
    reading_column = ft.Column([reading_text], scroll="hidden", expand=True)
    reading_container = ft.Container(
        content=reading_column, border_radius=10, border=ft.border.all(1.5, ft.Colors.BLUE_600),
        padding=ft.padding.only(left=20, right=20, top=15, bottom=15), expand=True
    )
    
    text_container_gen = ft.Container(content=text_area, height=380, width=float('inf'), expand=False)
    text_container_fav = ft.Container(content=fav_text_area, height=380, width=float('inf'), expand=False)

    tf_tiktok_session = ft.TextField(label="TikTok Session ID", password=True)
    dd_tiktok_voice = ft.Dropdown(label="TikTok Voice Preset", options=[ft.dropdown.Option(x) for x in TIKTOK_VOICES.keys()])
    tf_voicebox_url = ft.TextField(label="Voicebox PC URL (e.g. http://192.168.1.X:17493)")
    tf_voicebox_preset = ft.TextField(label="Voicebox Preset (Optional)")
    dd_voicebox_engine = ft.Dropdown(label="Voicebox Engine", options=[ft.dropdown.Option(x) for x in ["Auto", "kokoro", "q", "xtts", "piper", "styletts2"]])
    tf_fish_url = ft.TextField(label="Fish Speech Server (Gradio URL or HF Space)")
    tf_cache_dir = ft.TextField(label="Offline Audio Cache Folder (For Backup/Favorites)", expand=True)
    
    dd_format = ft.Dropdown(label="Format / Presentation", options=[ft.dropdown.Option(x) for x in ["Standard Devotional", "Sermon Outline", "Bible Study Guide", "Short Story / Parable", "Poem", "Prayer Focus", "S.O.A.P. Method", "Understanding Format", "Declarative Style", "Journaling / Brain-Dump", "One-Verse Breath Focus"]])
    dd_style = ft.Dropdown(label="Style", options=[ft.dropdown.Option(x) for x in ["Uplifting & Encouraging", "Deep & Theological", "Modern & Practical", "Short & Direct", "Poetic & Contemplative", "Direct person Target"]])
    dd_version = ft.Dropdown(label="Bible Version", options=[ft.dropdown.Option(x) for x in ["NIV (New International Version)", "ESV (English Standard Version)", "KJV (King James Version)", "NLT (New Living Translation)", "Tagalog: Magandang Balita Biblia (MBBTAG)", "Tagalog: Ang Dating Biblia (1905)", "Tagalog: Ang Salita ng Diyos (SND)"]])
    dd_theme = ft.Dropdown(label="Theme", options=[ft.dropdown.Option(x) for x in ["Random", "Hope", "Faith", "God's Love", "Courage", "Patience", "Forgiveness", "Joy", "Peace", "Grace", "Mercy", "Strength", "Healing", "Trusting God", "Wisdom", "Compassion", "Humility", "Perseverance", "Gratitude", "Kindness", "Obedience", "Overcoming Fear", "Guidance", "Comfort in Sorrow", "God's Promises", "Light in Darkness", "Fellowship", "Worship", "Praising God", "The Holy Spirit", "Creation", "Redemption", "Serving Others"]])
    dd_length = ft.Dropdown(label="Length", options=[ft.dropdown.Option(x) for x in ["Short (1 paragraph)", "Medium (2 paragraphs)", "Long (3-4 paragraphs)", "In-Depth (5+ paragraphs)"]])
    dd_lang = ft.Dropdown(label="Language", options=[ft.dropdown.Option(x) for x in ["English", "Native Tagalog", "Taglish", "Conyo"]])
    dd_duration = ft.Dropdown(label="Duration", options=[ft.dropdown.Option(x) for x in ["1 Day", "2 Days", "3 Days", "5 Days", "7 Days (1 Week)"]])
    dd_font = ft.Dropdown(label="Font", options=[ft.dropdown.Option(x) for x in ["Default", "Georgia", "Helvetica", "Arial", "Times New Roman", "Courier", "Verdana", "Trebuchet MS"]])
    dd_size = ft.Dropdown(label="Font Size", options=[ft.dropdown.Option(x) for x in ["12", "14", "15", "16", "18", "20", "22", "24"]])
    dd_tts_engine = ft.Dropdown(label="TTS Engine", options=[ft.dropdown.Option(x) for x in ["TikTok API", "Local PC Voicebox", "ElevenLabs", "Fish Speech"]])
    dd_elevenlabs_preset = ft.Dropdown(label="ElevenLabs Preset", options=[])
    dd_fish_preset = ft.Dropdown(label="Fish Speech Preset", options=[])
    
    ALL_MODELS = [
        "gemini-2.5-flash", "gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro",
        "llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768", "gemma2-9b-it",
        "gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo", "local-model"
    ]
    dd_model = ft.Dropdown(label="AI Model", options=[ft.dropdown.Option(x) for x in ALL_MODELS])
    dd_backend = ft.Dropdown(label="Powered by AI", options=[ft.dropdown.Option(x) for x in ["Groq", "Gemini", "OpenAI", "LM Studio (Local)"]])

    def on_audio_state_changed(e):
        if hasattr(e, 'data') and e.data == "completed":
            is_audio_playing[0] = False
            tts_btn.text = "🔊 Read Aloud"
            tts_btn.style = ft.ButtonStyle(bgcolor="#0284C7", color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=8))
            top_play_btn.text = "▶️"
            
            if current_fullscreen_mode[0] == "none":
                reading_container.border = ft.border.all(1.5, ft.Colors.BLUE_600)
                
            text_container_gen.content = text_area
            
            if is_video_recording[0]:
                is_video_recording[0] = False
            
            try: 
                text_container_gen.update()
                page.update()
            except: pass

    # Initialize Audio Player ONLY if it imported safely
    if AudioControl and not PYGAME_AVAILABLE:
        audio_player = AudioControl(autoplay=False)
        try: audio_player.on_state_changed = on_audio_state_changed
        except Exception: pass
    else: 
        audio_player = None

    groq_backend = GroqBackend(CONFIG_FILE)
    gemini_backend = GeminiBackend(CONFIG_FILE)
    openai_backend = OpenAIBackend(CONFIG_FILE)
    lmstudio_backend = LMStudioBackend(CONFIG_FILE)

    favorites = []
    app_settings = {}
    
    if os.path.exists(FAVORITES_FILE):
        try:
            with open(FAVORITES_FILE, 'r') as f: favorites = json.load(f)
        except json.JSONDecodeError: pass
        
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f: app_settings = json.load(f)
        except json.JSONDecodeError: pass
        
    # --- LOAD SETTINGS TO ELEMENTS ---
    dd_format.value = app_settings.get("format", "Standard Devotional")
    dd_style.value = app_settings.get("style", "Uplifting & Encouraging")
    dd_version.value = app_settings.get("version", "NIV (New International Version)")
    dd_theme.value = app_settings.get("theme", "Random")
    dd_length.value = app_settings.get("length", "Medium (2 paragraphs)")
    dd_lang.value = app_settings.get("lang", "English")
    dd_duration.value = app_settings.get("duration", "1 Day")
    dd_font.value = app_settings.get("font", "Default")
    dd_size.value = app_settings.get("size", "16")
    dd_tts_engine.value = app_settings.get("tts_engine", "TikTok API")
    dd_model.value = app_settings.get("model", "llama-3.3-70b-versatile")
    dd_backend.value = app_settings.get("backend", "Groq")
    
    chk_autoplay.value = app_settings.get("autoplay", True)
    chk_force_cache.value = app_settings.get("force_cache", False)
    
    saved_scroll_speed = app_settings.get("scroll_speed", 20)
    scroll_speed_slider.value = saved_scroll_speed
    slider_label.value = f"{saved_scroll_speed / 20.0:.1f}x"
    
    tf_tiktok_session.value = app_settings.get("tiktok_session_id", "")
    dd_tiktok_voice.value = app_settings.get("tiktok_voice", "US Female 2 (Jessie)")
    tf_voicebox_url.value = app_settings.get("voicebox_url", "")
    tf_voicebox_preset.value = app_settings.get("voicebox_preset", "")
    dd_voicebox_engine.value = app_settings.get("voicebox_engine", "Auto")
    tf_fish_url.value = app_settings.get("fish_url", "http://127.0.0.1:8080")
    tf_cache_dir.value = app_settings.get("audio_cache_dir", os.path.join(DATA_DIR, "audio_cache"))
    
    el_presets_dict = app_settings.get("elevenlabs_presets", {})
    dd_elevenlabs_preset.options = [ft.dropdown.Option(x) for x in el_presets_dict.keys()]
    el_active_val = app_settings.get("elevenlabs_active_preset", "")
    if el_active_val not in el_presets_dict and el_presets_dict: el_active_val = list(el_presets_dict.keys())[0]
    dd_elevenlabs_preset.value = el_active_val

    fish_presets_dict = app_settings.get("fish_presets", {})
    dd_fish_preset.options = [ft.dropdown.Option(x) for x in fish_presets_dict.keys()]
    fish_active_val = app_settings.get("fish_active_preset", "")
    if fish_active_val not in fish_presets_dict and fish_presets_dict: fish_active_val = list(fish_presets_dict.keys())[0]
    dd_fish_preset.value = fish_active_val

    def save_favorites():
        try:
            with open(FAVORITES_FILE, 'w') as f: json.dump(favorites, f, indent=4)
        except Exception as e: print(f"Error saving favorites: {e}")

    def show_snack(msg, color=ft.Colors.GREEN):
        snack = ft.SnackBar(content=ft.Text(msg), bgcolor=color, open=True)
        try:
            if hasattr(page, 'open'): page.open(snack)
            else:
                page.snack_bar = snack
                page.update()
        except Exception as e: print(f"Snackbar Alert: {msg}")

    def show_dialog(dlg):
        if hasattr(page, 'open'): page.open(dlg)
        else:
            if dlg not in page.overlay: page.overlay.append(dlg)
            dlg.open = True
            page.update()

    def hide_dialog(dlg):
        if hasattr(page, 'close'): page.close(dlg)
        else:
            dlg.open = False
            page.update()

    def show_error_dialog(error_msg):
        dlg = ft.AlertDialog(
            title=ft.Text("Alert", color=ft.Colors.RED_400),
            content=ft.Column([
                ft.Text("The provider returned the following message:", size=12),
                ft.TextField(value=error_msg, multiline=True, read_only=True, min_lines=6, max_lines=12, text_size=11)
            ], tight=True),
        )
        dlg.actions = [ft.TextButton("Close", on_click=lambda e: hide_dialog(dlg))]
        show_dialog(dlg)

    def perform_backup(e):
        try:
            chk_settings = ft.Checkbox(label="Include Settings & API Keys", value=True)
            chk_favorites = ft.Checkbox(label="Include Favorites", value=True)
            backup_field = ft.TextField(value="", multiline=True, read_only=True, min_lines=4, max_lines=8, label="Raw Backup Code:")
            file_status_text = ft.Text("", size=11, color=ft.Colors.GREEN_400)

            def generate_backup_str(e=None):
                data_to_save = {}
                if chk_favorites.value:
                    data_to_save["favorites"] = favorites
                
                if chk_settings.value:
                    data_to_save.update({
                        "groq_keys": groq_backend.keys,
                        "gemini_keys": gemini_backend.keys,
                        "openai_keys": openai_backend.keys,
                        "tiktok_session_id": (tf_tiktok_session.value or "").strip(),
                        "tiktok_voice": dd_tiktok_voice.value,
                        "voicebox_url": (tf_voicebox_url.value or "").strip(),
                        "voicebox_preset": (tf_voicebox_preset.value or "").strip(),
                        "voicebox_engine": getattr(dd_voicebox_engine, 'value', "Auto"),
                        "fish_url": (tf_fish_url.value or "").strip(),
                        "tts_engine": dd_tts_engine.value,
                        "autoplay": chk_autoplay.value,
                        "force_cache": chk_force_cache.value,
                        "scroll_speed": scroll_speed_slider.value,
                        "elevenlabs_presets": app_settings.get("elevenlabs_presets", {}),
                        "elevenlabs_active_preset": getattr(dd_elevenlabs_preset, 'value', ""),
                        "fish_presets": app_settings.get("fish_presets", {}),
                        "fish_active_preset": getattr(dd_fish_preset, 'value', ""),
                        "audio_cache_dir": getattr(tf_cache_dir, 'value', "")
                    })
                
                if not data_to_save:
                    backup_field.value = ""
                    file_status_text.value = "⚠️ Nothing selected to backup."
                    try:
                        backup_field.update()
                        file_status_text.update()
                    except: pass
                    return

                backup_str = json.dumps(data_to_save)
                backup_field.value = backup_str
                
                cache_dir = getattr(tf_cache_dir, 'value', "").strip()
                if not cache_dir: cache_dir = DATA_DIR
                os.makedirs(cache_dir, exist_ok=True)
                backup_file_path = os.path.join(cache_dir, "Devotional_Backup.txt")
                
                try:
                    with open(backup_file_path, "w", encoding="utf-8") as bf:
                        bf.write(backup_str)
                    file_status_text.value = f"✅ Auto-saved to:\n{backup_file_path}"
                except Exception as ex:
                    file_status_text.value = f"⚠️ Could not save file: {ex}"
                
                try:
                    backup_field.update()
                    file_status_text.update()
                except: pass

            def copy_backup(e):
                if not backup_field.value:
                    show_snack("Nothing to copy!", ft.Colors.ORANGE)
                    return
                try:
                    if hasattr(page, 'set_clipboard'):
                        page.set_clipboard(backup_field.value)
                    else:
                        import pyperclip
                        pyperclip.copy(backup_field.value)
                    show_snack("Backup code copied to clipboard!", ft.Colors.GREEN)
                except Exception:
                    show_snack("Auto-copy unavailable. Please manually select and copy the text.", ft.Colors.ORANGE)

            chk_settings.on_change = generate_backup_str
            chk_favorites.on_change = generate_backup_str
            
            generate_backup_str()

            dlg = ft.AlertDialog(
                title=ft.Text("Backup & Sync Data"),
                content=ft.Column([
                    ft.Text("Select what to backup:", weight="bold", size=12),
                    chk_settings,
                    chk_favorites,
                    ft.Divider(height=5),
                    file_status_text,
                    ft.Text("To sync across devices, copy this file via Google Drive/USB to your other device's Cache folder.\n\nOr manually copy the code below:", size=11, color=ft.Colors.GREY_300),
                    backup_field
                ], tight=True),
                actions=[
                    ft.TextButton("📋 Copy Code", on_click=copy_backup, style=ft.ButtonStyle(color=ft.Colors.BLUE_400)),
                    ft.TextButton("Close", on_click=lambda e: hide_dialog(dlg))
                ]
            )
            show_dialog(dlg)
        except Exception as ex: show_snack(f"Failed to create backup: {ex}", ft.Colors.RED)

    def perform_restore(e):
        chk_restore_settings = ft.Checkbox(label="Restore Settings & API Keys", value=True)
        chk_restore_favorites = ft.Checkbox(label="Restore Favorites", value=True)
        restore_field = ft.TextField(label="Paste backup code here...", multiline=True, min_lines=4, max_lines=8)
        
        def process_data(restored_data):
            if not chk_restore_settings.value and not chk_restore_favorites.value:
                show_snack("Please select what to restore!", ft.Colors.ORANGE)
                return

            restored_count = 0
            if chk_restore_favorites.value and "favorites" in restored_data:
                favorites.clear()
                favorites.extend(restored_data["favorites"])
                save_favorites()
                refresh_fav_list()
                restored_count += 1
            
            if chk_restore_settings.value:
                if "groq_keys" in restored_data: 
                    groq_backend.keys = restored_data["groq_keys"]
                    groq_backend.save_keys(groq_backend.keys)
                if "gemini_keys" in restored_data: 
                    gemini_backend.keys = restored_data["gemini_keys"]
                    gemini_backend.save_keys(gemini_backend.keys)
                if "openai_keys" in restored_data: 
                    openai_backend.keys = restored_data["openai_keys"]
                    openai_backend.save_keys(openai_backend.keys)
                if "tiktok_session_id" in restored_data: tf_tiktok_session.value = restored_data["tiktok_session_id"]
                if "tiktok_voice" in restored_data: dd_tiktok_voice.value = restored_data["tiktok_voice"]
                if "voicebox_url" in restored_data: tf_voicebox_url.value = restored_data["voicebox_url"]
                if "voicebox_preset" in restored_data: tf_voicebox_preset.value = restored_data["voicebox_preset"]
                if "voicebox_engine" in restored_data: dd_voicebox_engine.value = restored_data["voicebox_engine"]
                if "fish_url" in restored_data: tf_fish_url.value = restored_data["fish_url"]
                if "tts_engine" in restored_data: dd_tts_engine.value = restored_data["tts_engine"]
                if "autoplay" in restored_data: chk_autoplay.value = restored_data["autoplay"]
                if "force_cache" in restored_data: chk_force_cache.value = restored_data["force_cache"]
                if "scroll_speed" in restored_data: scroll_speed_slider.value = restored_data["scroll_speed"]
                if "elevenlabs_presets" in restored_data: app_settings["elevenlabs_presets"] = restored_data["elevenlabs_presets"]
                if "elevenlabs_active_preset" in restored_data: dd_elevenlabs_preset.value = restored_data["elevenlabs_active_preset"]
                if "fish_presets" in restored_data: app_settings["fish_presets"] = restored_data["fish_presets"]
                if "fish_active_preset" in restored_data: dd_fish_preset.value = restored_data["fish_active_preset"]
                if "audio_cache_dir" in restored_data: tf_cache_dir.value = restored_data["audio_cache_dir"]
                
                save_app_settings()
                refresh_el_dropdown()
                refresh_fish_dropdown()
                restored_count += 1
            
            hide_dialog(dlg)
            if restored_count > 0:
                show_snack("Selected data synced & restored successfully!", ft.Colors.GREEN)
            else:
                show_snack("No matching data found in backup.", ft.Colors.ORANGE)
            page.update()

        def process_restore_text(e):
            try:
                val = restore_field.value or ""
                if not val.strip():
                    show_snack("Please paste a backup code first.", ft.Colors.ORANGE)
                    return
                restored_data = json.loads(val.strip())
                process_data(restored_data)
            except Exception as ex: show_snack("Invalid backup text format!", ft.Colors.RED)

        def process_restore_file(e):
            cache_dir = getattr(tf_cache_dir, 'value', "").strip()
            if not cache_dir: cache_dir = DATA_DIR
            backup_file_path = os.path.join(cache_dir, "Devotional_Backup.txt")
            if os.path.exists(backup_file_path):
                try:
                    with open(backup_file_path, "r", encoding="utf-8") as bf:
                        restored_data = json.load(bf)
                    process_data(restored_data)
                except Exception as ex:
                    show_snack(f"Error reading file: {ex}", ft.Colors.RED)
            else:
                show_snack(f"No Devotional_Backup.txt found in:\n{cache_dir}", ft.Colors.ORANGE)

        dlg = ft.AlertDialog(
            title=ft.Text("Restore / Sync Data"),
            content=ft.Column([
                ft.Text("Select what to restore:", weight="bold", size=12),
                chk_restore_settings,
                chk_restore_favorites,
                ft.Divider(height=5),
                ft.Text("Load from 'Devotional_Backup.txt' in your Cache Folder:", size=11, color=ft.Colors.GREY_300),
                ft.TextButton("📂 Sync from File", on_click=process_restore_file, style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE)),
                ft.Divider(),
                ft.Text("Or paste your backup code manually below:", size=11, color=ft.Colors.GREY_300), 
                restore_field
            ], tight=True),
            actions=[
                ft.TextButton("Restore from Text", on_click=process_restore_text, style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE)), 
                ft.TextButton("Cancel", on_click=lambda e: hide_dialog(dlg))
            ]
        )
        show_dialog(dlg)

    pr = ft.ProgressRing(width=16, height=16, stroke_width=2, visible=False)
    status_text = ft.Text("Ready", color=ft.Colors.GREY_400, size=12)
    is_processing = [False]

    def set_loading(is_loading, msg="Ready", is_rendering_audio=False):
        is_processing[0] = is_loading
        pr.visible = is_loading
        status_text.value = msg
        
        generate_btn.disabled = is_loading
        prompt_gen_btn.disabled = is_loading
        revise_btn.disabled = is_loading
        prompt_rev_btn.disabled = is_loading
        translate_btn.disabled = is_loading
        qa_btn.disabled = is_loading
        
        if not is_audio_playing[0]:
            if is_rendering_audio:
                tts_btn.disabled = False
                tts_btn.text = "⏹️ Cancel Render"
                tts_btn.style = ft.ButtonStyle(bgcolor=ft.Colors.RED_700, color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=8))
                
                top_play_btn.disabled = False
                top_play_btn.text = "⏹️"
            else:
                tts_btn.disabled = is_loading
                tts_btn.text = "🔊 Read Aloud"
                tts_btn.style = ft.ButtonStyle(bgcolor="#0284C7", color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=8))
                
                top_play_btn.disabled = is_loading
                top_play_btn.text = "▶️"
                
            top_rec_btn.disabled = is_loading
            chk_autoplay.disabled = is_loading
            chk_force_cache.disabled = is_loading
            el_manage_btn.disabled = is_loading
            fish_manage_btn.disabled = is_loading
            link_audio_btn.disabled = is_loading
        
        try: page.update()
        except: pass

    # --- SAFE ASYNC RUNNER FOR AUTO-SCROLL ---
    def safe_fire_scroll(delta_val):
        async def _execute_scroll():
            try:
                res = reading_column.scroll_to(offset=delta_val, duration=500)
                if inspect.iscoroutine(res):
                    await res
                reading_column.update()
            except Exception: pass
            
        if hasattr(page, 'run_task'):
            page.run_task(_execute_scroll)
        else:
            try:
                res = reading_column.scroll_to(offset=delta_val, duration=500)
                if inspect.iscoroutine(res):
                    asyncio.run(res)
                reading_column.update()
            except Exception: pass

    def save_app_settings(e=None):
        try:
            data = {}
            if os.path.exists(CONFIG_FILE):
                try:
                    with open(CONFIG_FILE, 'r') as f: data = json.load(f)
                except Exception: pass
            
            if hasattr(dd_format, 'value'): data["format"] = dd_format.value
            if hasattr(dd_style, 'value'): data["style"] = dd_style.value
            if hasattr(dd_version, 'value'): data["version"] = dd_version.value
            if hasattr(dd_theme, 'value'): data["theme"] = dd_theme.value
            if hasattr(dd_length, 'value'): data["length"] = dd_length.value
            if hasattr(dd_lang, 'value'): data["lang"] = dd_lang.value
            if hasattr(dd_duration, 'value'): data["duration"] = dd_duration.value
            if hasattr(dd_font, 'value'): data["font"] = dd_font.value
            if hasattr(dd_size, 'value'): data["size"] = dd_size.value
            if hasattr(dd_model, 'value'): data["model"] = dd_model.value
            if hasattr(dd_backend, 'value'): data["backend"] = dd_backend.value
            if hasattr(dd_tts_engine, 'value'): data["tts_engine"] = dd_tts_engine.value
            if hasattr(tf_tiktok_session, 'value'): data["tiktok_session_id"] = tf_tiktok_session.value.strip()
            if hasattr(dd_tiktok_voice, 'value'): data["tiktok_voice"] = dd_tiktok_voice.value
            if hasattr(tf_voicebox_url, 'value'): data["voicebox_url"] = tf_voicebox_url.value.strip()
            if hasattr(tf_voicebox_preset, 'value'): data["voicebox_preset"] = tf_voicebox_preset.value.strip()
            if hasattr(dd_voicebox_engine, 'value'): data["voicebox_engine"] = dd_voicebox_engine.value
            if hasattr(tf_fish_url, 'value'): data["fish_url"] = tf_fish_url.value.strip()
            if hasattr(chk_autoplay, 'value'): data["autoplay"] = chk_autoplay.value
            if hasattr(chk_force_cache, 'value'): data["force_cache"] = chk_force_cache.value
            if hasattr(scroll_speed_slider, 'value'): data["scroll_speed"] = scroll_speed_slider.value
            if hasattr(tf_cache_dir, 'value'): data["audio_cache_dir"] = tf_cache_dir.value
            
            try:
                if 'text_area' in locals() or 'text_area' in globals() or hasattr(text_area, 'value'):
                    current_val = text_area.value
                    if current_val and not current_val.startswith("Welcome!"):
                        data["last_devotion_text"] = current_val
                    elif "last_devotion_text" in data:
                        pass
            except Exception: pass
            
            with open(CONFIG_FILE, 'w') as f: json.dump(data, f, indent=4)
        except Exception as err:
            pass

    def on_text_changed(e):
        app_state["last_audio_path"] = ""
        app_state["last_audio_hash"] = ""
        save_app_settings() 

    def browse_cache_dir(e):
        if is_android():
            android_path = "/storage/emulated/0/Documents/DailyDevotional"
            try:
                os.makedirs(android_path, exist_ok=True)
                tf_cache_dir.value = android_path
                save_app_settings()
                try: tf_cache_dir.update()
                except: pass
                show_snack("Cache folder set to Android Documents!", ft.Colors.GREEN)
            except Exception as ex:
                show_snack(f"Permission Denied. Could not create folder: {ex}", ft.Colors.RED)
            return

        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            selected_dir = filedialog.askdirectory(
                parent=root,
                title="Select Offline Audio Cache Folder",
                initialdir=tf_cache_dir.value
            )
            root.destroy()
            
            if selected_dir:
                tf_cache_dir.value = selected_dir
                save_app_settings()
                try: tf_cache_dir.update()
                except: pass
        except Exception as ex:
            show_snack(f"Browse Error: {ex}", ft.Colors.RED)
            
    def clear_cache_dir(e):
        cache_dir = getattr(tf_cache_dir, 'value', "").strip()
        if os.path.exists(cache_dir):
            try:
                count = 0
                for f in os.listdir(cache_dir):
                    if f.endswith(".mp3") or f.endswith(".wav"):
                        os.remove(os.path.join(cache_dir, f))
                        count += 1
                show_snack(f"Cleared {count} orphaned audio cache files!", ft.Colors.GREEN)
                page.update()
            except Exception as ex:
                show_snack(f"Error clearing cache: {ex}", ft.Colors.RED)
                page.update()
        else:
            show_snack("Cache folder is already empty.", ft.Colors.ORANGE)
            page.update()

    def open_el_dialog(e):
        el_list = ft.Column(spacing=5, height=150, scroll="auto")
        lbl_status = ft.Text("", color=ft.Colors.CYAN, size=12)
        
        def refresh_el_list():
            el_list.controls.clear()
            presets = app_settings.get("elevenlabs_presets", {})
            for name, data in presets.items():
                k = data.get("api_key", "")
                masked_k = f"{k[:4]}...{k[-4:]}" if len(k) > 8 else "No Key"
                def make_delete(n): return lambda e: delete_el_preset(n)
                row = ft.Row([ft.Text(f"{name} ({masked_k})", expand=True, size=12), ft.TextButton("❌", on_click=make_delete(name), width=40)])
                el_list.controls.append(row)
            try: el_list.update()
            except: pass

        def delete_el_preset(name):
            try:
                presets = app_settings.get("elevenlabs_presets", {})
                if name in presets:
                    del presets[name]
                    app_settings["elevenlabs_presets"] = presets
                    save_app_settings()
                    refresh_el_dropdown()
                    refresh_el_list()
                    lbl_status.value = f"Preset '{name}' deleted."
                    lbl_status.color = ft.Colors.ORANGE
                    dlg.update()
            except Exception as ex:
                lbl_status.value = f"Delete Error: {ex}"
                lbl_status.color = ft.Colors.RED
                dlg.update()

        name_tf = ft.TextField(label="Preset Name (e.g. Account1)", height=40, value="")
        id_tf = ft.TextField(label="Voice ID", height=40, value="")
        key_tf = ft.TextField(label="API Key", password=True, height=40, value="")

        def add_el_preset(e):
            try:
                n = (name_tf.value or "").strip()
                vid = (id_tf.value or "").strip()
                k = (key_tf.value or "").strip()
                
                if not n or not vid or not k:
                    lbl_status.value = "Error: All fields are required."
                    lbl_status.color = ft.Colors.RED
                    dlg.update()
                    return
                    
                presets = app_settings.get("elevenlabs_presets", {})
                presets[n] = {"voice_id": vid, "api_key": k}
                app_settings["elevenlabs_presets"] = presets
                save_app_settings()
                
                dd_elevenlabs_preset.options = [ft.dropdown.Option(opt) for opt in presets.keys()]
                if n in [opt.key for opt in dd_elevenlabs_preset.options]:
                    dd_elevenlabs_preset.value = n
                    
                dd_elevenlabs_preset.update()
                
                name_tf.value = ""
                id_tf.value = ""
                key_tf.value = ""
                
                lbl_status.value = f"Preset '{n}' saved successfully!"
                lbl_status.color = ft.Colors.GREEN
                
                refresh_el_list()
                dlg.update()
                page.update()
            except Exception as ex:
                lbl_status.value = f"Error saving preset: {ex}"
                lbl_status.color = ft.Colors.RED
                dlg.update()

        dlg = ft.AlertDialog(
            title=ft.Text("ElevenLabs Presets"),
            content=ft.Column([
                ft.Text("Add multiple burner accounts. App auto-rotates if limits hit.", size=11, color=ft.Colors.GREY_400),
                el_list, name_tf, id_tf, key_tf,
                lbl_status,
                ft.TextButton("💾 Save Preset", on_click=add_el_preset, style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE))
            ], tight=True),
            actions=[ft.TextButton("Close", on_click=lambda e: hide_dialog(dlg))]
        )
        refresh_el_list()
        show_dialog(dlg)
        
    def refresh_el_dropdown():
        try:
            presets = app_settings.get("elevenlabs_presets", {})
            dd_elevenlabs_preset.options = [ft.dropdown.Option(k) for k in presets.keys()]
            valid_keys = [opt.key for opt in dd_elevenlabs_preset.options]
            if dd_elevenlabs_preset.value not in valid_keys:
                dd_elevenlabs_preset.value = valid_keys[0] if valid_keys else None
            dd_elevenlabs_preset.update()
            page.update()
        except Exception as ex: pass

    def open_fish_dialog(e):
        fish_list = ft.Column(spacing=5, height=150, scroll="auto")
        lbl_status = ft.Text("", color=ft.Colors.CYAN, size=12)
        
        def refresh_fish_list():
            fish_list.controls.clear()
            presets = app_settings.get("fish_presets", {})
            for name, data in presets.items():
                p_aud = data.get("audio", "")
                masked_p = f"...{p_aud[-15:]}" if len(p_aud) > 15 else p_aud
                def make_delete(n): return lambda e: delete_fish_preset(n)
                row = ft.Row([
                    ft.Text(f"{name} ({masked_p})", expand=True, size=12), 
                    ft.TextButton("❌", on_click=make_delete(name), width=40)
                ])
                fish_list.controls.append(row)
            try: fish_list.update()
            except: pass

        def delete_fish_preset(name):
            try:
                presets = app_settings.get("fish_presets", {})
                if name in presets:
                    del presets[name]
                    app_settings["fish_presets"] = presets
                    save_app_settings()
                    refresh_fish_dropdown()
                    refresh_fish_list()
                    lbl_status.value = f"Fish Preset '{name}' deleted."
                    lbl_status.color = ft.Colors.ORANGE
                    dlg.update()
            except Exception as ex:
                lbl_status.value = f"Delete Error: {ex}"
                lbl_status.color = ft.Colors.RED
                dlg.update()

        fish_name_tf = ft.TextField(label="Preset Name (e.g. MyVoice)", height=40, value="")
        fish_audio_tf = ft.TextField(label="Ref Audio Path (.wav)", height=40, value="")
        fish_text_tf = ft.TextField(label="Ref Text Path (.txt) [Optional]", height=40, value="")

        def add_fish_preset(e):
            try:
                n = (fish_name_tf.value or "").strip()
                audio_path = (fish_audio_tf.value or "").strip().strip('"').strip("'")
                text_path = (fish_text_tf.value or "").strip().strip('"').strip("'")
                
                if not n or not audio_path:
                    lbl_status.value = "Error: Preset Name & Audio Path required."
                    lbl_status.color = ft.Colors.RED
                    dlg.update()
                    return
                    
                presets = app_settings.get("fish_presets", {})
                presets[n] = {"audio": audio_path, "text": text_path}
                app_settings["fish_presets"] = presets
                
                save_app_settings()
                
                dd_fish_preset.options = [ft.dropdown.Option(opt) for opt in presets.keys()]
                if n in [opt.key for opt in dd_fish_preset.options]:
                    dd_fish_preset.value = n
                    
                dd_fish_preset.update()
                
                fish_name_tf.value = ""
                fish_audio_tf.value = ""
                fish_text_tf.value = ""
                
                lbl_status.value = f"Preset '{n}' saved successfully!"
                lbl_status.color = ft.Colors.GREEN
                
                refresh_fish_list()
                dlg.update()
                page.update()
            except Exception as ex:
                lbl_status.value = f"Error saving preset: {ex}"
                lbl_status.color = ft.Colors.RED
                dlg.update()

        dlg = ft.AlertDialog(
            title=ft.Text("Fish Speech Presets"),
            content=ft.Column([
                ft.Text("Paste local file paths to clone voices. (Shift+Right-Click file -> Copy as path)", size=11, color=ft.Colors.GREY_400),
                ft.Text("💡 Hint: Fish Speech clones the EXACT accent of your audio file.\nFor an American accent, use an American speaker's .wav!", size=11, color=ft.Colors.AMBER_400),
                fish_list, fish_name_tf, fish_audio_tf, fish_text_tf,
                lbl_status,
                ft.TextButton("💾 Save Preset", on_click=add_fish_preset, style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE))
            ], tight=True),
            actions=[ft.TextButton("Close", on_click=lambda e: hide_dialog(dlg))]
        )
        refresh_fish_list()
        show_dialog(dlg)
        
    def refresh_fish_dropdown():
        try:
            presets = app_settings.get("fish_presets", {})
            dd_fish_preset.options = [ft.dropdown.Option(k) for k in presets.keys()]
            valid_keys = [opt.key for opt in dd_fish_preset.options]
            if dd_fish_preset.value not in valid_keys:
                dd_fish_preset.value = valid_keys[0] if valid_keys else None
            dd_fish_preset.update()
            page.update()
        except Exception as ex: pass

    def test_voicebox_conn(e):
        url = (tf_voicebox_url.value or "").strip().rstrip('/')
        if not url: return show_snack("Please enter a Voicebox URL first.", ft.Colors.RED)
        if is_android() and ("127.0.0.1" in url or "localhost" in url):
            return show_error_dialog("⚠️ You cannot use 127.0.0.1 or localhost on a phone!\n\nThat points to the phone itself. You must use your PC's actual Wi-Fi IP Address (e.g., http://192.168.1.5:17493).")
            
        set_loading(True, "Testing connection...")
        def worker():
            try:
                res = requests.get(f"{url}/profiles", timeout=5)
                def update_ui():
                    set_loading(False)
                    if res.status_code == 200:
                        data = res.json()
                        count = len(data) if isinstance(data, list) else len(data.get("items", []))
                        show_snack(f"✅ Success! Connected to Voicebox ({count} voices found).", ft.Colors.GREEN)
                    else:
                        show_snack(f"⚠️ Connected, but API returned status {res.status_code}.", ft.Colors.ORANGE)
                if hasattr(page, 'call_after'): page.call_after(update_ui)
                else: update_ui()
            except Exception as ex:
                def handle_err():
                    set_loading(False)
                    show_snack(f"❌ Connection Error: {ex}", ft.Colors.RED)
                if hasattr(page, 'call_after'): page.call_after(handle_err)
                else: handle_err()
                
        threading.Thread(target=worker, daemon=True).start()

    def handle_window_event(e):
        if e.data == "close":
            save_app_settings()
            page.window.destroy()
            
    try:
        page.window.prevent_close = True
        page.window.on_event = handle_window_event
    except Exception: pass
    
    page.on_disconnect = lambda e: save_app_settings()
            
    def on_simple_setting_change(e): save_app_settings()
        
    for dd in [dd_format, dd_style, dd_theme, dd_length, dd_lang, dd_duration, dd_tts_engine, chk_autoplay, chk_force_cache, tf_tiktok_session, dd_tiktok_voice, tf_voicebox_url, tf_voicebox_preset, dd_voicebox_engine, dd_elevenlabs_preset, dd_fish_preset, tf_fish_url]:
        dd.on_change = save_app_settings

    def update_font(e=None):
        family = dd_font.value if dd_font.value != "Default" else None
        try: size = int(dd_size.value)
        except ValueError: size = 16
        
        # 1. Standard size property overrides
        text_area.text_size = size
        fav_text_area.text_size = size
        reading_text.size = size
        
        # 2. Standard family property overrides
        reading_text.font_family = family
        
        # 3. Deep Flet TextStyle Object overrides (Safely wrapped)
        try:
            ts = ft.TextStyle(size=size, font_family=family) if family else ft.TextStyle(size=size)
            text_area.text_style = ts
            fav_text_area.text_style = ts
            reading_text.style = ts
        except Exception: 
            pass
            
        if e is not None:
            save_app_settings()
            try:
                # Force everything to repaint completely
                text_area.update()
                fav_text_area.update()
                try: reading_text.update()
                except: pass
                page.update()
                show_snack(f"Font updated to {dd_font.value} (Size {size})", ft.Colors.GREEN)
            except Exception: pass

    dd_font.on_change = update_font
    dd_size.on_change = update_font

    def get_active_backend():
        b = dd_backend.value
        if b == "LM Studio (Local)": return lmstudio_backend
        elif b == "Gemini": return gemini_backend
        elif b == "OpenAI": return openai_backend
        return groq_backend

    def on_backend_change(e):
        b = dd_backend.value
        if b == "Groq": dd_model.value = "llama-3.3-70b-versatile"
        elif b == "Gemini": dd_model.value = "gemini-2.5-flash" 
        elif b == "OpenAI": dd_model.value = "gpt-4o-mini"
        else: dd_model.value = "local-model"
        page.update()
        save_app_settings()

    def on_model_change(e):
        m = dd_model.value
        if "gemini" in m: dd_backend.value = "Gemini"
        elif "gpt" in m: dd_backend.value = "OpenAI"
        elif m == "local-model": dd_backend.value = "LM Studio (Local)"
        else: dd_backend.value = "Groq"
        page.update()
        save_app_settings()

    def on_apply_verse(e=None):
        try:
            save_app_settings()
            if is_processing[0]: return
            content = text_area.value
            
            if not content or content.startswith("Welcome!"):
                if e is not None:
                    show_snack("Generate a devotional first before changing the Bible version.", ft.Colors.ORANGE)
                return

            set_loading(True, "Translating Verse...")
            version_val = dd_version.value
            model_val = dd_model.value
            fmt_val = dd_format.value
            backend = get_active_backend()
            
            def worker():
                try:
                    success, new_content = backend.revise_verse(content, version_val, model_val, fmt_val)
                    
                    def update_ui():
                        set_loading(False)
                        if success:
                            text_area.value = format_and_clean(new_content)
                            reading_text.value = text_area.value 
                            save_app_settings() # Auto-Save!
                            show_snack("Verse translated successfully!", ft.Colors.GREEN)
                            
                            try: 
                                text_area.update()
                                page.update()
                            except Exception: pass
                            
                            if chk_autoplay.value:
                                threading.Timer(0.5, lambda: page.call_after(on_play_tts) if hasattr(page, 'call_after') else on_play_tts()).start()
                        else:
                            show_error_dialog(new_content)
                            show_snack("Error applying Bible version.", ft.Colors.RED)
                            page.update()
                            
                    if hasattr(page, 'call_after'): page.call_after(update_ui)
                    else: update_ui()
                    
                except Exception as ex:
                    def handle_err():
                        set_loading(False)
                        show_snack(f"Translation error: {ex}", ft.Colors.RED)
                        page.update()
                    if hasattr(page, 'call_after'): page.call_after(handle_err)
                    else: handle_err()
                    
            threading.Thread(target=worker, daemon=True).start()
        except Exception as ex:
            print(f"Apply verse error: {ex}")

    def execute_generation(custom_instruction=""):
        if is_processing[0]: return
        set_loading(True, f"Generating {dd_format.value}...")
        
        style_val, ver_val, theme_val, len_val, lang_val, model_val, dur_val, fmt_val = dd_style.value, dd_version.value, dd_theme.value, dd_length.value, dd_lang.value, dd_model.value, dd_duration.value, dd_format.value
        backend = get_active_backend()
        
        def worker():
            try:
                success, content = backend.generate_devotional(style_val, ver_val, theme_val, len_val, lang_val, custom_instruction, model_val, dur_val, fmt_val)
                
                def update_ui():
                    set_loading(False)
                    if success:
                        text_area.value = format_and_clean(content)
                        reading_text.value = text_area.value
                        save_app_settings() # Auto-Save!
                        show_snack("Content generated successfully!", ft.Colors.GREEN)
                        
                        try: 
                            text_area.update()
                            page.update() 
                        except Exception: pass
                        
                        if chk_autoplay.value:
                            threading.Timer(0.5, lambda: page.call_after(on_play_tts) if hasattr(page, 'call_after') else on_play_tts()).start()
                    else:
                        show_error_dialog(content)
                        show_snack("Failed to generate.", ft.Colors.RED)
                        page.update()
                        
                if hasattr(page, 'call_after'): page.call_after(update_ui)
                else: update_ui()
                
            except Exception as ex:
                def handle_err():
                    set_loading(False)
                    show_snack(f"Generation error: {ex}", ft.Colors.RED)
                    page.update()
                if hasattr(page, 'call_after'): page.call_after(handle_err)
                else: handle_err()
                
        threading.Thread(target=worker, daemon=True).start()

    def on_generate(e): execute_generation()

    def open_generate_ai_dialog(e):
        prompt_field = ft.TextField(label="Custom Instruction (e.g., 'Focus on strength')")
        def submit_dlg(e):
            hide_dialog(dlg)
            if prompt_field.value and prompt_field.value.strip(): execute_generation(prompt_field.value.strip())
        
        dlg = ft.AlertDialog(
            title=ft.Text("Generate with AI Prompt"), content=prompt_field,
            actions=[ft.TextButton("Cancel", on_click=lambda e: hide_dialog(dlg)), ft.TextButton("Generate", on_click=submit_dlg, style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE, color=ft.Colors.WHITE))]
        )
        show_dialog(dlg)

    def execute_revision(custom_instruction=""):
        if is_processing[0]: return
        content = text_area.value
        if not content or content.startswith("Welcome!"): return show_snack("Please generate a document first.", ft.Colors.RED)

        set_loading(True, "Revising content...")
        style_val, len_val, lang_val, model_val, fmt_val = dd_style.value, dd_length.value, dd_lang.value, dd_model.value, dd_format.value
        backend = get_active_backend()
        
        def worker():
            try:
                success, new_content = backend.revise_reflection(content, style_val, len_val, lang_val, custom_instruction, model_val, fmt_val)
                
                def update_ui():
                    set_loading(False)
                    if success:
                        text_area.value = format_and_clean(new_content)
                        reading_text.value = text_area.value
                        save_app_settings() # Auto-Save!
                        show_snack("Content revised successfully!", ft.Colors.GREEN)
                        
                        try: 
                            text_area.update()
                            page.update()
                        except Exception: pass
                        
                        if chk_autoplay.value:
                            threading.Timer(0.5, lambda: page.call_after(on_play_tts) if hasattr(page, 'call_after') else on_play_tts()).start()
                    else:
                        show_error_dialog(new_content)
                        show_snack("Failed to revise content.", ft.Colors.RED)
                        page.update()
                        
                if hasattr(page, 'call_after'): page.call_after(update_ui)
                else: update_ui()
                
            except Exception as ex:
                def handle_err():
                    set_loading(False)
                    show_snack(f"Revision error: {ex}", ft.Colors.RED)
                    page.update()
                if hasattr(page, 'call_after'): page.call_after(handle_err)
                else: handle_err()
                
        threading.Thread(target=worker, daemon=True).start()

    def on_revise_standard(e): execute_revision()

    def open_revise_ai_dialog(e):
        prompt_field = ft.TextField(label="Custom Instruction (e.g., 'Make it a short story')")
        def submit_dlg(e):
            hide_dialog(dlg)
            if prompt_field.value and prompt_field.value.strip(): execute_revision(prompt_field.value.strip())
        
        dlg = ft.AlertDialog(
            title=ft.Text("Revise Content with Prompt"), content=prompt_field,
            actions=[ft.TextButton("Cancel", on_click=lambda e: hide_dialog(dlg)), ft.TextButton("Revise", on_click=submit_dlg, style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE, color=ft.Colors.WHITE))]
        )
        show_dialog(dlg)

    def on_generate_qa(e=None):
        if is_processing[0]: return
        content = text_area.value
        if not content or content.startswith("Welcome!"): return show_snack("Please generate a document first.", ft.Colors.RED)

        set_loading(True, "Generating Q&A...")
        lang_val, model_val, fmt_val = dd_lang.value, dd_model.value, dd_format.value
        backend = get_active_backend()
        
        def worker():
            try:
                success, qa_content = backend.generate_qa(content, lang_val, "", model_val, fmt_val)
                
                def update_ui():
                    set_loading(False)
                    if success:
                        text_area.value = content.strip() + "\n\n---\n\n" + qa_content.strip()
                        reading_text.value = text_area.value
                        save_app_settings() # Auto-Save!
                        show_snack("Q&A generated successfully!", ft.Colors.GREEN)
                        
                        try: 
                            text_area.update()
                            page.update()
                        except Exception: pass
                    else:
                        show_error_dialog(qa_content)
                        show_snack("Failed to generate Q&A.", ft.Colors.RED)
                        page.update()
                        
                if hasattr(page, 'call_after'): page.call_after(update_ui)
                else: update_ui()
                
            except Exception as ex:
                def handle_err():
                    set_loading(False)
                    show_snack(f"Q&A error: {ex}", ft.Colors.RED)
                    page.update()
                if hasattr(page, 'call_after'): page.call_after(handle_err)
                else: handle_err()
                
        threading.Thread(target=worker, daemon=True).start()

    def on_play_tts(e=None, record_video=False):
        if app_state.get("is_rendering_audio"):
            app_state["cancel_render"] = True
            app_state["is_rendering_audio"] = False
            show_snack("Render canceled. Cleaning up...", ft.Colors.ORANGE)
            def _reset():
                set_loading(False)
                page.update()
            if hasattr(page, 'call_after'): page.call_after(_reset)
            else: _reset()
            return
            
        if is_audio_playing[0]:
            try:
                if PYGAME_AVAILABLE and pygame.mixer.get_init() and pygame.mixer.music.get_busy(): pygame.mixer.music.stop()
                elif audio_player: audio_player.pause()
                    
                is_audio_playing[0] = False
                is_video_recording[0] = False
                tts_btn.text = "🔊 Read Aloud"
                tts_btn.style = ft.ButtonStyle(bgcolor="#0284C7", color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=8))
                top_play_btn.text = "▶️"
                top_rec_btn.style = ft.ButtonStyle(color=ft.Colors.RED_400)
                top_rec_btn.text = "⏺️ Rec"
                
                if current_fullscreen_mode[0] == "none":
                    reading_container.border = ft.border.all(1.5, ft.Colors.BLUE_600)
                    
                # SAFELY SWAP BACK TO TEXT EDITOR
                text_container_gen.content = text_area
                
                try:
                    tts_btn.update()
                    top_play_btn.update()
                    top_rec_btn.update()
                    text_container_gen.update()
                except Exception: pass
                show_snack("Audio stopped.", ft.Colors.ORANGE)
                page.update()
            except Exception as e: print(f"Error stopping audio: {e}")
            return

        if is_processing[0]: return 
        
        content = text_area.value.strip()
        
        if not content or content.startswith("Welcome!"):
            show_snack("Please generate text to read first.", ft.Colors.RED)
            return
            
        engine = dd_tts_engine.value
        session_id = (tf_tiktok_session.value or "").strip()
        voice_id = TIKTOK_VOICES.get(dd_tiktok_voice.value, "en_us_002")
        server_url = (tf_voicebox_url.value or "").strip()
        preset = (tf_voicebox_preset.value or "").strip()
        vb_engine = dd_voicebox_engine.value
        
        el_presets = app_settings.get("elevenlabs_presets", {})
        el_active_preset = getattr(dd_elevenlabs_preset, 'value', "")
        
        fish_presets = app_settings.get("fish_presets", {})
        fish_active_preset = getattr(dd_fish_preset, 'value', "")
        fish_url = (tf_fish_url.value or "").strip()
        
        if engine == "TikTok API" and not session_id and not chk_force_cache.value: return show_snack("Missing TikTok Session ID! Enter it in settings.", ft.Colors.RED)
        if engine == "Local PC Voicebox" and not server_url and not chk_force_cache.value: return show_snack("Missing Voicebox URL! Enter your PC's IP URL in settings.", ft.Colors.RED)
        if engine == "ElevenLabs" and not el_presets and not chk_force_cache.value: return show_snack("Missing ElevenLabs Settings! Please click 'Manage ElevenLabs Keys' below.", ft.Colors.RED)
        if engine == "Fish Speech" and not fish_presets and not chk_force_cache.value: return show_snack("Missing Fish Speech Settings! Please configure a preset.", ft.Colors.RED)
            
        if not chk_force_cache.value and is_android() and engine in ["Local PC Voicebox", "Fish Speech"] and ("127.0.0.1" in server_url or "localhost" in server_url or "127.0.0.1" in fish_url or "localhost" in fish_url):
            return show_error_dialog("⚠️ You cannot use 127.0.0.1 or localhost on a phone!\n\nThat points to the phone itself. You must use your PC's actual Wi-Fi IP Address (e.g., http://192.168.1.5:8080).")
            
        app_state["is_rendering_audio"] = True
        app_state["cancel_render"] = False
        my_render_id = time.time()
        app_state["current_render_id"] = my_render_id
            
        set_loading(True, f"Generating {engine} Audio...", is_rendering_audio=True)
        
        fingerprint = f"{content}_{engine}_{session_id}_{voice_id}_{server_url}_{preset}_{vb_engine}_{el_active_preset}_{fish_active_preset}_{fish_url}"
        content_hash = hashlib.md5(fingerprint.encode('utf-8')).hexdigest()
        
        pure_text_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
        app_state["last_audio_hash"] = pure_text_hash
        
        def worker():
            try:
                for f in os.listdir(DATA_DIR):
                    if f.startswith("tts_output_") or f.startswith("play_") or f.startswith("temp_video_") or f.startswith("temp_final_"):
                        try: os.remove(os.path.join(DATA_DIR, f))
                        except: pass
                
                output_file = f"tts_output_{int(my_render_id)}.mp3"
                output_path = os.path.join(DATA_DIR, output_file)
                
                cache_dir = getattr(tf_cache_dir, 'value', "").strip()
                if not cache_dir: cache_dir = DATA_DIR
                os.makedirs(cache_dir, exist_ok=True)
                
                cached_mp3 = os.path.join(cache_dir, f"{content_hash}.mp3")
                cached_wav = os.path.join(cache_dir, f"{content_hash}.wav")
                pure_mp3 = os.path.join(cache_dir, f"{pure_text_hash}.mp3")
                pure_wav = os.path.join(cache_dir, f"{pure_text_hash}.wav")
                
                is_cached = False
                is_silent_playback = False
                
                if chk_force_cache.value:
                    if os.path.exists(pure_mp3):
                        success, result, output_path = True, "Loaded from pure cache", pure_mp3
                        output_file = os.path.basename(pure_mp3)
                        is_cached = True
                    elif os.path.exists(pure_wav):
                        success, result, output_path = True, "Loaded from pure cache", pure_wav
                        output_file = os.path.basename(pure_wav)
                        is_cached = True
                    elif os.path.exists(cached_mp3):
                        success, result, output_path = True, "Loaded from cache", cached_mp3
                        output_file = os.path.basename(cached_mp3)
                        is_cached = True
                    elif os.path.exists(cached_wav):
                        success, result, output_path = True, "Loaded from cache", cached_wav
                        output_file = os.path.basename(cached_wav)
                        is_cached = True
                    else:
                        def _notify_silent():
                            show_snack("No cache found for this text. Auto-scrolling silently.", ft.Colors.ORANGE)
                        if hasattr(page, 'call_after'): page.call_after(_notify_silent)
                        else: _notify_silent()
                        
                        success, result, output_path = True, "Silent Playback", ""
                        is_silent_playback = True
                else:
                    if os.path.exists(cached_mp3):
                        success, result, output_path = True, "Loaded from cache", cached_mp3
                        output_file = os.path.basename(cached_mp3)
                        is_cached = True
                    elif os.path.exists(cached_wav):
                        success, result, output_path = True, "Loaded from cache", cached_wav
                        output_file = os.path.basename(cached_wav)
                        is_cached = True
                    else:
                        if engine == "TikTok API":
                            success, result = generate_tiktok_audio(content, voice_id, session_id, output_path)
                        elif engine == "Local PC Voicebox":
                            def _update_status(msg):
                                if app_state.get("cancel_render") or app_state.get("current_render_id") != my_render_id: return
                                def _update():
                                    set_loading(True, msg, is_rendering_audio=True)
                                    page.update()
                                if hasattr(page, 'call_after'): page.call_after(_update)
                                else: _update()

                            output_file = output_file.replace(".mp3", ".wav")
                            output_path = output_path.replace(".mp3", ".wav")
                            
                            cancel_check = lambda: app_state.get("cancel_render") or app_state.get("current_render_id") != my_render_id
                            success, result = generate_voicebox_audio(content, server_url, preset, vb_engine, output_path, status_callback=_update_status, cancel_callback=cancel_check)
                        elif engine == "Fish Speech":
                            def _update_status(msg):
                                if app_state.get("cancel_render") or app_state.get("current_render_id") != my_render_id: return
                                def _update():
                                    set_loading(True, msg, is_rendering_audio=True)
                                    page.update()
                                if hasattr(page, 'call_after'): page.call_after(_update)
                                else: _update()
                                
                            output_file = output_file.replace(".mp3", ".wav")
                            output_path = output_path.replace(".mp3", ".wav")
                            
                            cancel_check = lambda: app_state.get("cancel_render") or app_state.get("current_render_id") != my_render_id
                            success, result, successful_preset_name = generate_fish_speech_audio(content, fish_url, fish_presets, fish_active_preset, output_path, status_callback=_update_status, cancel_callback=cancel_check)
                            if success:
                                def _update_preset():
                                    dd_fish_preset.value = successful_preset_name
                                    save_app_settings()
                                    try: dd_fish_preset.update()
                                    except: pass
                                if hasattr(page, 'call_after'): page.call_after(_update_preset)
                                else: _update_preset()
                        else:
                            success, result, successful_preset_name = generate_elevenlabs_audio(content, el_presets, el_active_preset, output_path)
                            if success:
                                def _update_preset():
                                    dd_elevenlabs_preset.value = successful_preset_name
                                    save_app_settings()
                                    try: dd_elevenlabs_preset.update()
                                    except: pass
                                if hasattr(page, 'call_after'): page.call_after(_update_preset)
                                else: _update_preset()
                                
                        if app_state.get("cancel_render") or app_state.get("current_render_id") != my_render_id:
                            try:
                                if os.path.exists(output_path): os.remove(output_path)
                            except: pass
                            return
                                
                        if success and not is_silent_playback:
                            app_state["last_audio_path"] = output_path
                            
                            if not is_cached:
                                try:
                                    if os.path.exists(output_path):
                                        ext = ".mp3" if output_path.endswith(".mp3") else ".wav"
                                        cache_path_specific = os.path.join(cache_dir, f"{content_hash}{ext}")
                                        cache_path_pure = os.path.join(cache_dir, f"{pure_text_hash}{ext}")
                                        shutil.copy2(output_path, cache_path_specific)
                                        shutil.copy2(output_path, cache_path_pure)
                                        print(f"✅ Auto-Cached audio to {cache_path_pure}")
                                except Exception as e:
                                    print(f"⚠️ Cache Error: {e}")

                if success:
                    if output_path and os.path.exists(output_path) and os.path.getsize(output_path) < 100:
                        def _warn():
                            show_snack("⚠️ Warning: Server returned an empty audio file (Silence).", ft.Colors.ORANGE)
                            set_loading(False)
                            page.update()
                        if hasattr(page, 'call_after'): page.call_after(_warn)
                        else: _warn()
                        return

                    try:
                        temp_avi_path = os.path.join(DATA_DIR, f"temp_video_{int(time.time())}.avi")
                        temp_mp4_path = os.path.join(DATA_DIR, "temp_final_video.mp4")
                        
                        # --- MOBILE AUDIO FIX: RELATIVE ASSET SANDBOX ---
                        # We must force the audio file into Flet's secure 'assets_dir' (DATA_DIR) 
                        # and use a relative filename, or Android security blocks playback!
                        if not is_silent_playback:
                            ext = ".mp3" if output_path.endswith(".mp3") else ".wav"
                            play_target_filename = f"play_{int(my_render_id)}{ext}"
                            play_target_path = os.path.join(DATA_DIR, play_target_filename)
                            
                            try:
                                shutil.copy2(output_path, play_target_path)
                            except Exception as e:
                                print(f"Error sandboxing audio: {e}")
                                play_target_path = output_path 
                                play_target_filename = os.path.basename(output_path)

                        is_processing[0] = False 
                        
                        def ui_updates():
                            family = dd_font.value if dd_font.value != "Default" else None
                            try: current_f_size = int(dd_size.value)
                            except: current_f_size = 16
                            reading_text.size = current_f_size
                            reading_text.font_family = family
                            try: reading_text.style = ft.TextStyle(size=current_f_size, font_family=family) if family else ft.TextStyle(size=current_f_size)
                            except: pass

                            # --- SAFE AUDIO INJECTION ---
                            if not is_silent_playback:
                                if PYGAME_AVAILABLE:
                                    if not pygame.mixer.get_init(): pygame.mixer.init()
                                    pygame.mixer.music.load(play_target_path)
                                    pygame.mixer.music.play()
                                elif audio_player:
                                    # Tell the frontend to load from its internal web server relative path
                                    audio_player.src = play_target_filename
                                    if audio_player not in page.overlay:
                                        page.overlay.append(audio_player)
                                    try: 
                                        page.update()
                                        audio_player.update()
                                        audio_player.play()
                                    except Exception as e:
                                        show_snack(f"Audio playback error: {e}", ft.Colors.RED)
                                else:
                                    show_snack("Cannot play audio: Ensure 'flet-audio' is in requirements.txt on GitHub!", ft.Colors.RED)

                            if record_video and is_cached:
                                status_msg = "🔴 Recording Video (Audio from Cache)..."
                            elif record_video and is_silent_playback:
                                status_msg = "🔴 Recording Video (Silent Mode)..."
                            elif record_video:
                                status_msg = "🔴 Recording Video..."
                            elif is_cached:
                                status_msg = "🔊 Playing from Cache..."
                            elif is_silent_playback:
                                status_msg = "📜 Auto-Scrolling Silently..."
                            else:
                                status_msg = "🔊 Playing Audio..."
                                
                            set_loading(False, status_msg)
                            tts_btn.text = "⏹️ Stop Audio"
                            tts_btn.style = ft.ButtonStyle(bgcolor=ft.Colors.RED_700, color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=8))
                            tts_btn.disabled = False
                            
                            top_play_btn.text = "⏹️"
                            top_play_btn.disabled = False
                            
                            if record_video:
                                top_rec_btn.style = ft.ButtonStyle(color=ft.Colors.RED_700, bgcolor=ft.Colors.WHITE)
                                top_rec_btn.text = "⏹️ Stop Rec"
                                reading_container.border = None
                            
                            # --- THE DOM SHATTER FIX ---
                            # Swap content instead of using visibility toggles on expanding rows
                            reading_text.value = "\n" + content + "\n\n\n\n"
                            try: reading_text.update()
                            except: pass
                            
                            text_container_gen.content = reading_container
                            
                            try: 
                                tts_btn.update()
                                top_play_btn.update()
                                top_rec_btn.update()
                                text_container_gen.update()
                                page.update() 
                                
                                async def _reset_scroll():
                                    try:
                                        res = reading_column.scroll_to(offset=0.0, duration=10)
                                        if inspect.iscoroutine(res): await res
                                    except: pass
                                if hasattr(page, 'run_task'):
                                    page.run_task(_reset_scroll)
                                else:
                                    try:
                                        res = reading_column.scroll_to(offset=0.0, duration=10)
                                        if inspect.iscoroutine(res): asyncio.run(res)
                                    except: pass
                            except: pass
                            
                        if hasattr(page, 'call_after'): page.call_after(ui_updates)
                        else: ui_updates()

                        if record_video and VIDEO_EXPORT_AVAILABLE:
                            is_video_recording[0] = True
                            
                            def frame_grabber_task():
                                try:
                                    with mss.mss() as sct:
                                        left, top, width, height = 0, 0, 0, 0
                                        scale = 1.0
                                        
                                        if platform.system().lower() == "windows":
                                            try:
                                                import ctypes
                                                from ctypes import wintypes
                                                ctypes.windll.user32.SetProcessDPIAware()
                                                hwnd = ctypes.windll.user32.FindWindowW(None, page.title)
                                                if hwnd:
                                                    rect = wintypes.RECT()
                                                    ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(rect))
                                                    pt = wintypes.POINT(0, 0)
                                                    ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(pt))
                                                    
                                                    dpi = ctypes.windll.user32.GetDpiForWindow(hwnd)
                                                    scale = dpi / 96.0
                                                    
                                                    header_offset = int(60 * scale)
                                                    
                                                    left = pt.x
                                                    top = pt.y + header_offset
                                                    width = rect.right - rect.left
                                                    height = (rect.bottom - rect.top) - header_offset
                                            except Exception as e:
                                                print(f"Windows API Rect Error: {e}")
                                                
                                        if width <= 0 or height <= 0:
                                            try:
                                                left, top = int(page.window.left), int(page.window.top)
                                                width, height = int(page.window.width), int(page.window.height)
                                                top += int(80 * scale)
                                                height -= int(100 * scale)
                                            except Exception:
                                                left, top, width, height = 0, 0, 450, 850
                                                
                                        width -= (width % 2)
                                        height -= (height % 2)

                                        monitor = {
                                            "top": int(top),
                                            "left": int(left),
                                            "width": int(width),
                                            "height": int(height)
                                        }
                                        
                                        fps = 20.0
                                        frame_duration = 1.0 / fps
                                        fourcc = cv2.VideoWriter_fourcc(*"XVID")
                                        out = cv2.VideoWriter(temp_avi_path, fourcc, fps, (monitor["width"], monitor["height"]))
                                        
                                        while is_video_recording[0]:
                                            start_t = time.time()
                                            
                                            img = np.array(sct.grab(monitor))
                                            frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                                            out.write(frame)
                                            
                                            elapsed = time.time() - start_t
                                            sleep_needed = frame_duration - elapsed
                                            if sleep_needed > 0:
                                                time.sleep(sleep_needed)
                                            
                                        out.release()
                                except Exception as e:
                                    print(f"Frame Grabber error: {e}")
                                    is_video_recording[0] = False
                                    
                            threading.Thread(target=frame_grabber_task, daemon=True).start()
                            
                        is_audio_playing[0] = True
                        
                        def monitor_playback():
                            try:
                                audio_dur = get_audio_duration(output_path, content)
                                
                                f_size = 16
                                try: f_size = int(dd_size.value)
                                except: pass
                                
                                c_width = f_size * 0.55
                                is_land = current_fullscreen_mode[0] == "landscape"
                                is_port = current_fullscreen_mode[0] == "portrait"
                                
                                if is_land: 
                                    b_width = 800 - 80
                                    viewport_height = 450 - 20
                                elif is_port: 
                                    b_width = 450 - 50
                                    viewport_height = 800 - 20
                                else: 
                                    b_width = 450 - 20
                                    viewport_height = 220 - 20
                                    
                                chars_per_line = max(5, b_width / (f_size * 0.6))
                                
                                lines_count = 0
                                for paragraph in content.split('\n'):
                                    lines_count += (len(paragraph) // chars_per_line) + 2.5
                                    
                                total_pixel_height = lines_count * (f_size * 2.5)
                                scroll_dist = max(0, total_pixel_height - (viewport_height * 0.5))
                                
                                delay_start = audio_dur * 0.10
                                active_scroll_dur = audio_dur * 0.80
                                if active_scroll_dur <= 0: active_scroll_dur = 1
                                
                                pixels_per_second = scroll_dist / active_scroll_dur
                                
                                start_time = time.time()
                                
                                while is_audio_playing[0]:
                                    if PYGAME_AVAILABLE and not is_silent_playback:
                                        if not pygame.mixer.music.get_busy(): break 
                                            
                                    try:
                                        elapsed = time.time() - start_time
                                        
                                        if is_silent_playback and elapsed >= audio_dur:
                                            break
                                        
                                        multiplier = 1.0
                                        try: multiplier = float(scroll_speed_slider.value) / 20.0
                                        except: pass
                                        
                                        if elapsed < delay_start:
                                            current_offset = 0.0
                                        elif elapsed > (delay_start + active_scroll_dur):
                                            current_offset = scroll_dist * multiplier
                                        else:
                                            progress = (elapsed - delay_start) / active_scroll_dur
                                            current_offset = (scroll_dist * progress) * multiplier
                                            
                                        if current_offset > 0:
                                            safe_fire_scroll(current_offset)
                                    except Exception: pass
                                    
                                    time.sleep(1)
                                
                                is_audio_playing[0] = False
                                is_video_recording[0] = False
                                
                                time.sleep(0.5)
                                
                                def reset_ui():
                                    tts_btn.text = "🔊 Read Aloud"
                                    tts_btn.style = ft.ButtonStyle(bgcolor="#0284C7", color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=8))
                                    top_play_btn.text = "▶️"
                                    top_rec_btn.style = ft.ButtonStyle(color=ft.Colors.RED_400, bgcolor=ft.Colors.TRANSPARENT)
                                    top_rec_btn.text = "⏺️ Rec"
                                    
                                    if current_fullscreen_mode[0] == "none":
                                        reading_container.border = ft.border.all(1.5, ft.Colors.BLUE_600)
                                        
                                    text_container_gen.content = text_area
                                    try: 
                                        tts_btn.update()
                                        top_play_btn.update()
                                        top_rec_btn.update()
                                        text_container_gen.update()
                                        refresh_fav_list()
                                        page.update()
                                    except: pass
                                    
                                if hasattr(page, 'call_after'): page.call_after(reset_ui)
                                else: reset_ui()
                                
                                if record_video and VIDEO_EXPORT_AVAILABLE and os.path.exists(temp_avi_path):
                                    def _show_mux():
                                        set_loading(True, "⏳ Compiling final MP4 Video... Please wait.")
                                        page.update()
                                    if hasattr(page, 'call_after'): page.call_after(_show_mux)
                                    else: _show_mux()
                                    
                                    def mux_video():
                                        try:
                                            import imageio_ffmpeg
                                            import subprocess
                                            
                                            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                                            
                                            cmd = [
                                                ffmpeg_exe,
                                                "-y", 
                                                "-i", temp_avi_path
                                            ]
                                            
                                            if output_path and os.path.exists(output_path):
                                                cmd.extend([
                                                    "-i", output_path, 
                                                    "-c:v", "libx264",
                                                    "-c:a", "aac"
                                                ])
                                            else:
                                                cmd.extend([
                                                    "-c:v", "libx264"
                                                ])
                                                
                                            cmd.append(temp_mp4_path)
                                            
                                            startupinfo = None
                                            if platform.system().lower() == "windows":
                                                startupinfo = subprocess.STARTUPINFO()
                                                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                                                
                                            process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)
                                            
                                            if process.returncode != 0:
                                                err_msg = process.stderr.decode('utf-8', errors='ignore')
                                                raise Exception(f"FFmpeg Compilation Error:\n{err_msg}")
                                            
                                            import tkinter as tk
                                            from tkinter import filedialog
                                            root = tk.Tk()
                                            root.withdraw()
                                            root.attributes('-topmost', True)
                                            save_path = filedialog.asksaveasfilename(
                                                parent=root,
                                                title="Save Devotional Video",
                                                initialfile=f"Devotional_{int(time.time())}.mp4",
                                                defaultextension=".mp4",
                                                filetypes=[("MP4 Video", "*.mp4")]
                                            )
                                            root.destroy()

                                            if save_path:
                                                shutil.move(temp_mp4_path, save_path)
                                                def _sc():
                                                    show_snack(f"✅ Video saved to {save_path}", ft.Colors.GREEN)
                                                    page.update()
                                                if hasattr(page, 'call_after'): page.call_after(_sc)
                                                else: _sc()
                                            else:
                                                def _cn():
                                                    show_snack("Video save cancelled.", ft.Colors.ORANGE)
                                                    page.update()
                                                if hasattr(page, 'call_after'): page.call_after(_cn)
                                                else: _cn()
                                                
                                        except Exception as ex:
                                            def _er():
                                                show_error_dialog(f"Video Compilation Error:\n{ex}")
                                                page.update()
                                            if hasattr(page, 'call_after'): page.call_after(_er)
                                            else: _er()
                                        finally:
                                            def _dn():
                                                set_loading(False)
                                                page.update()
                                            if hasattr(page, 'call_after'): page.call_after(_dn)
                                            else: _dn()
                                            try:
                                                if os.path.exists(temp_avi_path): os.remove(temp_avi_path)
                                                if os.path.exists(temp_mp4_path): os.remove(temp_mp4_path)
                                            except: pass
                                            
                                    threading.Thread(target=mux_video, daemon=True).start()

                            except: pass

                        threading.Thread(target=monitor_playback, daemon=True).start()
                        
                    except Exception as ex:
                        def _plerr():
                            show_error_dialog(f"Playback Error: {ex}")
                            show_snack("Failed to play audio.", ft.Colors.RED)
                            page.update()
                        if hasattr(page, 'call_after'): page.call_after(_plerr)
                        else: _plerr()
                else:
                    def _gerr():
                        if app_state.get("cancel_render") or app_state.get("current_render_id") != my_render_id:
                            return
                            
                        show_error_dialog(result)
                        show_snack("Failed to generate audio.", ft.Colors.RED)
                        page.update()
                    if hasattr(page, 'call_after'): page.call_after(_gerr)
                    else: _gerr()
            finally:
                if app_state.get("current_render_id") == my_render_id:
                    app_state["is_rendering_audio"] = False
                    if not is_audio_playing[0] and not is_video_recording[0]:
                        def _rls():
                            set_loading(False)
                            page.update()
                        if hasattr(page, 'call_after'): page.call_after(_rls)
                        else: _rls()
                
        threading.Thread(target=worker, daemon=True).start()

    def on_link_audio(e):
        content = text_area.value.strip()
        if not content or content.startswith("Welcome!"):
            show_snack("Please generate or paste text first to link audio to it.", ft.Colors.ORANGE)
            return

        if is_android():
            show_snack("Manual file linking is only supported on PC.", ft.Colors.ORANGE)
            return

        def _open_picker():
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                root.attributes('-topmost', True)
                selected_file = filedialog.askopenfilename(
                    parent=root,
                    title="Select Pre-Generated Audio File",
                    filetypes=[("Audio Files", "*.wav *.mp3")]
                )
                root.destroy()
                
                if selected_file:
                    pure_text_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
                    cache_dir = getattr(tf_cache_dir, 'value', "").strip()
                    if not cache_dir: cache_dir = DATA_DIR
                    os.makedirs(cache_dir, exist_ok=True)
                    
                    ext = ".mp3" if selected_file.lower().endswith(".mp3") else ".wav"
                    pure_path = os.path.join(cache_dir, f"{pure_text_hash}{ext}")
                    
                    shutil.copy2(selected_file, pure_path)
                    
                    def _sc():
                        refresh_fav_list()
                        show_snack("✅ Audio linked! You can now hit Play without rendering.", ft.Colors.GREEN)
                        page.update()
                    if hasattr(page, 'call_after'): page.call_after(_sc)
                    else: _sc()
            except Exception as ex:
                def _er():
                    show_snack(f"Error linking audio: {ex}", ft.Colors.RED)
                    page.update()
                if hasattr(page, 'call_after'): page.call_after(_er)
                else: _er()
                
        threading.Thread(target=_open_picker, daemon=True).start()

    def copy_to_clipboard(e):
        try:
            if hasattr(page, 'set_clipboard'):
                page.set_clipboard(text_area.value)
            else:
                import pyperclip
                pyperclip.copy(text_area.value)
            show_snack("Copied to clipboard!", ft.Colors.GREEN)
        except Exception:
            show_snack("Auto-copy unavailable. Please long-press text to copy.", ft.Colors.ORANGE)

    def on_record_clicked(e):
        if is_android():
            show_snack("Screen recording via Python is only supported on PC. On Mobile, please use your phone's native screen recorder.", ft.Colors.ORANGE)
            return
        if not VIDEO_EXPORT_AVAILABLE:
            show_error_dialog("Missing Video Libraries!\n\nTo use the Video Export feature on your PC, you must install the recording libraries. Run this exact command in your terminal/cmd:\n\npip install mss opencv-python imageio-ffmpeg")
            return
        
        if is_audio_playing[0]:
            on_play_tts(e)
        else:
            on_play_tts(e, record_video=True)

    def refresh_fav_list():
        cache_dir = getattr(tf_cache_dir, 'value', "").strip()
        if not cache_dir: cache_dir = DATA_DIR
        
        fav_list.controls.clear()
        for i, fav in enumerate(reversed(favorites)):
            real_idx = len(favorites) - 1 - i
            is_selected = selected_fav_idx[0] == real_idx
            
            def make_click(idx): return lambda e: select_fav(idx)
            def make_edit(idx): return lambda e: edit_specific_fav(idx)
            def make_delete(idx): return lambda e: delete_specific_fav(idx)
            
            pure_hash = hashlib.md5(fav.get("content", "").encode('utf-8')).hexdigest()
            has_cache = os.path.exists(os.path.join(cache_dir, f"{pure_hash}.mp3")) or os.path.exists(os.path.join(cache_dir, f"{pure_hash}.wav"))
            cache_icon = " 🎵" if has_cache else ""
            
            action_row = ft.Row([
                ft.TextButton("✏️", on_click=make_edit(real_idx), width=40, style=ft.ButtonStyle(padding=0)),
                ft.TextButton("🗑️", on_click=make_delete(real_idx), width=40, style=ft.ButtonStyle(padding=0, color=ft.Colors.RED_400))
            ], spacing=0)
            
            content_row = ft.Row([
                ft.Text(fav.get("title", "Saved Document") + cache_icon, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE if is_selected else ft.Colors.WHITE70, expand=True),
                action_row
            ])
            
            fav_list.controls.append(
                ft.Container(
                    content=content_row,
                    bgcolor=ft.Colors.BLUE_700 if is_selected else ft.Colors.TRANSPARENT,
                    padding=10, border_radius=5, on_click=make_click(real_idx)
                )
            )
        page.update()

    def select_fav(idx):
        selected_fav_idx[0] = idx
        fav_text_area.value = favorites[idx].get("content", "")
        refresh_fav_list()

    def edit_specific_fav(idx):
        selected_fav_idx[0] = idx
        fav = favorites[idx]
        text_area.value = fav.get("content", "")
        reading_text.value = text_area.value
        switch_to_tab("gen")
        show_snack("Loaded favorite into generator.", ft.Colors.GREEN)

    def delete_specific_fav(idx):
        try:
            content_to_delete = favorites[idx].get("content", "")
            cache_dir = getattr(tf_cache_dir, 'value', "").strip()
            if not cache_dir: cache_dir = DATA_DIR
            pure_hash = hashlib.md5(content_to_delete.encode('utf-8')).hexdigest()
            mp3_path = os.path.join(cache_dir, f"{pure_hash}.mp3")
            wav_path = os.path.join(cache_dir, f"{pure_hash}.wav")
            if os.path.exists(mp3_path): os.remove(mp3_path)
            if os.path.exists(wav_path): os.remove(wav_path)
        except: pass
        
        del favorites[idx]
        if selected_fav_idx[0] == idx:
            selected_fav_idx[0] = None
            fav_text_area.value = "Select a favorite document to read here..."
        elif selected_fav_idx[0] is not None and selected_fav_idx[0] > idx:
            selected_fav_idx[0] -= 1
            
        save_favorites()
        refresh_fav_list()
        show_snack("Favorite deleted.", ft.Colors.GREEN)
        page.update()

    def on_save_favorite(e):
        content = text_area.value.strip()
        if not content or content.startswith("Welcome!"): return show_snack("Please generate or write a document first.", ft.Colors.ORANGE)
        title = extract_title(content)
        for fav in favorites:
            if fav["content"] == content: return show_snack("This exact document is already in your favorites!", ft.Colors.ORANGE)
        favorites.append({"title": title, "content": content})
        save_favorites()
        refresh_fav_list()
        
        cache_dir = getattr(tf_cache_dir, 'value', "").strip()
        if not cache_dir: cache_dir = DATA_DIR
        os.makedirs(cache_dir, exist_ok=True)
        
        audio_path = app_state.get("last_audio_path")
        pure_text_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
        
        cached_status = "❤️ Document saved to favorites!"
        if audio_path and os.path.exists(audio_path):
            ext = ".mp3" if audio_path.endswith(".mp3") else ".wav"
            cache_path_pure = os.path.join(cache_dir, f"{pure_text_hash}{ext}")
            if not os.path.exists(cache_path_pure):
                try:
                    shutil.copy2(audio_path, cache_path_pure)
                    cached_status = "❤️ Document & Audio cached for offline playback!"
                except Exception as ex:
                    print(f"Audio cache error: {ex}")
        
        show_snack(cached_status, ft.Colors.GREEN)

    def open_keys_dialog(e):
        backend_name = dd_backend.value
        if backend_name == "LM Studio (Local)": return show_snack("LM Studio runs locally and does not require API keys.", ft.Colors.BLUE)

        backend_instance = get_active_backend()
        keys_list = ft.ListView(spacing=5, height=150)
        
        def refresh_keys_list():
            keys_list.controls.clear()
            for k in backend_instance.keys: keys_list.controls.append(ft.Text(f"{k[:8]}...{k[-4:]}" if len(k) > 12 else k))
            page.update()

        new_key_field = ft.TextField(label=f"New {backend_name} API Key")
        
        def add_key_action(e):
            val = new_key_field.value or ""
            k = val.strip()
            if k and k not in backend_instance.keys:
                backend_instance.keys.append(k)
                backend_instance.save_keys(backend_instance.keys)
                new_key_field.value = ""
                refresh_keys_list()
                show_snack("Key added!", ft.Colors.GREEN)

        def remove_keys_action(e):
            if backend_instance.keys:
                backend_instance.keys.pop()
                backend_instance.save_keys(backend_instance.keys)
                refresh_keys_list()
                show_snack("Last key removed!", ft.Colors.ORANGE)

        dlg = ft.AlertDialog(
            title=ft.Text(f"Manage {backend_name} API Keys"),
            content=ft.Column([
                ft.Text("The app will automatically rotate through these keys.", italic=True, size=12),
                keys_list, new_key_field,
                ft.Row([ft.TextButton("Add", on_click=add_key_action, style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE)), ft.TextButton("Remove Last", on_click=remove_keys_action, style=ft.ButtonStyle(bgcolor=ft.Colors.RED, color=ft.Colors.WHITE))])
            ], tight=True),
            actions=[ft.TextButton("Close", on_click=lambda e: hide_dialog(dlg))]
        )
        refresh_keys_list()
        show_dialog(dlg)

    # --- WIRE UP ALL BUTTON CALLBACKS ---
    text_area.on_change = on_text_changed
    top_play_btn.on_click = on_play_tts
    top_rec_btn.on_click = on_record_clicked
    copy_btn.on_click = copy_to_clipboard
    generate_btn.on_click = on_generate
    prompt_gen_btn.on_click = open_generate_ai_dialog
    revise_btn.on_click = on_revise_standard
    prompt_rev_btn.on_click = open_revise_ai_dialog
    translate_btn.on_click = on_apply_verse
    qa_btn.on_click = on_generate_qa
    tts_btn.on_click = on_play_tts
    save_btn.on_click = on_save_favorite
    backup_btn.on_click = perform_backup
    restore_btn.on_click = perform_restore
    link_audio_btn.on_click = on_link_audio
    el_manage_btn.on_click = open_el_dialog
    fish_manage_btn.on_click = open_fish_dialog
    test_vb_btn.on_click = test_voicebox_conn
    btn_browse_cache.on_click = browse_cache_dir
    btn_clear_cache.on_click = clear_cache_dir

    # =======================================================
    # UI TABS CONSTRUCTION
    # =======================================================
    
    # 1. GENERATE TAB ACTIONS
    gen_actions_container = ft.Column([
        generate_btn,
        ft.ResponsiveRow([
            ft.Column([prompt_gen_btn], col={"xs": 6}), ft.Column([revise_btn], col={"xs": 6}),
            ft.Column([prompt_rev_btn], col={"xs": 6}), ft.Column([translate_btn], col={"xs": 6}),
            ft.Column([qa_btn], col={"xs": 6}), ft.Column([tts_btn], col={"xs": 6}),
            ft.Column([save_btn], col={"xs": 6}), ft.Column([link_audio_btn], col={"xs": 6}),
        ])
    ])
    
    # 2. SETTINGS TAB CONTENT
    settings_tab_content = ft.Column([
        ft.Text("Content & Display Setup", weight=ft.FontWeight.BOLD, size=18, color=ft.Colors.BLUE_400),
        ft.ResponsiveRow([
            ft.Column([dd_format], col={"sm": 6, "xs": 6}), ft.Column([dd_style], col={"sm": 6, "xs": 6}),
            ft.Column([dd_version], col={"sm": 6, "xs": 6}), ft.Column([dd_theme], col={"sm": 6, "xs": 6}),
            ft.Column([dd_length], col={"sm": 6, "xs": 6}), ft.Column([dd_lang], col={"sm": 6, "xs": 6}),
            ft.Column([dd_duration], col={"sm": 6, "xs": 6}), ft.Column([dd_font], col={"sm": 6, "xs": 6}),
            ft.Column([dd_size], col={"sm": 6, "xs": 6}),
        ]),
        ft.Divider(),
        ft.Text("AI Backend Models", weight=ft.FontWeight.BOLD, size=18, color=ft.Colors.BLUE_400),
        ft.ResponsiveRow([
            ft.Column([dd_backend], col={"sm": 6, "xs": 6}), ft.Column([dd_model], col={"sm": 6, "xs": 6}),
        ]),
        ft.Divider(),
        ft.Text("Data Management", weight=ft.FontWeight.BOLD, size=18, color=ft.Colors.BLUE_400),
        ft.ResponsiveRow([
            ft.Column([backup_btn], col={"xs": 6}), ft.Column([restore_btn], col={"xs": 6})
        ]),
        ft.Container(height=50) # Padding for scrolling
    ], scroll="auto", expand=True)

    # 3. VOICE ENGINE TAB CONTENT
    voice_tab_content = ft.Column([
        ft.Text("TTS Engine Setup", weight=ft.FontWeight.BOLD, size=18, color=ft.Colors.PURPLE_400),
        ft.ResponsiveRow([
            ft.Column([dd_tts_engine], col={"sm": 12, "xs": 12}), 
            ft.Column([chk_autoplay], col={"sm": 6, "xs": 6}), ft.Column([chk_force_cache], col={"sm": 6, "xs": 6}),
            ft.Column([
                ft.Row([
                    ft.Text("Auto-Scroll Speed Multiplier:", font_family="Helvetica", size=14, weight="bold", color=ft.Colors.GREY_400),
                    slider_label
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                scroll_speed_slider
            ], col={"sm": 12, "xs": 12}),
        ]),
        ft.Divider(),
        ft.Text("TikTok Configuration", weight=ft.FontWeight.BOLD, size=16, color=ft.Colors.PINK_400),
        ft.ResponsiveRow([
            ft.Column([tf_tiktok_session], col={"sm": 6, "xs": 6}), ft.Column([dd_tiktok_voice], col={"sm": 6, "xs": 6}),
        ]),
        ft.Divider(),
        ft.Text("Voicebox Configuration", weight=ft.FontWeight.BOLD, size=16, color=ft.Colors.GREEN_400),
        ft.ResponsiveRow([
            ft.Column([tf_voicebox_url], col={"sm": 6, "xs": 12}), 
            ft.Column([tf_voicebox_preset], col={"sm": 6, "xs": 6}),
            ft.Column([dd_voicebox_engine], col={"sm": 6, "xs": 6}), 
            ft.Column([test_vb_btn], col={"sm": 12, "xs": 12}),
        ]),
        ft.Divider(),
        ft.Text("ElevenLabs & Fish Speech", weight=ft.FontWeight.BOLD, size=16, color=ft.Colors.ORANGE_400),
        ft.ResponsiveRow([
            ft.Column([dd_elevenlabs_preset], col={"sm": 6, "xs": 6}), ft.Column([el_manage_btn], col={"sm": 6, "xs": 6}),
            ft.Column([tf_fish_url], col={"sm": 12, "xs": 12}),
            ft.Column([dd_fish_preset], col={"sm": 6, "xs": 6}), ft.Column([fish_manage_btn], col={"sm": 6, "xs": 6}),
        ]),
        ft.Divider(),
        ft.Text("Offline Audio Cache", weight=ft.FontWeight.BOLD, size=16, color=ft.Colors.CYAN_400),
        ft.ResponsiveRow([
            ft.Column([ft.Row([tf_cache_dir, btn_browse_cache, btn_clear_cache], expand=True)], col={"sm": 12, "xs": 12}),
        ]),
        ft.Container(height=50) # Padding for scrolling
    ], scroll="auto", expand=True)

    # 4. FAVORITES TAB CONTENT
    custom_border = ft.Border(top=ft.BorderSide(1, "#374151"), bottom=ft.BorderSide(1, "#374151"), left=ft.BorderSide(1, "#374151"), right=ft.BorderSide(1, "#374151"))
    
    def open_cache_folder_cmd(e):
        cache_dir = getattr(tf_cache_dir, 'value', "").strip()
        if not cache_dir: cache_dir = DATA_DIR
        os.makedirs(cache_dir, exist_ok=True)
        try:
            if platform.system() == "Windows":
                os.startfile(cache_dir)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", cache_dir])
            else:
                subprocess.Popen(["xdg-open", cache_dir])
        except Exception as ex:
            show_snack(f"Could not open folder: {ex}", ft.Colors.RED)

    fav_title_row = ft.Row([
        ft.Text("Saved Documents", weight=ft.FontWeight.BOLD),
        ft.Container(expand=True),
        ft.TextButton("📁 Open Cache Folder", on_click=open_cache_folder_cmd, height=30, style=ft.ButtonStyle(padding=0))
    ])

    favorites_tab_content = ft.Column([
        fav_title_row,
        ft.Container(content=fav_list, expand=True, border=custom_border, border_radius=5, padding=5)
    ], expand=True)

    # =======================================================
    # FULLSCREEN & TAB NAVIGATION LOGIC
    # =======================================================
    
    header_gen_left = ft.Row([
        ft.Text("Preview", weight="bold", color=ft.Colors.GREY_500), 
        top_play_btn, top_rec_btn, copy_btn
    ], alignment=ft.MainAxisAlignment.START, spacing=0)

    # Create space-saving buttons
    fs_portrait_btn = ft.TextButton("📱 Port", tooltip="Portrait Mode", on_click=lambda e: set_fullscreen("portrait"), style=ft.ButtonStyle(color="#60A5FA"))
    fs_landscape_btn = ft.TextButton("📺 Land", tooltip="Landscape Mode", on_click=lambda e: set_fullscreen("landscape"), style=ft.ButtonStyle(color="#60A5FA"))
    fs_exit_btn = ft.TextButton("↙️ Exit", tooltip="Exit Fullscreen", on_click=lambda e: set_fullscreen("none"), style=ft.ButtonStyle(color="#60A5FA"), visible=False)
    
    fs_portrait_btn.visible = True
    fs_landscape_btn.visible = True
    fs_exit_btn.visible = False
    
    fs_row = ft.Row([fs_portrait_btn, fs_landscape_btn, fs_exit_btn], spacing=0)
    header_gen = ft.Row([header_gen_left, fs_row], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
    
    generator_tab_content = ft.Column([header_gen, text_container_gen, ft.Divider(color=ft.Colors.TRANSPARENT, height=5), gen_actions_container], expand=True, scroll="hidden", spacing=0) 

    tab_view_container = ft.Container(
        content=ft.Column([
            generator_tab_content,
            settings_tab_content,
            voice_tab_content,
            favorites_tab_content
        ], expand=True), 
        expand=True, 
        padding=10
    )
    
    active_tab_style = ft.ButtonStyle(bgcolor="#1D4ED8", color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=5), padding=ft.padding.symmetric(horizontal=8, vertical=0))
    inactive_tab_style = ft.ButtonStyle(bgcolor=ft.Colors.TRANSPARENT, color=ft.Colors.GREY_400, shape=ft.RoundedRectangleBorder(radius=5), padding=ft.padding.symmetric(horizontal=8, vertical=0))

    gen_tab_btn = ft.TextButton("✨ Gen", expand=True, on_click=lambda e: switch_to_tab("gen"), style=inactive_tab_style)
    set_tab_btn = ft.TextButton("⚙️ Setup", expand=True, on_click=lambda e: switch_to_tab("set"), style=inactive_tab_style)
    voice_tab_btn = ft.TextButton("🗣️ Voice", expand=True, on_click=lambda e: switch_to_tab("voice"), style=inactive_tab_style)
    fav_tab_btn = ft.TextButton("❤️ Favs", expand=True, on_click=lambda e: switch_to_tab("fav"), style=inactive_tab_style)
    
    tabs_row_container = ft.Container(content=ft.Row([gen_tab_btn, set_tab_btn, voice_tab_btn, fav_tab_btn], alignment=ft.MainAxisAlignment.CENTER, spacing=2), padding=ft.padding.only(left=5, right=5, top=5))

    def switch_to_tab(tab_name):
        gen_tab_btn.style = inactive_tab_style
        set_tab_btn.style = inactive_tab_style
        voice_tab_btn.style = inactive_tab_style
        fav_tab_btn.style = inactive_tab_style
        
        # Hide all contents natively via CSS
        generator_tab_content.visible = False
        settings_tab_content.visible = False
        voice_tab_content.visible = False
        favorites_tab_content.visible = False

        if tab_name == "gen":
            generator_tab_content.visible = True
            gen_tab_btn.style = active_tab_style
        elif tab_name == "set":
            settings_tab_content.visible = True
            set_tab_btn.style = active_tab_style
        elif tab_name == "voice":
            voice_tab_content.visible = True
            voice_tab_btn.style = active_tab_style
        else:
            favorites_tab_content.visible = True
            fav_tab_btn.style = active_tab_style
            
        page.update()

    def set_fullscreen(mode):
        current_fullscreen_mode[0] = mode
        if mode == "none":
            is_fullscreen[0] = False
            if not is_android():
                set_window_size(page, 450, 850)
            
            if not is_video_recording[0]:
                reading_container.border = ft.border.all(1.5, ft.Colors.BLUE_600)
                
            reading_container.padding = ft.padding.only(left=20, right=20, top=15, bottom=15)
        elif mode == "portrait":
            is_fullscreen[0] = True
            if not is_android():
                set_window_size(page, 450, 800)
            reading_container.border = None
            reading_container.padding = ft.padding.only(left=25, right=25, top=35, bottom=35)
        elif mode == "landscape":
            is_fullscreen[0] = True
            if not is_android():
                set_window_size(page, 800, 450)
            reading_container.border = None
            reading_container.padding = ft.padding.only(left=40, right=40, top=35, bottom=35)
            
        title_row.visible = not is_fullscreen[0]
        status_row.visible = not is_fullscreen[0]
        tabs_row_container.visible = not is_fullscreen[0]
        gen_actions_container.visible = not is_fullscreen[0]
        
        if is_fullscreen[0]:
            generator_tab_content.scroll = None
            text_container_gen.height = None
            text_container_gen.expand = True
            tab_view_container.padding = 0
            
            fs_portrait_btn.visible = False
            fs_landscape_btn.visible = False
            fs_exit_btn.visible = True
        else:
            generator_tab_content.scroll = "hidden"
            text_container_gen.height = 380
            text_container_gen.expand = False
            tab_view_container.padding = 10
            
            fs_portrait_btn.visible = True
            fs_landscape_btn.visible = True
            fs_exit_btn.visible = False
            
        page.update()

    switch_to_tab("gen")
    refresh_fav_list()
    update_font()
    on_backend_change(None)

    title_row = ft.Row(
        [ft.Container(width=45), ft.Text("Edu's Daily Devotional", size=20, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER), ft.TextButton("🔑", on_click=open_keys_dialog, width=45, height=45, tooltip="API Keys", style=ft.ButtonStyle(padding=0))],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN
    )

    status_row = ft.Row([pr, status_text], alignment=ft.MainAxisAlignment.CENTER)
    page.add(title_row, status_row, tabs_row_container, tab_view_container)

if __name__ == "__main__":
    try:
        ft.app(target=main, assets_dir=DATA_DIR)
    except Exception as e:
        print("\n❌ FATAL CRASH OCCURRED ❌")
        traceback.print_exc()
        if not is_android(): input("\nPress Enter to close this window...")
