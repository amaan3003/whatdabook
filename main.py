from telegram import BotCommand, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes,CallbackQueryHandler,CommandHandler
from telegram.error import BadRequest, TelegramError
import asyncio
import os
from html import escape
from pathlib import Path
import tempfile
from dotenv import load_dotenv
from summarizer import suggest_similar_books, summarize
from book_metadata import fetch_recommendation_metadata
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
    extract_user_id,
    find_existing_rating,
    scrape_goodreads,
)
from userBasedMLmodel import recommend_for_user_with_reasons
import json
from google.cloud import vision
from google.api_core.client_options import ClientOptions
from google.api_core.exceptions import GoogleAPICallError
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
    if response.error.message:
        raise RuntimeError("The cover-reading service returned an error.")
    texts = response.text_annotations           
    
    return texts[0].description if texts else "" 


def book_context_from_summary(summary):
    """Recover only non-personal book identity fields from an old bot message."""
    if not isinstance(summary, str):
        return ""

    identity_lines = []
    for line in summary.splitlines():
        cleaned_line = line.replace("*", "").strip()
        normalized_line = cleaned_line.casefold()
        if any(
            label in normalized_line
            for label in ("title:", "author:", "genre:")
        ):
            identity_lines.append(cleaned_line)
    return "\n".join(identity_lines[:3])

 


async def start(update, context):
    user = update.effective_user
    save_user(user.id, user.first_name)
    context.user_data.pop("awaiting_goodreads_link", None)
    context.user_data.pop("awaiting_book_title", None)

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
        [
            InlineKeyboardButton("👤 My profile", callback_data="start_profile"),
            InlineKeyboardButton("❓ How it works", callback_data="start_help"),
        ],
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
    
    
    
