from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes,CallbackQueryHandler,CommandHandler
import os
from html import escape
from dotenv import load_dotenv
from summarizer import summarize
from recommendationModel import get_genres,get_similar_books
from db import (
    get_user,
    has_training_consent,
    init_db,
    replace_contributed_ratings,
    save_goodreads,
    save_user,
    set_training_consent,
)
from bookRatingScraper import (
    build_reading_profile,
    extract_rated_books,
    scrape_goodreads,
)
from userBasedMLmodel import recommend_for_user
import json
from google.cloud import vision
from google.api_core.client_options import ClientOptions
load_dotenv()
from flask import Flask
import threading






flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get('PORT', 8000))
    flask_app.run(host='0.0.0.0', port=port)







telegramBot = os.getenv("TELEGRAM_TOKEN")
if not telegramBot:
    raise ValueError("API_KEY not found in environment")








def ocr(path):
    client = vision.ImageAnnotatorClient(
        client_options=ClientOptions(api_key=os.getenv("GOOGLE_CLOUD_VISION_API_KEY"))
    )

    with open(path, "rb") as f:
        content = f.read()
        
    image = vision.Image(content=content)
    response = client.text_detection(image=image)   
    texts = response.text_annotations           
    
    return texts[0].description if texts else "" 

 


async def start(update, context):
    user = update.effective_user
    save_user(user.id, user.first_name)

    saved_user = get_user(user.id)
    goodreads_connected = saved_user is not None and saved_user[1] is not None
    personalization_status = (
        "✅ <b>Personalization is ready</b> — your Goodreads history is connected."
        if goodreads_connected
        else "✨ <b>Want personal results?</b> Connect your Goodreads history."
    )
    goodreads_button = (
        "🔄 Refresh Goodreads" if goodreads_connected else "🔗 Connect Goodreads"
    )
    keyboard = [
        [InlineKeyboardButton("📸 Scan a book", callback_data="start_scan")],
        [InlineKeyboardButton("🎯 Get recommendations", callback_data="start_recommend")],
        [InlineKeyboardButton(goodreads_button, callback_data="start_goodreads")],
        [InlineKeyboardButton("❓ How it works", callback_data="start_help")],
    ]

    await update.message.reply_text(
        f"Hey {escape(user.first_name)}! 👋\n\n"
        "📚 <b>WhatDaBook</b>\n"
        "<i>Your next great read starts with one photo.</i>\n\n"
        "Send me a book cover and I’ll identify it, summarize it, and explain "
        "why it may—or may not—fit your taste.\n\n"
        f"{personalization_status}\n\n"
        "What would you like to do?",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    
    
    
async def goodreads(update, context):
    if not context.args:                                    
        await update.message.reply_text("Send it like: /goodreads <your profile link>")
        return

    link = context.args[0]                            
    await update.message.reply_text("Fetching your Goodreads data... ⏳")

    data = scrape_goodreads(link)                           

    if data is None:                                     
        await update.message.reply_text("Couldn't fetch that. Check the link and try again.")
        return

    user = update.effective_user
    save_user(user.id, user.first_name)
    save_goodreads(user.id, data)

    if has_training_consent(user.id):
        saved_count = replace_contributed_ratings(
            user.id,
            extract_rated_books(data),
        )
        await update.message.reply_text(
            "Done! ✅ Your summaries and recommendations will now use your "
            f"reading history. I also refreshed {saved_count} contributed ratings.\n\n"
            "Use /optout anytime to remove contributed ratings."
        )
        return

    contribution_keyboard = [[
        InlineKeyboardButton(
            "✅ Help improve recommendations",
            callback_data="training_opt_in",
        ),
        InlineKeyboardButton("No thanks", callback_data="training_opt_out"),
    ]]
    await update.message.reply_text(
        "Done! ✅ Your summaries and recommendations will now use your reading "
        "history.\n\nWould you also like to contribute your book titles and "
        "ratings to improve future recommendations? Your name and Telegram ID "
        "will not be included in training exports, and you can use /optout anytime.",
        reply_markup=InlineKeyboardMarkup(contribution_keyboard),
    )
 

async def send_personalized_recommendations(message, user_id):
    user = get_user(user_id)                     # get (name, goodreads_data) from DB

    if user is None or user[1] is None:           # user hasn't linked Goodreads
        await message.reply_text(
            "Connect Goodreads first so I can learn your reading taste.\n\n"
            "Send <code>/goodreads</code> followed by your public Goodreads "
            "profile link.",
            parse_mode="HTML",
        )
        return

    goodreads_data = user[1]                      # index 1 = goodreads_data column

    await message.reply_text("Finding books for you... ⏳")

    try:
        data = json.loads(goodreads_data)
    except (TypeError, json.JSONDecodeError):
        await message.reply_text("Your saved Goodreads data could not be read. Please link it again with /goodreads.")
        return

    recs = recommend_for_user(data, n=5)          
    if not recs:                                  
        await message.reply_text("Couldn't find good matches yet — your books might not be in my dataset.")
        return

    msg = "📚 *Recommended for you:*\n\n" + "".join(f"• {b}\n" for b in recs)
    await message.reply_text(msg, parse_mode="Markdown")


async def recommend_cmd(update, context):
    await send_personalized_recommendations(
        update.message,
        update.effective_user.id,
    )

async def handle_photo(update, context):
    photo = update.message.photo[-1]             
    file = await photo.get_file()                 
    await file.download_to_drive("incoming.jpg")  
    
    book_text = ocr("incoming.jpg")
    if not book_text.strip():
        await update.message.reply_text("I couldn't read that cover. Try a clearer, well-lit photo.")
        return

    reading_profile = None
    user = get_user(update.effective_user.id)
    if user is not None and user[1] is not None:
        try:
            goodreads_data = json.loads(user[1])
            reading_profile = build_reading_profile(goodreads_data)
        except (TypeError, json.JSONDecodeError):
            # Broken saved data should not prevent the normal summary.
            reading_profile = None

    try:
        summary = summarize(book_text, reading_profile)
    except (RuntimeError, ValueError):
        await update.message.reply_text("I couldn't create the summary right now. Please try again shortly.")
        return
    
    context.user_data['genres'] = get_genres(summary)   
    
    keyboard = [[InlineKeyboardButton("📚 Similar Books", callback_data="similar")]]  
    
    await update.message.reply_text(
        summary,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)     
    )


