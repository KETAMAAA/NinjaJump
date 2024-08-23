import os
import imaplib
import email
from email.header import decode_header
import re
import discord
from discord.ext import commands
import asyncio
from bs4 import BeautifulSoup
from datetime import datetime
from html import unescape

# IMAP account and server information
account = {
    'email': os.getenv('EMAIL_ACCOUNT'),
    'password': os.getenv('EMAIL_PASSWORD'),
    'imap_server': 'imap.hostinger.com'
}

# Discord bot token from environment variables
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# Function to decode email headers containing special characters
def decode_mime_words(s):
    return ''.join(
        str(part, encoding or 'utf-8') if isinstance(part, bytes) else part
        for part, encoding in email.header.decode_header(s)
    )

# Funktion för att rensa och extrahera text från HTML-innehåll
def clean_html(html_content):
    # Försök att automatiskt reparera trasig HTML
    soup = BeautifulSoup(html_content, 'html.parser')

    # Ta bort skript, stilar, kommentarer och andra oönskade taggar
    for tag in soup(["script", "style", "head", "title", "meta", "[document]", "noscript"]):
        tag.decompose()

    # Extrahera text och avkoda HTML-entiteter
    text = soup.get_text(separator=" ")

    # Avkoda HTML-entiteter
    text = unescape(text)

    # Ta bort extra mellanslag, nya rader, flikar, och onödiga radbrytningar
    text = re.sub(r'\s+', ' ', text).strip()

    # Ta bort tomma rader eller linjer med endast mellanslag
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    # Sammanfoga linjer till ett rent textblock
    cleaned_text = ' '.join(lines)

    return cleaned_text

# Förbättrad detektering av autosvar
def is_auto_response(subject, from_, body):
    # Lista över vanliga fraser i autosvar, både på engelska och svenska
    auto_response_phrases = [
        "detta är ett automatiskt svar",  # Swedish: "this is an automated response"
        "detta är ett automatiserat meddelande",  # Swedish
        "do not reply to this email",  # English
        "svara inte på detta e-postmeddelande",  # Swedish: "do not reply to this email"
        "tack för att du kontaktade oss",  # Swedish: "thank you for contacting us"
        "tack för ditt meddelande",  # Swedish: "thank you for your message"
        "your message has been received",  # English
        "vi har mottagit ditt meddelande",  # Swedish: "we have received your message"
        "detta är ett automatiskt genererat meddelande",  # Swedish: "this is an auto-generated message"
        "automated response",  # English
        "vi återkommer så snart vi kan",  # Swedish: "we will get back to you as soon as we can"
        "we will get back to you shortly",  # English
        "out of office",  # English
        "out-of-office",  # English
        "jag är för närvarande inte tillgänglig",  # Swedish: "I am currently unavailable"
        "jag är på semester",  # Swedish: "I am on vacation"
        "kommer att vara borta",  # Swedish: "will be away"
        "automatisk bekräftelse",  # Swedish: "automatic confirmation"
        "mail delivery failed",  # English: Common error message
        "mail delivery subsystem",  # English: Mailer Daemon error
        "undelivered mail returned to sender",  # English
        "ditt ärende har registrerats",  # Swedish: "your case has been registered"
        "ärendenummer",  # Swedish: "case number"
        "bekräftelse på ditt ärende",  # Swedish: "confirmation of your case"
        "thank you for your email",  # English
        "your case has been logged",  # English
        "we appreciate your contact",  # English
        "din förfrågan har mottagits",  # Swedish: "your request has been received"
        "we have received your request",  # English
        "response will be delayed",  # English
        "fått ditt meddelande",  # Swedish: "received your message"
        "bekräftelsemail",  # Swedish: "confirmation email"
        "automatgenererat meddelande",  # Swedish: "auto-generated message"
        "do not reply",  # English: Common auto-response phrase
        "do not respond",  # English: Common auto-response phrase
        "autoreply",  # English: Common auto-response phrase
        "noreply",  # English: Common auto-response phrase
        "autoresponder",  # English: Common auto-response phrase
        "detta är ett automatiserat svar",  # Swedish
        "please do not respond",  # English
        "this mailbox is unattended",  # English
        "this is an unattended mailbox",  # English
        "vi behandlar ditt ärende",  # Swedish: "we are processing your case"
        "tack för ditt mejl",  # Swedish: "thank you for your email"
    ]

    # Kontrollera om någon av dessa fraser finns i ämnesraden, avsändarfältet eller kroppsinnehållet
    for phrase in auto_response_phrases:
        if phrase.lower() in subject.lower() or phrase.lower() in from_.lower() or phrase.lower() in body.lower():
            return True

    return False



# Asynchronous function to fetch unseen emails
async def fetch_unseen_emails():
    try:
        # Connect to IMAP server
        mail = imaplib.IMAP4_SSL(account['imap_server'])
        mail.login(account['email'], account['password'])
        mail.select("inbox")

        # Search for unseen emails
        status, messages = mail.search(None, '(UNSEEN)')
        email_ids = messages[0].split()

        for email_id in email_ids:
            # Fetch the email message by ID
            status, msg_data = mail.fetch(email_id, '(RFC822)')
            msg = email.message_from_bytes(msg_data[0][1])

            # Decode email subject and sender
            subject = decode_mime_words(msg["Subject"])
            from_ = decode_mime_words(msg.get("From"))

            # Get email body content
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get("Content-Disposition"))

                    if "attachment" not in content_disposition:
                        if content_type == "text/plain":
                            body = part.get_payload(decode=True).decode("utf-8")
                            break
                        elif content_type == "text/html":
                            html_content = part.get_payload(decode=True).decode("utf-8")
                            body = clean_html(html_content)
                            break
            else:
                content_type = msg.get_content_type()
                if content_type == "text/plain":
                    body = msg.get_payload(decode=True).decode("utf-8")
                elif content_type == "text/html":
                    html_content = msg.get_payload(decode=True).decode("utf-8")
                    body = clean_html(html_content)

            # Check if the email is an auto-response
            if is_auto_response(subject, from_, body):
                print(f"Skipped auto-response from {from_}")
                continue

            # Create a preview of the message (first 100 characters)
            preview = (body[:150] + '...') if len(body) > 150 else body

            # Send email details to Discord
            await send_email_to_discord(subject, from_, preview)

        # Logout from the server
        mail.logout()

    except Exception as e:
        print(f"Error fetching emails: {e}")

# Function to send email details to Discord
async def send_email_to_discord(subject, from_, preview):
    channel = bot.get_channel(1274024103350894622)  # Set your Discord channel ID here
    if channel:
        button = discord.ui.Button(label="📧 📧  SVARA HÄR  📧 📧", style=discord.ButtonStyle.link, url=f"https://mail.hostinger.com/?clearSession=true&_user={account['email']}")
        view = discord.ui.View()
        view.add_item(button)

        embed = discord.Embed(
            title="💰 Nytt Meddelande Mottaget! 💰",
            description="Här är detaljerna för ditt senaste e-postmeddelande:",
            color=discord.Color.green()
        )
        embed.add_field(name="👤 **Från:**", value=f"```{from_}```", inline=False)
        embed.add_field(name="📌 **Ämne:**", value=f"```{subject}```", inline=False)
        embed.add_field(name="🔍 **Förhandsvisning:**", value=f"```{preview}```", inline=False)

        await channel.send(embed=embed, view=view)

@bot.event
async def on_ready():
    await fetch_unseen_emails()  # Fetch and send emails to Discord
    await bot.close()  # Close the bot when done

if __name__ == "__main__":
    bot.run(DISCORD_BOT_TOKEN)