async def ask_for_goodreads_link(message, context):
    context.user_data.pop("awaiting_book_title", None)
    context.user_data["awaiting_goodreads_link"] = True
    keyboard = [[
        InlineKeyboardButton("Cancel", callback_data="goodreads_cancel")
    ]]
    await message.reply_text(
        "🔗 <b>Paste your public Goodreads profile link</b>\n\n"
        "It should look like:\n"
        "<code>https://www.goodreads.com/user/show/123456-your-name</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def connect_goodreads(message, telegram_user, context, link):
    if extract_user_id(link) is None:
        await message.reply_text(
            "That doesn’t look like a Goodreads profile link. Please copy the "
            "link from your public Goodreads profile and try again."
        )
        return

    status_message = await message.reply_text("Fetching your Goodreads data... ⏳")
    data = await asyncio.to_thread(scrape_goodreads, link)

    if data is None:
        await status_message.edit_text(
            "I found the profile link, but couldn’t read its book history. Make "
            "sure the profile is public, then paste the link again."
        )
        return

    context.user_data.pop("awaiting_goodreads_link", None)
    user = telegram_user
    save_user(user.id, user.first_name)
    save_goodreads(user.id, data)
    rated_books = extract_rated_books(data)
    rating_word = "rating" if len(rated_books) == 1 else "ratings"

    if has_training_consent(user.id):
        saved_count = replace_contributed_ratings(
            user.id,
            rated_books,
        )
        await status_message.edit_text(
            f"Done! ✅ Imported {len(rated_books)} {rating_word}. Your summaries "
            "and recommendations will now use your reading history. I also "
            f"refreshed {saved_count} contributed ratings.\n\n"
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
    await status_message.edit_text(
        f"Done! ✅ Imported {len(rated_books)} {rating_word}. Your summaries and "
        "recommendations will now use your reading history.\n\nWould you also "
        "like to contribute your book titles and "
        "ratings to improve future recommendations? Your name and Telegram ID "
        "will not be included in training exports, and you can use /optout anytime.",
        reply_markup=InlineKeyboardMarkup(contribution_keyboard),
    )


async def goodreads(update, context):
    context.user_data.pop("awaiting_book_title", None)
    context.user_data["awaiting_goodreads_link"] = True
    if context.args:
        await connect_goodreads(
            update.message,
            update.effective_user,
            context,
            context.args[0],
        )
        return

    await ask_for_goodreads_link(update.message, context)


async def handle_text(update, context):
    text = update.message.text.strip()

    if context.user_data.get("awaiting_goodreads_link"):
        await connect_goodreads(
            update.message,
            update.effective_user,
            context,
            text,
        )
        return

    if not context.user_data.get("awaiting_book_title"):
        return

    if len(text) < 2:
        await update.message.reply_text(
            "Please enter at least two characters from the book title."
        )
        return

    if len(text) > 300:
        await update.message.reply_text(
            "That is a little too long for a title. Please send only the book "
            "title and, if you know it, the author."
        )
        return

    context.user_data.pop("awaiting_book_title", None)
    status_message = await update.message.reply_text(
        "🔎 Looking up that book..."
    )
    await build_book_report(
        update.effective_user.id,
        context,
        text,
        status_message,
    )
 

async def send_recommendation_card(message, recommendation, metadata, position):
    title = escape(recommendation["title"])
    authors = metadata["authors"][:2]
    author_text = escape(", ".join(authors)) if authors else "Author unavailable"
    publication_text = (
        f"\n🗓 First published: {metadata['first_publish_year']}"
        if metadata["first_publish_year"]
        else ""
    )
    source_titles = recommendation["based_on"]
    if len(source_titles) == 1:
        match_reason = f"Recommended from your interest in <i>{escape(source_titles[0])}</i>."
    else:
        formatted_sources = " and ".join(
            f"<i>{escape(source_title)}</i>" for source_title in source_titles
        )
        match_reason = f"Recommended from your interest in {formatted_sources}."

    caption = (
        f"📚 <b>{position}. {title}</b>\n"
        f"✍️ {author_text}"
        f"{publication_text}\n\n"
        f"💡 <b>Why this matches</b>\n{match_reason}"
    )
    buttons = []
    if metadata["details_url"]:
        buttons.append(
            InlineKeyboardButton("📖 Book details", url=metadata["details_url"])
        )
    buttons.append(InlineKeyboardButton("🛒 Find on Amazon", url=metadata["amazon_url"]))
    reply_markup = InlineKeyboardMarkup([buttons])

    if metadata["cover_url"]:
        try:
            await message.reply_photo(
                photo=metadata["cover_url"],
                caption=caption,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
            return
        except TelegramError:
            # The metadata is still useful when Telegram cannot fetch a cover.
            pass

    await message.reply_text(
        caption,
        parse_mode="HTML",
        reply_markup=reply_markup,
    )


async def send_personalized_recommendations(message, user_id):
    user = get_user(user_id)                     # get (name, goodreads_data) from DB

    if user is None or user[1] is None:           # user hasn't linked Goodreads
        await message.reply_text(
            "Connect Goodreads first so I can learn your reading taste.\n\n"
            "Send <code>/goodreads</code>, then paste your public Goodreads "
            "profile link when I ask for it.",
            parse_mode="HTML",
        )
        return

    goodreads_data = user[1]                      # index 1 = goodreads_data column

    status_message = await message.reply_text("Finding books for you... ⏳")

    try:
        data = json.loads(goodreads_data)
    except (TypeError, json.JSONDecodeError):
        await status_message.edit_text(
            "Your saved Goodreads data could not be read. Please link it again "
            "with /goodreads."
        )
        return

    try:
        recommendations = recommend_for_user_with_reasons(data, n=5)
    except (KeyError, TypeError):
        await status_message.edit_text(
            "Your saved Goodreads ratings could not be used. Please refresh them "
            "with /goodreads."
        )
        return

    if not recommendations:
        await status_message.edit_text(
            "I couldn’t find good matches yet—your books may not be in my dataset."
        )
        return

    await status_message.edit_text("✨ Turning your recommendations into book cards...")
    metadata_results = await asyncio.to_thread(
        fetch_recommendation_metadata,
        [recommendation["title"] for recommendation in recommendations],
    )
    await status_message.edit_text(
        f"🎯 <b>{len(recommendations)} personalized picks for you</b>\n\n"
        "Each match is connected to a book from your Goodreads history.",
        parse_mode="HTML",
    )

    for position, (recommendation, metadata) in enumerate(
        zip(recommendations, metadata_results),
        start=1,
    ):
        await send_recommendation_card(
            message,
            recommendation,
            metadata,
            position,
        )


async def recommend_cmd(update, context):
    context.user_data.pop("awaiting_goodreads_link", None)
    context.user_data.pop("awaiting_book_title", None)
    await send_personalized_recommendations(
        update.message,
        update.effective_user.id,
    )


async def send_profile(message, telegram_user):
    save_user(telegram_user.id, telegram_user.first_name)
    user = get_user(telegram_user.id)
    goodreads_data = user[1] if user is not None else None

    rated_books = []
    goodreads_status = "Not connected"
    match_status = "Unavailable until Goodreads is connected"
    goodreads_button = "🔗 Connect Goodreads"

    if goodreads_data is not None:
        try:
            rated_books = extract_rated_books(json.loads(goodreads_data))
        except (TypeError, json.JSONDecodeError):
            goodreads_status = "Needs to be connected again"
            match_status = "Unavailable until Goodreads is refreshed"
        else:
            goodreads_status = "Connected ✅"
            match_status = (
                "Ready ✅" if rated_books else "Needs at least one rated book"
            )
            goodreads_button = "🔄 Refresh Goodreads"

    contribution_status = (
        "Enabled ✅" if has_training_consent(telegram_user.id) else "Not enabled"
    )
    keyboard = [
        [InlineKeyboardButton(goodreads_button, callback_data="start_goodreads")],
        [InlineKeyboardButton("🎯 Get recommendations", callback_data="start_recommend")],
    ]

    await message.reply_text(
        f"👤 <b>{escape(telegram_user.first_name)}’s WhatDaBook profile</b>\n\n"
        f"<b>Goodreads:</b> {goodreads_status}\n"
        f"<b>Ratings available:</b> {len(rated_books)}\n"
        f"<b>Personal Match:</b> {match_status}\n"
        f"<b>Training contribution:</b> {contribution_status}\n\n"
        "Your Goodreads history personalizes your own results. Training "
        "contribution is optional and can be disabled with /optout.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def profile_cmd(update, context):
    context.user_data.pop("awaiting_goodreads_link", None)
    context.user_data.pop("awaiting_book_title", None)
    await send_profile(update.message, update.effective_user)


async def build_book_report(user_id, context, book_text, status_message):
    """Build the same book report whether text came from OCR or user input."""
    reading_profile = None
    user = get_user(user_id)
    if user is not None and user[1] is not None:
        try:
            goodreads_data = json.loads(user[1])
            reading_profile = build_reading_profile(goodreads_data)
            existing_rating = find_existing_rating(book_text, goodreads_data)
            if existing_rating is not None:
                reading_profile = dict(reading_profile or {})
                reading_profile["existing_rating"] = existing_rating
        except (TypeError, json.JSONDecodeError):
            # Broken saved data should not prevent the normal summary.
            reading_profile = None

    report_type = "personalized book report" if reading_profile else "book report"
    await status_message.edit_text(f"🧠 Building your {report_type}...")

    try:
        summary = await asyncio.to_thread(summarize, book_text, reading_profile)
    except (RuntimeError, ValueError):
        await status_message.edit_text(
            "I couldn’t create the book report right now. Please try again shortly."
        )
        return

    context.user_data["genres"] = get_genres(summary)
    context.user_data["last_book_text"] = book_text
    context.user_data.pop("similar_books", None)
    context.user_data.pop("similar_books_source", None)
    context.user_data.pop("similar_result_shown", None)
    context.user_data.pop("similar_lookup_in_progress", None)

    keyboard = [[InlineKeyboardButton("📚 Similar Books", callback_data="similar")]]

    try:
        await status_message.edit_text(
            summary,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    except BadRequest:
        # A title containing Markdown punctuation should not lose the result.
        await status_message.edit_text(
            summary,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


async def handle_photo(update, context):
    context.user_data.pop("awaiting_goodreads_link", None)
    context.user_data.pop("awaiting_book_title", None)
    status_message = await update.message.reply_text(
        "📥 Photo received. Getting it ready..."
    )

    image_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as image_file:
            image_path = Path(image_file.name)

        photo = update.message.photo[-1]
        file = await photo.get_file()
        await file.download_to_drive(image_path)
        await status_message.edit_text("🔍 Reading the title and cover text...")
        book_text = await asyncio.to_thread(ocr, str(image_path))
    except (OSError, RuntimeError, GoogleAPICallError, TelegramError):
        await status_message.edit_text(
            "I couldn’t process that photo right now. You can try another photo "
            "or type the book title instead.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "⌨️ Type book title",
                    callback_data="type_book_title",
                )
            ]]),
        )
        return
    finally:
        if image_path is not None:
            image_path.unlink(missing_ok=True)

    if not book_text.strip():
        await status_message.edit_text(
            "I couldn’t read any text on that cover. 📸\n\n"
            "Try again with the front cover filling the frame, good lighting, "
            "and as little glare as possible—or type the title instead.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "⌨️ Type book title",
                    callback_data="type_book_title",
                )
            ]]),
        )
        return

    await build_book_report(
        update.effective_user.id,
        context,
        book_text,
        status_message,
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
        context.user_data.pop("awaiting_goodreads_link", None)
        context.user_data.pop("awaiting_book_title", None)
        await query.message.reply_text(
            "📸 <b>Take a photo of the book’s front cover</b>\n\n"
            "Tap Telegram’s attachment or camera icon below, choose "
            "<b>Camera</b>, and send the photo.\n\n"
            "For the best result:\n"
            "• Keep the title visible\n"
            "• Use good lighting\n"
            "• Avoid blur and glare",
            parse_mode="HTML",
        )
        return

    if query.data == "type_book_title":
        context.user_data.pop("awaiting_goodreads_link", None)
        context.user_data["awaiting_book_title"] = True
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except TelegramError:
            pass
        await query.message.reply_text(
            "⌨️ <b>Type the book title</b>\n\n"
            "You can include the author for a more accurate result, for example:\n"
            "<code>The Kite Runner by Khaled Hosseini</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Cancel", callback_data="book_title_cancel")
            ]]),
        )
        return

    if query.data == "book_title_cancel":
        context.user_data.pop("awaiting_book_title", None)
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("Book title entry cancelled.")
        return

    if query.data == "start_recommend":
        context.user_data.pop("awaiting_goodreads_link", None)
        context.user_data.pop("awaiting_book_title", None)
        await send_personalized_recommendations(
            query.message,
            query.from_user.id,
        )
        return

    if query.data == "start_goodreads":
        await ask_for_goodreads_link(query.message, context)
        return

    if query.data == "goodreads_cancel":
        context.user_data.pop("awaiting_goodreads_link", None)
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("Goodreads connection cancelled.")
        return

    if query.data == "start_profile":
        context.user_data.pop("awaiting_goodreads_link", None)
        context.user_data.pop("awaiting_book_title", None)
        await send_profile(query.message, query.from_user)
        return

    if query.data == "start_help":
        context.user_data.pop("awaiting_goodreads_link", None)
        context.user_data.pop("awaiting_book_title", None)
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
        if context.user_data.get("similar_result_shown"):
            return
        if context.user_data.get("similar_lookup_in_progress"):
            return

        context.user_data["similar_lookup_in_progress"] = True
        try:
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except TelegramError:
                pass

            status_message = None
            message_text = query.message.text or query.message.caption or ""
            genres = context.user_data.get("genres") or get_genres(message_text)

            if "similar_books" in context.user_data:
                books = context.user_data["similar_books"]
                source = context.user_data.get("similar_books_source", "local")
            else:
                books = get_similar_books(genres, n=5)
                source = "local"

                if not books:
                    status_message = await query.message.reply_text(
                        "🔎 My local catalog didn’t have a strong match. "
                        "Trying a wider book search..."
                    )
                    book_context = context.user_data.get("last_book_text")
                    if not book_context:
                        book_context = book_context_from_summary(message_text)

                    try:
                        books = await asyncio.to_thread(
                            suggest_similar_books,
                            book_context,
                            genres,
                            5,
                        )
                    except RuntimeError:
                        books = []
                    source = "deepseek"

                context.user_data["similar_books"] = books
                context.user_data["similar_books_source"] = source

            if not books:
                failure_message = (
                    "The wider book search is temporarily unavailable. Please "
                    "send the cover again or try shortly."
                )
                if status_message:
                    await status_message.edit_text(failure_message)
                else:
                    await query.message.reply_text(failure_message)
                context.user_data["similar_result_shown"] = True
                return

            heading = (
                "✨ <b>Similar books from the wider AI search</b>"
                if source == "deepseek"
                else "📚 <b>Similar books</b>"
            )
            result_message = heading + "\n\n" + "\n".join(
                f"• {escape(title)}" for title in books
            )
            if source == "deepseek":
                result_message += (
                    "\n\n<i>Used because the local genre catalog had no match.</i>"
                )

            if status_message:
                await status_message.edit_text(result_message, parse_mode="HTML")
            else:
                await query.message.reply_text(result_message, parse_mode="HTML")
            context.user_data["similar_result_shown"] = True
        finally:
            context.user_data["similar_lookup_in_progress"] = False
 

async def register_bot_commands(application):
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Open the WhatDaBook menu"),
            BotCommand("profile", "View your personalization status"),
            BotCommand("goodreads", "Connect or refresh Goodreads"),
            BotCommand("recommend", "Get personalized book recommendations"),
            BotCommand("optout", "Remove contributed training ratings"),
        ]
    )


 
 
 


# App handlers

app = (
    Application.builder()
    .token(telegramBot)
    .post_init(register_bot_commands)
    .build()
)
init_db()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("goodreads",goodreads))
app.add_handler(CommandHandler("recommend", recommend_cmd))  
app.add_handler(CommandHandler("profile", profile_cmd))
app.add_handler(CommandHandler("optout", optout))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
app.add_handler(CallbackQueryHandler(button_handler)) 
threading.Thread(target=run_flask, daemon=True).start()
app.run_polling()




