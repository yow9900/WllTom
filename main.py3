import os
import tempfile
import speech_recognition as sr
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import ffmpeg
import subprocess
import logging

# Configuration
BOT_TOKEN = os.environ.get('7790991731:AAF4NHGm0BJCf08JTdBaUWKzwfs82_Y9Ecw')
WEBHOOK_URL = os.environ.get('https://wlltom-i5v5.onrender.com')

# FFmpeg binary detection
FFMPEG_ENV = os.environ.get("FFMPEG_BINARY", "")
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

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# Language configuration
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

# Supported audio/video formats
SUPPORTED_FORMATS = {
    'audio': ['mp3', 'wav', 'm4a', 'ogg', 'webm', 'flac', 'aac', 'aiff', 'amr', 'wma', 'opus'],
    'video': ['mp4', 'mkv', 'avi', 'mov', 'm4v', 'ts', 'flv', '3gp', 'hevc'],
    'voice': ['ogg']  # Telegram voice messages
}

# Store user language preferences
user_languages = {}

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = """
🤖 *Speech-to-Text Bot*

Send me voice messages, audio files, or even video files, and I'll transcribe the audio to text!

📁 *Supported Formats:*
• *Audio:* mp3, wav, m4a, ogg, webm, flac, aac, aiff, amr, wma, opus
• *Video:* mp4, mkv, avi, mov, m4v, ts, flv, 3gp, hevc
• *Voice:* Telegram voice messages

Features:
• Multiple language support
• Voice message transcription
• Audio/video file processing
• Language selection

Use /language to set your preferred language for transcription.
Use /formats to see all supported formats.
"""
    bot.reply_to(message, welcome_text, parse_mode='Markdown')

@bot.message_handler(commands=['language'])
def set_language(message):
    keyboard = InlineKeyboardMarkup()
    rows = []
    
    # Create buttons for each language
    for code, name in LANGUAGES.items():
        rows.append(InlineKeyboardButton(name, callback_data=f"lang_{code}"))
    
    # Arrange buttons in 2 columns
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

@bot.message_handler(commands=['formats'])
def show_formats(message):
    formats_text = """
📁 *Supported File Formats:*

🎵 *Audio Formats:*
• MP3, WAV, M4A, OGG, WEBM, FLAC
• AAC, AIFF, AMR, WMA, OPUS

🎬 *Video Formats:*
• MP4, MKV, AVI, MOV, M4V
• TS, FLV, 3GP, HEVC

🎤 *Telegram Voice Messages:*
• OGG (automatically supported)

Just send me any of these files and I'll extract and transcribe the audio!
"""
    bot.reply_to(message, formats_text, parse_mode='Markdown')

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

@bot.message_handler(content_types=['voice'])
def handle_voice_message(message):
    process_audio_message(message, is_voice=True)

@bot.message_handler(content_types=['audio', 'document', 'video'])
def handle_media_file(message):
    process_audio_message(message, is_voice=False)

def get_file_extension(file_name):
    """Extract file extension from filename"""
    if not file_name:
        return None
    return file_name.lower().split('.')[-1] if '.' in file_name else None

def is_supported_format(file_extension, file_type):
    """Check if the file format is supported"""
    if not file_extension:
        return False
    
    for format_category, extensions in SUPPORTED_FORMATS.items():
        if file_extension in extensions:
            return True
    return False

def process_audio_message(message, is_voice=True):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # Get user's language preference or default to English
    language = user_languages.get(user_id, 'en')
    
    try:
        bot.send_chat_action(chat_id, 'typing')
        
        # Determine file source based on message type
        if is_voice:
            file_info = bot.get_file(message.voice.file_id)
            file_extension = 'ogg'
        elif message.audio:
            file_info = bot.get_file(message.audio.file_id)
            file_extension = get_file_extension(message.audio.file_name)
        elif message.video:
            file_info = bot.get_file(message.video.file_id)
            file_extension = get_file_extension(message.video.file_name)
        elif message.document:
            file_info = bot.get_file(message.document.file_id)
            file_extension = get_file_extension(message.document.file_name)
            # Check if document is a supported media format
            if not is_supported_format(file_extension, 'document'):
                bot.reply_to(message, f"❌ Unsupported file format: .{file_extension}\nUse /formats to see supported formats.")
                return
        else:
            bot.reply_to(message, "❌ Unsupported message type")
            return
        
        # Check if format is supported
        if not is_supported_format(file_extension, 'audio'):
            bot.reply_to(message, f"❌ Unsupported file format: .{file_extension}\nUse /formats to see supported formats.")
            return
        
        # Download the file
        downloaded_file = bot.download_file(file_info.file_path)
        
        # Create temporary files
        original_ext = file_extension or 'audio'
        with tempfile.NamedTemporaryFile(suffix=f'.{original_ext}', delete=False) as temp_input:
            temp_input.write(downloaded_file)
            temp_input_path = temp_input.name
        
        with tempfile.NamedTemporaryFile(suffix='.flac', delete=False) as temp_flac:
            temp_flac_path = temp_flac.name
        
        try:
            # Check if FFmpeg is available
            if FFMPEG_BINARY is None:
                bot.reply_to(message, "❌ Audio processing service is currently unavailable. Please try again later.")
                return
            
            # Convert audio to FLAC format using ffmpeg with explicit binary path
            (
                ffmpeg
                .input(temp_input_path)
                .output(temp_flac_path, ac=1, ar=16000, acodec='flac')
                .overwrite_output()
                .run(cmd=FFMPEG_BINARY, quiet=True)
            )
            
            # Initialize recognizer
            recognizer = sr.Recognizer()
            
            # Transcribe audio using FLAC file
            with sr.AudioFile(temp_flac_path) as source:
                # Adjust for ambient noise
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio_data = recognizer.record(source)
                text = recognizer.recognize_google(audio_data, language=language)
            
            # Send transcription result
            file_type = "Voice message" if is_voice else "Media file"
            response = f"🎤 *Transcription ({LANGUAGES[language]}):*\n\n{text}"
            bot.reply_to(message, response, parse_mode='Markdown')
            
        except sr.UnknownValueError:
            bot.reply_to(message, "❌ Could not understand the audio. Please try again with clearer audio or a different language setting.")
        except sr.RequestError as e:
            bot.reply_to(message, f"❌ Error with speech recognition service: {e}")
        except ffmpeg.Error as e:
            bot.reply_to(message, f"❌ Error processing audio/video file: {e}")
        except Exception as e:
            bot.reply_to(message, f"❌ Error processing file: {e}")
        
        finally:
            # Cleanup temporary files
            if os.path.exists(temp_input_path):
                os.unlink(temp_input_path)
            if os.path.exists(temp_flac_path):
                os.unlink(temp_flac_path)
                
    except Exception as e:
        bot.reply_to(message, f"❌ Error downloading or processing file: {e}")

@bot.message_handler(func=lambda message: True)
def handle_other_messages(message):
    help_text = """
I process voice messages, audio files, and video files!

Available commands:
/start - Show welcome message
/language - Set transcription language
/formats - Show supported formats
/help - Show this help

Just send me a voice message or media file to get started!
"""
    bot.reply_to(message, help_text)

# Flask routes for webhook
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
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
