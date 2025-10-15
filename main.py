import os
import tempfile
import speech_recognition as sr
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import ffmpeg
import subprocess
import logging

logging.basicConfig(level=logging.INFO)

FFMPEG_ENV = ""
POSSIBLE_FFMPEG_PATHS = [FFMPEG_ENV, "./ffmpeg", "/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg", "ffmpeg"]
FFMPEG_BINARY = None
for p in POSSIBLE_FFMPEG_PATHS:
    if not p:
        continue
    try:
        subprocess.run([p, "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
        FFMPEG_BINARY = p
        break
    except Exception:
        continue

if FFMPEG_BINARY is None:
    logging.warning("ffmpeg binary not found. Set FFMPEG_BINARY env var or place ffmpeg in ./ffmpeg or /usr/bin/ffmpeg")
else:
    logging.info(f"FFMPEG_BINARY found at: {FFMPEG_BINARY}")

BOT_TOKEN = "8107285502:AAHzzp-UCcAnciMwf3xnSOMizV7lqMc1fq0"
WEBHOOK_URL = "https://wlltom-i5v5.onrender.com"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

LANGUAGES = {
    'en': 'English',
    'es': 'Spanish', 
    'fr': 'French',
    'de': 'German',
    'it': 'Italian',
    'pt': 'Portuguese',
    'ru': 'Russian',
    'ja': 'Japanese',
    'ko': 'Korean',
    'zh': 'Chinese'
}

user_languages = {}

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = """
🤖 *Speech-to-Text Bot*

Send me a **voice message**, **audio file**, or **video file** and I'll transcribe the audio to text!

Features:
• Multiple language support
• Voice/Audio/Video transcription
• Language selection

Use /language to set your preferred language for transcription.
"""
    bot.reply_to(message, welcome_text, parse_mode='Markdown')

@bot.message_handler(commands=['language'])
def set_language(message):
    keyboard = InlineKeyboardMarkup()
    rows = []
    for code, name in LANGUAGES.items():
        rows.append(InlineKeyboardButton(name, callback_data=f"lang_{code}"))
    for i in range(0, len(rows), 2):
        if i + 1 < len(rows):
            keyboard.row(rows[i], rows[i+1])
        else:
            keyboard.row(rows[i])
    bot.send_message(
        message.chat.id,
        "🌐 *Select your preferred language for transcription:*",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('lang_'))
def handle_language_selection(call):
    language_code = call.data.split('_')[1]
    user_languages[call.from_user.id] = language_code
    language_name = LANGUAGES.get(language_code, 'Unknown')
    bot.answer_callback_query(call.id, f"Language set to {language_name}")
    bot.edit_message_text(
        f"✅ Transcription language set to: *{language_name}*",
        call.message.chat.id,
        call.message.message_id,
        parse_mode='Markdown'
    )

@bot.message_handler(content_types=['voice', 'audio', 'video'])
def handle_media_message(message):
    chat_id = message.chat.id
    if FFMPEG_BINARY is None:
        bot.reply_to(message, "❌ *Error:* FFMPEG is not configured on the server. Cannot process audio/video files.")
        return
    file_id = None
    file_extension = None
    if message.voice:
        file_id = message.voice.file_id
        file_extension = '.ogg' 
    elif message.audio:
        file_id = message.audio.file_id
        file_extension = '.' + (message.audio.file_name.split('.')[-1] if message.audio.file_name else 'mp3')
    elif message.video:
        file_id = message.video.file_id
        file_extension = '.' + (message.video.file_name.split('.')[-1] if message.video.file_name else 'mp4')
    if not file_id:
        bot.reply_to(message, "❌ Could not retrieve file information.")
        return
    process_media(message, file_id, file_extension)

def process_media(message, file_id, file_extension):
    chat_id = message.chat.id
    user_id = message.from_user.id
    language = user_languages.get(user_id, 'en')
    try:
        bot.send_chat_action(chat_id, 'typing')
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        with tempfile.NamedTemporaryFile(suffix=file_extension, delete=False) as temp_input:
            temp_input.write(downloaded_file)
            temp_input_path = temp_input.name
        with tempfile.NamedTemporaryFile(suffix='.flac', delete=False) as temp_flac:
            temp_flac_path = temp_flac.name
        try:
            (
                ffmpeg
                .input(temp_input_path)
                .output(temp_flac_path, ac=1, ar=16000)
                .overwrite_output()
                .run(cmd=FFMPEG_BINARY, quiet=True)
            )
            recognizer = sr.Recognizer()
            with sr.AudioFile(temp_flac_path) as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio_data = recognizer.record(source)
                text = recognizer.recognize_google(audio_data, language=language)
            language_name = LANGUAGES.get(language, 'Selected Language')
            response = f"🎤 *Transcription ({language_name}):*\n\n{text}"
            bot.reply_to(message, response, parse_mode='Markdown')
        except sr.UnknownValueError:
            bot.reply_to(message, "❌ Could not understand the audio. Please try again with clearer audio.")
        except sr.RequestError as e:
            bot.reply_to(message, f"❌ Error with speech recognition service: {e}")
        except ffmpeg.Error as e:
            logging.error(f"FFMPEG Error: {e}")
            bot.reply_to(message, "❌ Error during audio conversion (FFMPEG): Check file format or FFMPEG installation.")
        except Exception as e:
            logging.error(f"General processing error: {e}")
            bot.reply_to(message, f"❌ Error processing media: {e}")
        finally:
            if os.path.exists(temp_input_path):
                os.unlink(temp_input_path)
            if os.path.exists(temp_flac_path):
                os.unlink(temp_flac_path)
    except Exception as e:
        logging.error(f"Download or initial error: {e}")
        bot.reply_to(message, f"❌ Error downloading or processing media: {e}")

@bot.message_handler(func=lambda message: True)
def handle_other_messages(message):
    help_text = """
I only process **voice messages**, **audio files**, and **video files**!

Available commands:
/start - Show welcome message
/language - Set transcription language
/help - Show this help

Just send me a file to get started!
"""
    bot.reply_to(message, help_text)

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    else:
        return 'Invalid content type', 403

@app.route('/')
def index():
    return 'Bot is running!'

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
    return 'Webhook set!'

if __name__ == '__main__':
    logging.info("Starting Flask app...")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
