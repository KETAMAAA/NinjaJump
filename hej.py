import imaplib
import email
from email.header import decode_header
import re
import discord
from discord.ext import commands
import asyncio

# IMAP-konto och serverinformation
account = {
    'email': 'kim@mail.truevision.se',
    'password': 'SuperLemon.123',
    'imap_server': 'imap.hostinger.com'
}

# Discord bot token
DISCORD_BOT_TOKEN = 'MTI3NjMxMjA2MDYxNTA2OTc2Ng.GuvOu8.eCWxgqHmDfSOVIQuiRlM_At06LPQP0_CIeMJ4M'

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# Anslutning till IMAP-servern
def connect_to_imap():
    mail = imaplib.IMAP4_SSL(account['imap_server'])
    mail.login(account['email'], account['password'])
    return mail

# Funktion för att dekoda e-postheaderar som kan innehålla ÅÄÖ
def decode_mime_words(s):
    return ''.join(
        str(part, encoding or 'utf-8') if isinstance(part, bytes) else part
        for part, encoding in email.header.decode_header(s)
    )

# Asynkron funktion för att hämta osedda e-postmeddelanden
async def fetch_unseen_emails(mail):
    try:
        mail.select("inbox")

        # Sök efter osedda e-postmeddelanden
        status, messages = mail.search(None, '(UNSEEN)')
        email_ids = messages[0].split()

        for email_id in email_ids:
            # Hämta e-postmeddelandet
            status, msg_data = mail.fetch(email_id, '(RFC822)')
            msg = email.message_from_bytes(msg_data[0][1])

            # Dekodera e-posthuvud
            subject = decode_mime_words(msg["Subject"])
            from_ = decode_mime_words(msg.get("From"))

            # Kontrollera om e-postmeddelandet är ett autosvar eller liknande
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
                continue

            # Hämta kroppsinnehåll
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get("Content-Disposition"))

                    if "attachment" not in content_disposition:
                        if content_type == "text/plain":
                            body = part.get_payload(decode=True).decode("utf-8")
                            break
            else:
                body = msg.get_payload(decode=True).decode("utf-8")

            # Skapa en förhandsvisning av meddelandet (första 100 tecken)
            preview = (body[:100] + '...') if len(body) > 100 else body

            # Skicka e-postinformationen till Discord
            await send_email_to_discord(subject, from_, preview)

    except Exception as e:
        print(f"Error fetching emails: {e}")
    finally:
        mail.logout()  # Logga ut från IMAP-servern när allt är klart

# Funktion för att skicka e-postinformation till Discord
async def send_email_to_discord(subject, from_, preview):
    channel = bot.get_channel(1274024103350894622)  # Sätt din Discord-kanal ID här
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
    mail = connect_to_imap()  # Anslut till IMAP-servern
    asyncio.run(fetch_unseen_emails(mail))  # Hämta och skicka e-postmeddelanden
    await bot.close()  # Stäng boten när allt är klart

bot.run(DISCORD_BOT_TOKEN)

