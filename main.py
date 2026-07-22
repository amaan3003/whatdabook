import easyocr
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import os
from dotenv import load_dotenv
from summerizer import summarize

load_dotenv()

telegramBot = os.getenv("TELEGRAM_TOKEN")

if not telegramBot:
    raise ValueError("API_KEY not found in environment")

print(summarize("""Frank Herbert’s 1965 sci-fi epic, Dune, is set in a distant, feudal future. It follows young Paul Atreides as his noble family takes control of the harsh desert planet Arrakis. Arrakis is the only source of "spice," a resource vital for interstellar travel and human longevity, making it a prime target for deadly political betrayal.The Core PlotThe Setup: The Padishah Emperor tasks House Atreides with governing Arrakis (also called Dune). This is secretly a trap designed to destroy the Atreides family by pitting them against their long-standing rivals, the Harkonnens.The Spice: The desert is the universe's only source of "melange," or "spice". This highly addictive substance grants extended life, heightened consciousness, and the precognition required by space navigators to safely travel between planets.The Survival: After his family is betrayed and destroyed, Paul flees into the deep desert. He aligns with the Fremen, the native inhabitants of Arrakis, who possess a deep, symbiotic relationship with the planet's brutal ecology and giant sandworms.The Ascension: Paul learns the ways of the desert, evolves into the mysterious messianic leader Muad'Dib, and uses both his new abilities and the Fremen's fierce military power to exact revenge and seize control of the universe.Key Themes & IdeasEcology: The story deeply examines environmentalism and the complex, brutal ecosystem of a planet struggling with extreme water scarcity.The Dangers of Messiahs: Unlike traditional heroic journeys, Dune serves as a cautionary tale about the perils of blindly following charismatic leaders and the devastating holy wars (jihads) they can provoke.Religion & Politics: It explores how ruling classes artificially engineer myths, prophecies, and religious fervor to control populations and extract resources.Would you like to know more about the specific factions (like the Bene Gesserit or the Fremen), or are you looking for details on how to read the rest of the book series?""")) 

def ocr(path):
    reader = easyocr.Reader(['en'], gpu=False)
    result = reader.readtext(path)
    return " ".join([text for _, text, conf in result if conf > 0.3])
 
 
async def handle_photo(update, context):
    photo = update.message.photo[-1]             
    file = await photo.get_file()                 
    await file.download_to_drive("incoming.jpg")  
    await update.message.reply_text(ocr("incoming.jpg"))
 
 
app = Application.builder().token(telegramBot).build()
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.run_polling()