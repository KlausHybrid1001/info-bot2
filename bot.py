import os
import requests
import asyncio
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from pyppeteer import launch
import fitz  # PyMuPDF

# Your bot token (replace this with your actual bot token)
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Path to the locally installed Chromium executable
CHROMIUM_PATH = r"C:\Program Files\Chromium\Application\chrome.exe"  # Adjust if needed

# Directory paths
tmp_folder = r"C:\Users\AJAY\Desktop\DL INFO\tmp"
output_folder = r"C:\Users\AJAY\Desktop\DL INFO"

# HTTP headers and cookies (make sure to use the latest ones if they change)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Referer": "https://sarathi.parivahan.gov.in/sarathiservice/relApplnSearch.do",
    "Cookie": "JSESSIONID=3899D603FD2EACF9C7678AEB5152EE12; _ga_W8LPQ3GPJF=deleted; _gid=GA1.3.2141960273.1735205718; GOTWL_MODE=2; _ga=GA1.1.1181027328.1735205717; STATEID=dklEcFJuUWtUd2FTYjdINVBvMDhJdz09"
}

# Function to convert HTML to PDF using Pyppeteer (full HTML)
async def convert_html_to_pdf(input_html, output_pdf):
    try:
        # Launch Chromium using the local path
        browser = await launch(
            headless=True,
            executablePath=CHROMIUM_PATH,  # Use locally installed Chromium
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        page = await browser.newPage()

        # Set the HTML content of the page
        with open(input_html, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        if not html_content:
            print("[ERROR] HTML content is empty!")
            return None
        
        await page.setContent(html_content)

        # Debug: Wait for the page to load completely
        print("[DEBUG] Waiting for the page to load...")
        await page.waitForSelector('body')  # Wait for the body to be loaded
        await asyncio.sleep(2)  # Give it a bit more time to ensure proper rendering

        # Convert the HTML content to PDF (for the entire page)
        await page.pdf({
            'path': output_pdf,
            'printBackground': True
        })

        print(f"[INFO] Full PDF saved at: {output_pdf}")
        await browser.close()
        return output_pdf
    except Exception as e:
        print(f"[ERROR] Error converting HTML to PDF: {e}")
        if browser:
            await browser.close()
        return None

# Function to crop the first page of the generated PDF using PyMuPDF (fitz)
def crop_pdf(input_pdf, output_pdf):
    try:
        pdf_document = fitz.open(input_pdf)

        # Extract the first page (page index is 0-based)
        first_page = pdf_document.load_page(0)

        # Get the page height and set cropping (100 points from top and bottom)
        page_height = first_page.rect.height
        crop_top = 165
        crop_bottom = 5

        # Define the cropping rectangle (left, top, right, bottom)
        crop_rect = fitz.Rect(0, crop_top, first_page.rect.width, page_height - crop_bottom)

        # Crop the first page by applying the crop rectangle
        first_page.set_cropbox(crop_rect)

        # Create a new PDF for the cropped first page
        cropped_pdf = fitz.open()

        # Insert the cropped first page into the new PDF
        cropped_pdf.insert_pdf(pdf_document, from_page=0, to_page=0)

        # Save the cropped PDF with the DL number
        cropped_pdf.save(output_pdf)
        print(f"[INFO] Cropped PDF saved at: {output_pdf}")

        # Close the documents
        pdf_document.close()
        cropped_pdf.close()

        return output_pdf
    except Exception as e:
        print(f"[ERROR] Error cropping PDF: {e}")
        return None

# Function to send the PDF to the user via Telegram bot
async def send_pdf_to_telegram(update: Update, context: ContextTypes.DEFAULT_TYPE, pdf_filename):
    try:
        bot = Bot(token=BOT_TOKEN)
        with open(pdf_filename, "rb") as pdf_file:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=pdf_file,
                filename=os.path.basename(pdf_filename),
                caption="Here is your DL INFO."
            )
        print(f"PDF {pdf_filename} sent successfully!")
    except Exception as e:
        print(f"Failed to send PDF: {e}")
        await update.message.reply_text("Failed to send the PDF file. Please try again.")

# Start command to welcome users
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome! Send the DL number directly to get the PDF.")

# Message handler for direct input (DL number)
async def handle_dl_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dl_number = update.message.text.strip()

    if not dl_number:
        await update.message.reply_text("❌ Please provide a valid DL number.")
        return

    html_filename = os.path.join(tmp_folder, f"{dl_number}_details.html")
    pdf_filename = os.path.join(tmp_folder, f"{dl_number}_details.pdf")
    cropped_pdf_filename = os.path.join(output_folder, f"{dl_number}_cropped.pdf")

    # Check if the cropped PDF already exists
    if os.path.exists(cropped_pdf_filename):
        await update.message.reply_text("✅ PDF already exists. Sending the existing file...")
        await send_pdf_to_telegram(update, context, cropped_pdf_filename)
        return

    # URL for fetching DL details
    url = f"https://sarathi.parivahan.gov.in/sarathiservice/dlDetailsResult.do?reqDlNumber={dl_number}"

    try:
        # Send processing message
        await update.message.reply_text(f"⏳ Fetching DL details for {dl_number}. Please wait...")

        # Fetch the webpage content with headers and cookies
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            # Save the HTML content to a file
            with open(html_filename, "w", encoding="utf-8") as file:
                file.write(response.text)
            print(f"[DEBUG] HTML file saved at: {html_filename}")

            # Convert HTML to PDF (for the full document)
            pdf_filename = await convert_html_to_pdf(html_filename, pdf_filename)

            if pdf_filename is None:
                await update.message.reply_text("❌ Error while converting HTML to PDF. Please try again.")
                return

            # Crop the first page and save it as a new PDF
            cropped_pdf_filename = crop_pdf(pdf_filename, cropped_pdf_filename)

            if cropped_pdf_filename is None:
                await update.message.reply_text("❌ Error while cropping the PDF. Please try again.")
                return

            # Send the cropped PDF to the user
            await send_pdf_to_telegram(update, context, cropped_pdf_filename)

            # Cleanup the HTML and original PDF after processing
            os.remove(html_filename)
            os.remove(pdf_filename)
        else:
            await update.message.reply_text(f"❌ Failed to fetch details. HTTP Status Code: {response.status_code}")
    except Exception as e:
        await update.message.reply_text(f"⚠️ An error occurred: {str(e)}")

# Main function to start the bot
def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    
    # Add message handler for user input (DL number)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_dl_number))

    # Start the bot
    application.run_polling()

# Start the bot
if __name__ == "__main__":
    main()
