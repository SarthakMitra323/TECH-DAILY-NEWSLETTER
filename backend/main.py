import dotenv
import os
import sys

dotenv.load_dotenv()

recipient = os.getenv("NEWS_EMAIL_RECIPIENT")

RSS_FEEDS = [
    "https://feeds.arstechnica.com/arstechnica/index",
    "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "https://www.theverge.com/rss/index.xml",
    "https://www.wired.com/feed/rss",
    "https://techcrunch.com/feed/",
]

def send_test_email():
    from news_fetch import fetch_news
    from send_email import send_email

    articles = fetch_news(RSS_FEEDS, limit=5)
    send_email(articles, recipient)


if __name__ == "__main__":
    if "--test-email" in sys.argv:
        send_test_email()
    else:
        from scheduler import run_scheduler

        run_scheduler()