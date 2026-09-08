"""Compatibility entry point for ``python main.py``."""

from scraperbot.main import run


if __name__ == "__main__":
    run()

#telegrambot handlers
async def start(update: Update, context: CallbackContext):
    
    await update.message.reply_text(
        "Welcome! One reply at a time please. Please choose a site:\n"
        "Available sites: yuyutei, bigweb"
    )
    return SITE

async def handle_site(update: Update, context: CallbackContext):
    
    site = update.message.text.lower().strip()
    
    if site not in scrapers:
        await update.message.reply_text(
            "Invalid site. Please choose from: " + 
            ", ".join(scrapers.keys())
        )
        return SITE
    
    context.user_data['site'] = site
    await update.message.reply_text("Enter the set number (e.g. dzbt01):")
    return SET_NUMBER

async def handle_set_number(update: Update, context: CallbackContext):

    set_number = update.message.text.strip().upper()
    context.user_data['set_number'] = set_number
    await update.message.reply_text("Enter the rarity (e.g. FFR):")
    return RARITY

async def handle_rarity(update: Update, context: CallbackContext):

    site = context.user_data['site']
    set_number = context.user_data['set_number']
    rarity = update.message.text.strip().upper()
    
    try:
        loading_message = await update.message.reply_text("Loading...")
        scraper = scrapers[site]
        url = scraper.construct_url(set_number, rarity)
        page_content = await scraper.fetch_page(url)
        cards = await scraper.parse_cards(page_content, rarity)
        
        if not cards:
            await loading_message.edit_text("No cards found.")
        else:
            result = "\n".join(
                f"{card['name']}: {card['price']}" for card in cards
            )
            await loading_message.edit_text(result)
    
    except Exception as e:
        log_error(e)
        await update.message.reply_text(
            "An error occurred while processing your request."
        )
    
    return ConversationHandler.END

async def cancel(update: Update, context: CallbackContext):

    await update.message.reply_text(
        "Operation cancelled. You can start again by typing /start."
    )
    return ConversationHandler.END

#Endpoints
@app.post("/webhook")
async def handle_webhook(request: Request):

    try:
        update = Update.de_json(await request.json(), app.state.bot_application.bot)
        await app.state.bot_application.process_update(update)
        return {"status": "ok"}
    except Exception as e:
        log_error(e)
        return JSONResponse(
            status_code=500, 
            content={"error": "Webhook processing failed"}
        )

@app.get("/")
def read_root():
    return {"message": "Telegram Scraper Bot is running"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
