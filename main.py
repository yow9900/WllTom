import os
import time
import logging
import io
import requests

from flask import Flask, request, abort
import telebot
import speech_recognition as sr

# --- Constants ---

# Bot token-kaaga oo aad soo siisay
API_TOKEN = "7790991731:AAF4NHGm0BJCf08JTdBaUWKzwfs82_Y9Ecw"
# URL-ka webhook-kaaga oo aad soo siisay
WEBHOOK_URL = "https://wlltom-gct6.onrender.com"

# --- Setup ---

logging.basicConfig(level=logging.INFO)
bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)
r = sr.Recognizer()

# --- Webhook Routes (Sida aad u codsatay) ---

@app.route("/", methods=["GET", "POST", "HEAD"])
def webhook():
    """Wuxuu qabtaa dhamaan codsiyada soo gala ee Telegram ka imanaya."""
    if request.method in ("GET", "HEAD"):
        return "Bot-ka Waa Shaqaynayaa! U dir Cod (Voice) ama Audio.", 200

    if request.method == "POST":
        ct = request.headers.get("Content-Type", "")
        if ct and ct.startswith("application/json"):
            try:
                # Dib-u-qaabayn ku samee xogta JSON
                update = telebot.types.Update.de_json(request.get_data().decode("utf-8"))
                # Halkan ayaanu ku farsamaynaa updates-ka
                bot.process_new_updates([update])
                return "", 200
            except Exception as e:
                logging.error(f"Error processing update: {e}")
                return "Error", 500
    
    # Haddii aanay ahayn POST ama Content-Type aan sax ahayn
    return abort(403)

@app.route("/set_webhook", methods=["GET", "POST"])
def set_webhook_route():
    """Wuxuu dejiyaa webhook-ka."""
    try:
        # Tirtir webhook-kii hore haddii uu jiro, ka dibna deji midka cusub
        bot.delete_webhook()
        time.sleep(0.5) # Sug in yar
        bot.set_webhook(url=WEBHOOK_URL)
        logging.info(f"Webhook set to {WEBHOOK_URL}")
        return f"Webhook si guul ah ayaa loo dejiyay: {WEBHOOK_URL}", 200
    except Exception as e:
        logging.error(f"Failed to set webhook: {e}")
        return f"Ku guul daraystay dejinta webhook-ka: {e}", 500

@app.route("/delete_webhook", methods=["GET", "POST"])
def delete_webhook_route():
    """Wuxuu tirtiraa webhook-ka."""
    try:
        bot.delete_webhook()
        return "Webhook si guul ah ayaa loo tirtiray.", 200
    except Exception as e:
        logging.error(f"Failed to delete webhook: {e}")
        return f"Ku guul daraystay tirtirista webhook-ka: {e}", 500

# --- Bot Handlers (Logic) ---

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """Wuxuu soo diraa fariin soo dhaweyn ah."""
    bot.reply_to(message, 
        "Ku soo dhawoow bot-ka qoraal u badalka codka (Audio Transcriber).\n\n"
        "Fadlan ii soo dir **Cod (Voice Message)** ama **Audio File** si aan isugu dayo inaan qoraal u badalo.\n\n"
        "Waxaan ku shaqaynayaa qaab cilmi baaris ah (research mode). Waxaan si toos ah u dhiibi doonaa faylkaaga asalka ah maktabada `speech_recognition` si aan u eegno noocyada uu toos u taageero (Waa laga yaabaa inay ku dhacdo 'Error' maxaa yeelay Telegram badanaa waxay isticmaashaa OGG ama MP4 oo aan la bedelin)."
    )

