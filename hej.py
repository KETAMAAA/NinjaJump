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
import requests

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

# Function to clean and extract text from HTML content
def clean_html(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')

    # Remove scripts, styles, comments, and other unwanted tags
    for tag in soup(["script", "style", "head", "title", "meta", "[document]", "noscript"]):
        tag.decompose()

    # Extract text and decode HTML entities
    text = soup.get_text(separator=" ")

    # Decode HTML entities
    text = unescape(text)

    # Remove extra spaces, new lines, tabs, and unnecessary line breaks
    text = re.sub(r'\s+', ' ', text).strip()

    # Remove empty lines or lines with only spaces
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    # Combine lines into a clean text block
    cleaned_text = ' '.join(lines)

    return cleaned_text

# Enhanced detection of auto-responses and other irrelevant emails
def is_auto_response(subject, from_, body, msg):
    # List of common phrases in auto-responses, in both English and Swedish
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
        "ärende"
    ]

    # Additional checks for common auto-responses
    if any([
        "MAILER-DAEMON" in from_,
        "Undelivered Mail Returned to Sender" in subject,
        "no-reply@account.hostinger.com" in from_,
        "Email sending limits reached" in subject,
        re.search(r'postmaster@', from_) and re.search(r'Undeliverable', subject),
        re.search(r'(?i)(autosvar|automatic reply|ärendenummer|AUTOSVAR|out of office|autoreply|out-of-office)', subject),
        msg.get("Precedence") in ["bulk", "list", "auto_reply"],
        "noreply" in from_.lower(),
    ]):
        return True

    # Check if any of these phrases are in the subject, sender field, or body content
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
                            try:
                                body = part.get_payload(decode=True).decode(part.get_content_charset(), errors='replace')
                            except Exception as e:
                                print(f"Failed to decode email part: {e}")
                            break
                        elif content_type == "text/html":
                            try:
                                html_content = part.get_payload(decode=True).decode(part.get_content_charset(), errors='replace')
                                body = clean_html(html_content)
                            except Exception as e:
                                print(f"Failed to decode email part: {e}")
                            break
            else:
                content_type = msg.get_content_type()
                try:
                    if content_type == "text/plain":
                        body = msg.get_payload(decode=True).decode(msg.get_content_charset(), errors='replace')
                    elif content_type == "text/html":
                        html_content = msg.get_payload(decode=True).decode(msg.get_content_charset(), errors='replace')
                        body = clean_html(html_content)
                except Exception as e:
                    print(f"Failed to decode email: {e}")

            # Check if the email is an auto-response
            if is_auto_response(subject, from_, body):
                print(f"Skipped auto-response from {from_}")
                continue

            # Create a preview of the message (first 150 characters)
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
        # Request the login link from the PHP backend service
        backend_url = "https://truevision.se/emails.php"
        response = requests.post(backend_url, data={'email': account['email'], 'password': account['password']})
        
        if response.status_code == 200:
            login_link = response.json().get('login_link')
        else:
            login_link = "https://mail.hostinger.com/"  # Fallback to generic link if token generation fails
        
        # Create a button with a link to respond to the email
        button = discord.ui.Button(label="📧 📧  SVARA HÄR  📧 📧", style=discord.ButtonStyle.link, url=login_link)
        view = discord.ui.View()
        view.add_item(button)

        # Create an embed message to display email details in Discord
        embed = discord.Embed(
            title="💰 Nytt Meddelande Mottaget! 💰",
            description="Här är detaljerna för ditt senaste e-postmeddelande:",
            color=discord.Color.green()
        )
        embed.add_field(name="👤 **Från:**", value=f"```{from_}```", inline=False)
        embed.add_field(name="📌 **Ämne:**", value=f"```{subject}```", inline=False)
        embed.add_field(name="🔍 **Förhandsvisning:**", value=f"```{preview}```", inline=False)

        # Send the embed message and the button to Discord
        await channel.send(embed=embed, view=view)
@bot.event
async def on_ready():
    await fetch_unseen_emails()  # Fetch and send emails to Discord
    await bot.close()  # Close the bot when done

if __name__ == "__main__":
    bot.run(DISCORD_BOT_TOKEN)
