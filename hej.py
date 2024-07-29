import asyncio
import httpx
from bs4 import BeautifulSoup
import re
import tkinter as tk
from tkinter import scrolledtext, messagebox, Toplevel
from asyncio import Semaphore
import random
import threading
import time

class EmailScraperApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Email Scraper")
        self.links = []
        self.emails_with_websites = set()
        self.emails_without_websites = set()
        self.current_page = 1
        self.total_pages = 0

        self.semaphore = Semaphore(10)
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0'
        ]

        # Set up the GUI
        self.frame = tk.Frame(root)
        self.frame.pack(pady=20, padx=20)

        self.label = tk.Label(self.frame, text="Enter search term:")
        self.label.grid(row=0, column=0, padx=5, pady=5)

        self.entry = tk.Entry(self.frame, width=40)
        self.entry.grid(row=0, column=1, padx=5, pady=5)

        self.button = tk.Button(self.frame, text="Run Scraper", command=self.start_scraper)
        self.button.grid(row=1, column=0, columnspan=2, padx=5, pady=5)

        self.label_with_websites = tk.Label(self.frame, text="Emails with Websites:")
        self.label_with_websites.grid(row=2, column=0, columnspan=2, pady=10)

        self.text_with_websites = scrolledtext.ScrolledText(self.frame, width=80, height=10)
        self.text_with_websites.grid(row=3, column=0, columnspan=2, padx=5, pady=5)

        self.label_without_websites = tk.Label(self.frame, text="Emails without Websites:")
        self.label_without_websites.grid(row=4, column=0, columnspan=2, pady=10)

        self.text_without_websites = scrolledtext.ScrolledText(self.frame, width=80, height=10)
        self.text_without_websites.grid(row=5, column=0, columnspan=2, padx=5, pady=5)

        self.update_interval = 1000  # Update interval in milliseconds

    def start_scraper(self):
        # Open a new window to show loading status
        self.loading_window = Toplevel(self.root)
        self.loading_window.title("Loading")
        self.loading_label = tk.Label(self.loading_window, text="Scraping in progress. Please wait...")
        self.loading_label.pack(padx=20, pady=20)

        # Run the scraper in a separate thread
        threading.Thread(target=self.run_scraper, daemon=True).start()

    def run_scraper(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._run_scraper())

    async def fetch(self, url, client):
        headers = {
            'User-Agent': random.choice(self.user_agents)
        }
        async with self.semaphore:
            response = await client.get(url, headers=headers)
        response.raise_for_status()
        await asyncio.sleep(random.uniform(1, 3))  # Random delay between requests
        return response

    async def scrape_hittase_search(self, search_term: str, page: int, client: httpx.AsyncClient):
        main_url = f"https://www.hitta.se/sök?vad={search_term}&typ=ftg&sida={page}&riks=1"
        try:
            response = await self.fetch(main_url, client)
        except httpx.HTTPStatusError as e:
            print(f"Failed to fetch page {page}: {e}")
            return False

        soup = BeautifulSoup(response.text, "html.parser")

        for link_box in soup.find_all("a", attrs={"data-test": "search-list-link"}):
            link = "https://www.hitta.se" + link_box.get("href")
            self.links.append(link)

        next_page_link = soup.find("a", attrs={"data-test": "next"})
        return bool(next_page_link)

    async def scrape_emails_and_websites(self, client: httpx.AsyncClient):
        for link in self.links:
            emails, has_website = await self.process_link(link, client)
            if has_website:
                self.emails_with_websites.update(emails)
            else:
                self.emails_without_websites.update(emails)
            # Schedule a GUI update after processing each link
            self.root.after(0, self.update_gui)
            await asyncio.sleep(0)  # Allow other tasks to run

    async def process_link(self, link: str, client: httpx.AsyncClient):
        try:
            response = await self.fetch(link, client)
        except httpx.HTTPStatusError as e:
            print(f"Failed to fetch link {link}: {e}")
            return [], False

        soup = BeautifulSoup(response.text, "html.parser")

        company_name_tag = soup.find("h3", class_="style_title__2C92s")
        emails = []

        if company_name_tag:
            email_links = soup.find_all("a", attrs={"data-track": re.compile("e-mail")})
            if not email_links:
                email_links = soup.find_all("a", attrs={"href": re.compile("mailto:")})

            for email_link in email_links:
                email = email_link.get("data-census-details") or email_link.get("href")
                if email and "mailto:" in email:
                    email = email.replace("mailto:", "")
                if email:
                    emails.append(email)

            website_tag = soup.find("a", attrs={"data-track": re.compile("homepage-detail|directlink_web_page")})
            has_website = bool(website_tag)
            return emails, has_website

        return [], False

    def update_gui(self):
        # Update the GUI elements with the current results
        self.text_with_websites.delete('1.0', tk.END)
        self.text_without_websites.delete('1.0', tk.END)

        if self.emails_with_websites:
            self.text_with_websites.insert(tk.END, "\n".join(sorted(self.emails_with_websites)))
        else:
            self.text_with_websites.insert(tk.END, "No emails found with websites.")

        if self.emails_without_websites:
            self.text_without_websites.insert(tk.END, "\n".join(sorted(self.emails_without_websites)))
        else:
            self.text_without_websites.insert(tk.END, "No emails found without websites.")

    async def _run_scraper(self):
        search_term = self.entry.get()
        if not search_term:
            messagebox.showwarning("Input Error", "Please enter a search term.")
            self.loading_window.destroy()
            return

        self.links = []
        self.emails_with_websites = set()
        self.emails_without_websites = set()
        self.current_page = 1
        self.total_pages = 0

        async with httpx.AsyncClient() as client:
            while True:
                has_next_page = await self.scrape_hittase_search(search_term, self.current_page, client)
                await self.scrape_emails_and_websites(client)
                self.current_page += 1
                self.total_pages += 1

                if not has_next_page:
                    break

        self.update_gui()
        self.loading_window.destroy()
        messagebox.showinfo("Scraper", f"Scraping completed. Total pages processed: {self.total_pages}")

# Initialize the GUI
root = tk.Tk()
app = EmailScraperApp(root)
root.mainloop()