@bot.message_handler(content_types=['voice', 'audio'])
def handle_audio_transcription(message):
    """
    Wuxuu qabtaa faylasha codka.
    Wuxuu soo dajinayaa faylka asalka ah oo u dhiibayaa 'speech_recognition' si toos ah.
    """
    chat_id = message.chat.id
    bot.send_message(chat_id, "Waan helay faylka codka. Waan isku dayayaa inaan qoraal u badalo...")

    try:
        # 1. Hel File ID-ga
        if message.voice:
            file_id = message.voice.file_id
            mime_type = message.voice.mime_type
        elif message.audio:
            file_id = message.audio.file_id
            mime_type = message.audio.mime_type
        else:
            bot.send_message(chat_id, "Fadlan iigu soo dir qaab 'Voice' ama 'Audio' file.")
            return

        # 2. Hel File Path iyo URL
        file_info = bot.get_file(file_id)
        file_url = f"https://api.telegram.org/file/bot{API_TOKEN}/{file_info.file_path}"
        
        logging.info(f"Downloading file with File ID: {file_id}, Mime Type: {mime_type}, Path: {file_info.file_path}")

        # 3. Soo dajiso nuxurka faylka (Raw Bytes)
        file_response = requests.get(file_url)
        file_response.raise_for_status() # Hubi khaladaadka HTTP
        file_content = file_response.content
        
        # 4. Ku rid raw bytes-ka 'io.BytesIO' si uu maktabadu u isticmaasho (Cilmi baaris)
        audio_file_like = io.BytesIO(file_content)

        # 5. Isku day in loo dhiibo 'speech_recognition'
        # Halkan waxaa laga yaabaa inuu khalkhal yimaado maxaa yeelay OGG ama MP4 uma badna inuu toos u taageero.
        transcribed_text = ""
        try:
            with sr.AudioFile(audio_file_like) as source:
                # Qaado xogta codka
                audio = r.record(source) 
            
            # Isku day transcription
            transcribed_text = r.recognize_google(audio, language="so-SO") # Isku day Soomaali, haddii kalena: en-US
            
            bot.reply_to(message, 
                f"**Qoraalkii soo baxay:**\n\n"
                f"_{transcribed_text}_"
            )

        except sr.UnknownValueError:
            bot.reply_to(message, 
                "**Natiijada Cilmi Baarista:**\n"
                "Maktabada `speech_recognition` **waa ay aqbashay** qaabka faylka (format) laakiin ma fahmin codka (ama codku wuu yaraa). Tani waxay inta badan dhacdaa haddii codka aad loo bedelay ama aanu cadayn."
            )
        
        except sr.RequestError as e:
            bot.reply_to(message, 
                "**Natiijada Cilmi Baarista:**\n"
                "Wuxuu la xiriiri kari waayay Google Speech Recognition Service. Fadlan isku day mar kale.\n"
                f"Khaladkii soo baxay (Error): `{e}`"
            )

        except Exception as e:
            # Tani waxay soo qabanaysaa khaladaadka maktabada 'speech_recognition' ayadoo diidaysa qaabka faylka (format)
            error_message = (
                f"**Natiijada Cilmi Baarista ee Qaabka Faylka:**\n\n"
                f"Fadlan, waan isku dayay inaan si toos ah ugu gudbiyo faylkaaga `speech_recognition` laakiin maktabadu **ma aqbalin** qaabkan (format).\n\n"
                f"**Khaladkii soo baxay (Error) wuxuu muujinayaa:** \n`{e}`\n\n"
                f"Tani waxay cadaynaysaa in `speech_recognition` aysan toos u taageerin noocyada codka ee Telegramka sida **OGG/MP4** iyadoo aan marka hore loo bedelin **WAV** (adiga oo isticmaalaya maktabad sida **`pydub`**)."
            )
            bot.reply_to(message, error_message)

    except Exception as e:
        logging.error(f"Error in main handler: {e}")
        bot.reply_to(message, f"Waxa dhacay khalad aan la filayn: {e}")


# --- Startup Function (Sida aad u codsatay) ---

def set_webhook_on_startup():
    """Wuxuu dejiyaa webhook-ka marka uu bot-ku shaqo bilaabayo."""
    try:
        # Hubi inuu shaqaynayo set_webhook_route
        response = requests.get(WEBHOOK_URL + "/set_webhook")
        response.raise_for_status()
        logging.info(response.text)
    except Exception as e:
        logging.error(f"Failed to set main bot webhook on startup via route: {e}")

def set_bot_info_and_startup():
    """Ku bilow dejinta webhook-ka."""
    # Waxaan u isticmaalaynaa habka route-ka (GET /set_webhook) si loo hubiyo inuu si sax ah u shaqaynayo
    # Waxaa fiican in gooni loo shaqaysiiyo mar kasta oo la shido app-ka
    set_webhook_on_startup() 

# --- Main Execution ---

if __name__ == "__main__":
    # Deji webhook-ka marka app-ka la bilaabo
    set_bot_info_and_startup()
    
    # Bilow Flask app-ka
    # Wuxuu u isticmaalayaa 'PORT' variable-ka deegaanka (environment variable)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

