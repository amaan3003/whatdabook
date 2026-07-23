import easyocr
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import os
from dotenv import load_dotenv
from summarizer import summarize
load_dotenv()

telegramBot = os.getenv("TELEGRAM_TOKEN")

if not telegramBot:
    raise ValueError("API_KEY not found in environment")


def ocr(path):
    reader = easyocr.Reader(['en'], gpu=False)
    result = reader.readtext(path)
    return " ".join([text for _, text, conf in result if conf > 0.3])
 
 
async def handle_photo(update, context):
    photo = update.message.photo[-1]             
    file = await photo.get_file()                 
    await file.download_to_drive("incoming.jpg")  
    await update.message.reply_text(summarize(ocr("incoming.jpg")), parse_mode = "Markdown")
 
 
app = Application.builder().token(telegramBot).build()
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.run_polling()