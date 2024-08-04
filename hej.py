import asyncio
import httpx
from bs4 import BeautifulSoup
import re
import random
import json
from asyncio import Semaphore
from typing import List, Tuple, Set, Dict

class EmailScraperApp:
    def __init__(self):
        self.links: List[str] = []
        self.emails_with_websites: Set[Tuple[str, str]] = set()  # Tuple of (email, company_name)
        self.emails_without_websites: Set[Tuple[str, str]] = set()  # Tuple of (email, company_name)
        self.current_page: int = 1
        self.total_pages: int = 0
        self.total_results: int = 0
        self.stop_scraper_flag: bool = False
        self.semaphore: Semaphore = Semaphore(10)
        self.user_agents: List[str] = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0'
        ]
        self.server_url = "https://truevision.se/save_data.php"  # Update with your actual URL

    async def verify_key(self) -> bool:
        url = "https://truevision.se/hej.txt"
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url)
                response.raise_for_status()
                key = response.text.strip()
                print(f"Fetched key: {key}")
                return key == "faca2f2d03dbdd580aaaf38c3f53661acc70555f4ff22bd1098a45a530865e0e"
            except httpx.HTTPError as e:
                print(f"Error fetching key: {e}")
                return False

    async def key_check_loop(self):
        while not self.stop_scraper_flag:
            valid = await self.verify_key()
            if not valid:
                print("Nyckeln är ogiltig eller inte hittad. Applikationen avslutas.")
                self.stop_scraper_flag = True
            await asyncio.sleep(60)

    async def fetch(self, url: str, client: httpx.AsyncClient) -> httpx.Response:
        headers = {'User-Agent': random.choice(self.user_agents)}
        retries = 0
        max_retries = 5

        while retries < max_retries and not self.stop_scraper_flag:
            try:
                async with self.semaphore:
                    response = await client.get(url, headers=headers, timeout=30.0)
                response.raise_for_status()
                await asyncio.sleep(random.uniform(1, 3))
                return response
            except (httpx.ReadTimeout, httpx.HTTPStatusError) as e:
                print(f"Error fetching URL {url}: {e}")
                retries += 1
                await asyncio.sleep(10)

        print(f"Failed to fetch URL: {url} after {max_retries} retries.")
        return None

    async def scrape_hittase_search(self, search_term: str, page: int, client: httpx.AsyncClient) -> bool:
        main_url = f"https://www.hitta.se/sök?vad={search_term}&typ=ftg&sida={page}&riks=1"
        print(f"Fetching search results page: {main_url}")
        response = await self.fetch(main_url, client)
        if response is None:
            return False

        soup = BeautifulSoup(response.text, "html.parser")
        try:
            results_text = soup.find("span", class_="style_tabNumbers__VbAE7").get_text()
            self.total_results = int(results_text.replace(',', ''))
            self.total_pages = (self.total_results + 24) // 25
            print(f"Total results: {self.total_results}, Total pages: {self.total_pages}")
        except AttributeError:
            self.total_results = 0
            self.total_pages = 0
            print("Could not find total results")

        for link_box in soup.find_all("a", attrs={"data-test": "search-list-link"}):
            link = "https://www.hitta.se" + link_box.get("href")
            self.links.append(link)
            print(f"Found link: {link}")

        next_page_link = soup.find("a", attrs={"data-test": "next"})
        return bool(next_page_link)

    async def scrape_emails_and_websites(self, client: httpx.AsyncClient, search_term: str):
        print(f"Scraping emails and websites from {len(self.links)} links.")
        tasks = [self.process_link(link, client, search_term) for link in self.links]
        await asyncio.gather(*tasks)
        self.links.clear()

    async def process_link(self, link: str, client: httpx.AsyncClient, search_term: str):
        print(f"Processing link: {link}")
        response = await self.fetch(link, client)
        if response is None:
            return

        soup = BeautifulSoup(response.text, "html.parser")
        company_name_tag = soup.find("h3", class_="style_title__2C92s")
        company_name = company_name_tag.get_text(strip=True) if company_name_tag else "Unknown"
        emails = []

        if company_name_tag:
            email_links = soup.find_all("a", attrs={"data-track": re.compile("e-mail")}) or \
                          soup.find_all("a", attrs={"href": re.compile("mailto:")})

            for email_link in email_links:
                email = email_link.get("data-census-details") or email_link.get("href")
                if email and "mailto:" in email:
                    email = email.replace("mailto:", "")
                if email:
                    emails.append(email)

            website_tag = soup.find("a", attrs={"data-track": re.compile("homepage-detail|directlink_web_page")})
            has_website = bool(website_tag)
            print(f"Found emails: {emails}, Has website: {has_website}, Company: {company_name}")
            
            for email in emails:
                if has_website:
                    self.emails_with_websites.add((email, company_name))
                else:
                    self.emails_without_websites.add((email, company_name))
            
            await self.save_to_json(search_term)

    async def main_loop(self, search_term: str):
        async with httpx.AsyncClient(follow_redirects=True) as client:  # Ensure redirects are followed
            while self.current_page <= self.total_pages or self.total_pages == 0:
                print(f"Scraping page {self.current_page} of {self.total_pages}")
                has_next_page = await self.scrape_hittase_search(search_term, self.current_page, client)
                await self.scrape_emails_and_websites(client, search_term)
                if not has_next_page:
                    print("No more pages to scrape.")
                    break
                self.current_page += 1

            self.display_results()

    async def run(self, search_term: str):
        if not await self.verify_key():
            print("Nyckeln är ogiltig eller inte hittad. Applikationen avslutas.")
            return

        await asyncio.gather(
            self.key_check_loop(),
            self.main_loop(search_term)
        )

    def display_results(self):
        print("\nEmails with Websites:")
        if self.emails_with_websites:
            for email, company_name in sorted(self.emails_with_websites):
                print(f"{company_name}: {email}")

        print("\nEmails without Websites:")
        if self.emails_without_websites:
            for email, company_name in sorted(self.emails_without_websites):
                print(f"{company_name}: {email}")

    async def save_to_json(self, search_term: str):
        data = {
            search_term: {
                "with_website": [
                    {"email": email, "name": name} for email, name in self.emails_with_websites
                ],
                "without_website": [
                    {"email": email, "name": name} for email, name in self.emails_without_websites
                ]
            }
        }

        async with httpx.AsyncClient(follow_redirects=True) as client:  # Ensure redirects are followed
            try:
                response = await client.post(
                    self.server_url, 
                    json=data,
                    headers={'Content-Type': 'application/json; charset=utf-8'}
                )
                if response.status_code == 200:
                    print("Data successfully saved to the server.")
                else:
                    print(f"Failed to save data to the server. Status code: {response.status_code}")
            except Exception as e:
                print(f"An error occurred while saving data to the server: {e}")

# Example usage
if __name__ == "__main__":
    scraper = EmailScraperApp()
    search_term = input("Enter search term: ").replace(' ', '%20')
    asyncio.run(scraper.run(search_term))
