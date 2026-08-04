import easyocr
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes,CallbackQueryHandler,CommandHandler
import os
from dotenv import load_dotenv
from summarizer import summarize
from recommendationModel import get_genres,get_similar_books
from db import init_db, save_user, get_user,save_goodreads
from bookRatingScraper import scrape_goodreads
from userBasedMLmodel import recommend_for_user
import json
load_dotenv()

telegramBot = os.getenv("TELEGRAM_TOKEN")


if not telegramBot:
    raise ValueError("API_KEY not found in environment")


reader = easyocr.Reader(['en'], gpu=False)



def ocr(path):
    result = reader.readtext(path)
    return " ".join([text for _, text, conf in result if conf > 0.3])
 
 


async def start(update, context):
    user = update.effective_user
    save_user(user.id, user.first_name)
    await update.message.reply_text(f"Welcome {user.first_name}! 📚\n\nSend a book cover photo to get started.\nOr use /goodreads to link your profile for personalized recommendations.")
    
    
    
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

    save_goodreads(update.effective_user.id, data)          # DB mein daalo
    await update.message.reply_text("Done! ✅ You'll now get personalized recommendations.")
 

async def recommend_cmd(update, context):
    user_id = update.effective_user.id
    user = get_user(user_id)                     # get (name, goodreads_data) from DB

    goodreads_data = user[1]                      # index 1 = goodreads_data column

    if goodreads_data is None:                    # user hasn't linked Goodreads
        await update.message.reply_text("Link your Goodreads first with /goodreads to get personalized recommendations!")
        return

    await update.message.reply_text("Finding books for you... ⏳")

    data = json.loads(goodreads_data)             # string -> structure
    recs = recommend_for_user(data, n=5)          # get recommendations from the model

    if not recs:                                  # empty (no matching books found)
        await update.message.reply_text("Couldn't find good matches yet — your books might not be in my dataset.")
        return

    msg = "📚 *Recommended for you:*\n\n" + "".join(f"• {b}\n" for b in recs)
    await update.message.reply_text(msg, parse_mode="Markdown")

async def handle_photo(update, context):
    photo = update.message.photo[-1]             
    file = await photo.get_file()                 
    await file.download_to_drive("incoming.jpg")  
    
    summary = summarize(ocr("incoming.jpg"))       
    
    context.user_data['genres'] = get_genres(summary)   
    
    keyboard = [[InlineKeyboardButton("📚 Similar Books", callback_data="similar")]]  
    
    await update.message.reply_text(
        summary,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)     
    )
    
async def button_handler(update, context):
    query = update.callback_query
    await query.answer()                              # acknowledge the tap (stops the loading spinner)
    
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
 

 
app = Application.builder().token(telegramBot).build()
init_db()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("goodreads",goodreads))
app.add_handler(CommandHandler("recommend", recommend_cmd))  
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(CallbackQueryHandler(button_handler)) 
app.run_polling()




