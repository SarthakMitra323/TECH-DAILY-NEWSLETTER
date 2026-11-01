import feedparser
import logging
import os
import requests


REQUEST_TIMEOUT = float(os.getenv("NEWS_REQUEST_TIMEOUT", "15"))
logger = logging.getLogger(__name__)


def fetch_news(urls, limit=5):
    all_articles = []

    for url in urls:
        try:
            response = requests.get(
                url,
                timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": "TechDailyNewsletter/1.0"},
            )
            response.raise_for_status()
            feed = feedparser.parse(response.content)

            if feed.bozo and not feed.entries:
                print(f"Could not parse feed: {url}")
                continue

            source = feed.feed.get("title", "Unknown Source")

            for article in feed.entries[:limit]:
                all_articles.append({
                    "title": article.get("title", "Untitled"),
                    "link": article.get("link", ""),
                    "summary": article.get("summary", ""),
                    "source": source,
                    "published": article.get("published", ""),
                    "published_parsed": article.get("published_parsed"),
                })

            print(f"Fetched {min(len(feed.entries), limit)} articles from {source}")

        except requests.RequestException:
            logger.exception("Error fetching configured news feed")
            continue

    return all_articles



if __name__ == "__main__":

    RSS_FEEDS = [
        "https://feeds.arstechnica.com/arstechnica/index",
        "https://feeds.bbci.co.uk/news/technology/rss.xml",
        "https://www.theverge.com/rss/index.xml",
        "https://www.wired.com/feed/rss",
        "https://techcrunch.com/feed/",
    ]

    fetch_news(RSS_FEEDS, limit=5)