async def optout(update, context):
    set_training_consent(update.effective_user.id, False)
    await update.message.reply_text(
        "You have opted out. Your contributed training ratings were removed. ✅\n\n"
        "Your linked Goodreads data will still personalise your own summaries "
        "and recommendations."
    )
    
async def button_handler(update, context):
    query = update.callback_query
    await query.answer()                              # acknowledge the tap (stops the loading spinner)

    if query.data == "start_scan":
        await query.message.reply_text(
            "📸 <b>Send me a clear photo of the book’s front cover.</b>\n\n"
            "For the best result:\n"
            "• Keep the title visible\n"
            "• Use good lighting\n"
            "• Avoid blur and glare",
            parse_mode="HTML",
        )
        return

    if query.data == "start_recommend":
        await send_personalized_recommendations(
            query.message,
            query.from_user.id,
        )
        return

    if query.data == "start_goodreads":
        await query.message.reply_text(
            "🔗 <b>Connect your Goodreads history</b>\n\n"
            "Send <code>/goodreads</code> followed by your public profile link.\n\n"
            "Example:\n"
            "<code>/goodreads https://www.goodreads.com/user/show/123456</code>\n\n"
            "I’ll use your ratings to personalize summaries and recommendations.",
            parse_mode="HTML",
        )
        return

    if query.data == "start_help":
        await query.message.reply_text(
            "<b>How WhatDaBook works</b> 📚\n\n"
            "1️⃣ Send a clear photo of a book cover.\n"
            "2️⃣ Get a summary and reasons you may like or dislike it.\n"
            "3️⃣ Connect Goodreads for results based on your reading taste.\n\n"
            "You can return to this menu anytime with /start.",
            parse_mode="HTML",
        )
        return

    if query.data == "training_opt_in":
        user = get_user(query.from_user.id)
        if user is None or user[1] is None:
            await query.message.reply_text(
                "Link Goodreads first with /goodreads before contributing ratings."
            )
            return

        try:
            goodreads_data = json.loads(user[1])
        except (TypeError, json.JSONDecodeError):
            await query.message.reply_text(
                "Your Goodreads data could not be read. Please link it again."
            )
            return

        rated_books = extract_rated_books(goodreads_data)
        set_training_consent(query.from_user.id, True)
        saved_count = replace_contributed_ratings(query.from_user.id, rated_books)
        await query.message.reply_text(
            f"Thank you! ✅ {saved_count} ratings can now help improve the model.\n\n"
            "Training exports exclude your name and Telegram ID. Use /optout anytime."
        )
        return

    if query.data == "training_opt_out":
        set_training_consent(query.from_user.id, False)
        await query.message.reply_text(
            "No problem—your ratings will only be used for your own personalisation."
        )
        return
    
    if query.data == "similar":
        genres = context.user_data.get('genres', [])  # genres saved when the photo was processed
        books = get_similar_books(genres, n=5)         
        
        if not books:
            await query.message.reply_text("No similar books found.")   # was Hinglish
            return
        
        msg = "📚 *Similar Books:*\n\n"
        for title in books:
            msg += f"• {title}\n"
        
        await query.message.reply_text(msg, parse_mode="Markdown")
 

 
 
 


# App handlers

app = Application.builder().token(telegramBot).build()
init_db()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("goodreads",goodreads))
app.add_handler(CommandHandler("recommend", recommend_cmd))  
app.add_handler(CommandHandler("optout", optout))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(CallbackQueryHandler(button_handler)) 
threading.Thread(target=run_flask, daemon=True).start()
app.run_polling()




