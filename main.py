import os
import tempfile
import speech_recognition as sr
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import ffmpeg
import subprocess
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)

# --- FFMPEG Binary Search (as provided in the request) ---
FFMPEG_ENV = os.environ.get("FFMPEG_BINARY", "")
POSSIBLE_FFMPEG_PATHS = [FFMPEG_ENV, "./ffmpeg", "/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg", "ffmpeg"]
FFMPEG_BINARY = None
for p in POSSIBLE_FFMPEG_PATHS:
    if not p:
        continue
    try:
        # Check if the binary runs the version command
        subprocess.run([p, "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
        FFMPEG_BINARY = p
        break
    except Exception:
        continue

if FFMPEG_BINARY is None:
    logging.warning("ffmpeg binary not found. Set FFMPEG_BINARY env var or place ffmpeg in ./ffmpeg or /usr/bin/ffmpeg")
else:
    logging.info(f"FFMPEG_BINARY found at: {FFMPEG_BINARY}")
# ---------------------------------------------------------


# Configuration
BOT_TOKEN = os.environ.get('BOT_TOKEN')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')

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

# Store user language preferences
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

# Handle Voice, Audio, and Video messages
@bot.message_handler(content_types=['voice', 'audio', 'video'])
def handle_media_message(message):
    
    chat_id = message.chat.id
    
    if FFMPEG_BINARY is None:
        bot.reply_to(message, "❌ *Error:* FFMPEG is not configured on the server. Cannot process audio/video files.")
        return

    # Determine the file ID and file extension based on content type
    file_id = None
    file_extension = None
    
    if message.voice:
        file_id = message.voice.file_id
        # Telegram voice messages are typically Opus encoded in an Ogg container (.ogg)
        file_extension = '.ogg' 
    elif message.audio:
        file_id = message.audio.file_id
        # Use the file's provided mime type or default to the file name extension
        file_extension = '.' + (message.audio.file_name.split('.')[-1] if message.audio.file_name else 'mp3')
    elif message.video:
        file_id = message.video.file_id
        # Use the file's provided mime type or default to the file name extension
        file_extension = '.' + (message.video.file_name.split('.')[-1] if message.video.file_name else 'mp4')
    
    if not file_id:
        bot.reply_to(message, "❌ Could not retrieve file information.")
        return

    process_media(message, file_id, file_extension)

def process_media(message, file_id, file_extension):
    
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # Get user's language preference or default to English
    language = user_languages.get(user_id, 'en')
    
    try:
        bot.send_chat_action(chat_id, 'typing')
        
        # Download the audio/video file
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # Create temporary files
        # The input file uses the actual extension, which FFMPEG will handle
        with tempfile.NamedTemporaryFile(suffix=file_extension, delete=False) as temp_input:
            temp_input.write(downloaded_file)
            temp_input_path = temp_input.name
        
        # The output file must be in WAV format for speech_recognition
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_wav:
            temp_wav_path = temp_wav.name
        
        try:
            # Convert audio stream from any input format to WAV format using ffmpeg
            # ac=1 (mono), ar=16000 (16kHz sample rate) are standard for speech recognition
            (
                ffmpeg
                .input(temp_input_path)
                .output(temp_wav_path, ac=1, ar=16000)
                .overwrite_output()
                .run(cmd=FFMPEG_BINARY, quiet=True) # Use the discovered FFMPEG_BINARY
            )
            
            # Initialize recognizer
            recognizer = sr.Recognizer()
            
            # Transcribe audio
            with sr.AudioFile(temp_wav_path) as source:
                # Adjust for ambient noise and then record
                recognizer.adjust_for_ambient_noise(source, duration=0.5) 
                audio_data = recognizer.record(source)
                text = recognizer.recognize_google(audio_data, language=language)
            
            # Send transcription result
            language_name = LANGUAGES.get(language, 'Selected Language')
            response = f"🎤 *Transcription ({language_name}):*\n\n{text}"
            bot.reply_to(message, response, parse_mode='Markdown')
            
        except sr.UnknownValueError:
            bot.reply_to(message, "❌ Could not understand the audio. Please try again with clearer audio.")
        except sr.RequestError as e:
            bot.reply_to(message, f"❌ Error with speech recognition service: {e}")
        except ffmpeg.Error as e:
            logging.error(f"FFMPEG Error: {e.stderr.decode('utf8')}")
            bot.reply_to(message, f"❌ Error during audio conversion (FFMPEG): Check the file format or FFMPEG installation.")
        except Exception as e:
            logging.error(f"General processing error: {e}")
            bot.reply_to(message, f"❌ Error processing media: {e}")
        
        finally:
            # Cleanup temporary files
            if os.path.exists(temp_input_path):
                os.unlink(temp_input_path)
            if os.path.exists(temp_wav_path):
                os.unlink(temp_wav_path)
                
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
    if not WEBHOOK_URL:
        return 'WEBHOOK_URL environment variable is not set.', 500
    
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
    return 'Webhook set!'

if __name__ == '__main__':
    # Ensure all required environment variables are set
    if not BOT_TOKEN:
        logging.error("BOT_TOKEN environment variable not set. Exiting.")
        exit(1)
    if not WEBHOOK_URL:
        logging.error("WEBHOOK_URL environment variable not set. Exiting.")
        exit(1)
        
    logging.info("Starting Flask app...")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
