import asyncio
import httpx
from bs4 import BeautifulSoup
import re
import random
from asyncio import Semaphore

class EmailScraperApp:
    def __init__(self):
        self.links = []
        self.emails_with_websites = set()
        self.emails_without_websites = set()
        self.current_page = 1
        self.total_pages = 0
        self.total_results = 0
        self.stop_scraper_flag = False
        self.semaphore = Semaphore(10)
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0'
        ]

    async def fetch(self, url, client):
        headers = {
            'User-Agent': random.choice(self.user_agents)
        }
        retries = 0
        max_retries = 5

        while retries < max_retries:
            if self.stop_scraper_flag:
                print("Stop scraper flag set. Exiting fetch.")
                return None
            try:
                async with self.semaphore:
                    print(f"Fetching URL: {url}")
                    response = await client.get(url, headers=headers, timeout=30.0)
                response.raise_for_status()
                await asyncio.sleep(random.uniform(1, 3))
                print(f"Successfully fetched URL: {url}")
                return response
            except (httpx.ReadTimeout, httpx.HTTPStatusError) as e:
                retries += 1
                print(f"Error occurred for URL: {url}. Retrying in 10 seconds... (Attempt {retries})")
                await asyncio.sleep(10)

        print(f"Failed to fetch URL: {url} after {max_retries} retries.")
        return None

    async def scrape_hittase_search(self, search_term: str, page: int, client: httpx.AsyncClient):
        main_url = f"https://www.hitta.se/sök?vad={search_term}&typ=ftg&sida={page}&riks=1"
        print(f"Scraping search results for URL: {main_url}")
        try:
            response = await self.fetch(main_url, client)
            if response is None:
                return False
        except httpx.HTTPStatusError as e:
            print(f"Failed to fetch page {page}: {e}")
            return False

        soup = BeautifulSoup(response.text, "html.parser")

        try:
            results_text = soup.find("span", class_="style_tabNumbers__VbAE7").get_text()
            self.total_results = int(results_text.replace(',', ''))
            self.total_pages = (self.total_results + 24) // 25
        except AttributeError as e:
            print(f"Failed to extract total results: {e}")
            self.total_results = 0
            self.total_pages = 0

        for link_box in soup.find_all("a", attrs={"data-test": "search-list-link"}):
            link = "https://www.hitta.se" + link_box.get("href")
            self.links.append(link)

        next_page_link = soup.find("a", attrs={"data-test": "next"})
        has_next_page = bool(next_page_link)
        print(f"Next page link found: {has_next_page}")
        return has_next_page

    async def scrape_emails_and_websites(self, client: httpx.AsyncClient):
        print(f"Processing {len(self.links)} links.")
        for i, link in enumerate(self.links):
            if self.stop_scraper_flag:
                print("Stop scraper flag set. Exiting scrape_emails_and_websites.")
                return
            emails, has_website = await self.process_link(link, client)
            if has_website:
                self.emails_with_websites.update(emails)
            else:
                self.emails_without_websites.update(emails)
            print(f"Processing link: {i + 1}/{self.total_results} - {link}")
            await asyncio.sleep(0)

        self.links.clear()

    async def process_link(self, link: str, client: httpx.AsyncClient):
        print(f"Processing link: {link}")
        try:
            response = await self.fetch(link, client)
            if response is None:
                return [], False
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
            print(f"Found emails: {emails}, Has website: {has_website}")
            return emails, has_website

        return [], False

    async def run(self, search_term: str):
        async with httpx.AsyncClient() as client:
            while True:
                has_next_page = await self.scrape_hittase_search(search_term, self.current_page, client)
                if not has_next_page or self.current_page >= self.total_pages:
                    break
                self.current_page += 1

            await self.scrape_emails_and_websites(client)
            self.display_results()

    def display_results(self):
        print("\nEmails with Websites:")
        if self.emails_with_websites:
            print("\n".join(sorted(self.emails_with_websites)))
        print("\nEmails without Websites:")
        if self.emails_without_websites:
            print("\n".join(sorted(self.emails_without_websites)))


# Example usage
if __name__ == "__main__":
    scraper = EmailScraperApp()
    search_term = input("Enter search term: ").replace(' ', '%20')
    asyncio.run(scraper.run(search_term))
