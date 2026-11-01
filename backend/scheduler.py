import os
import logging
from datetime import datetime, timezone
from threading import Event
from zoneinfo import ZoneInfoNotFoundError

from dotenv import load_dotenv

from firebase_db import (
    get_subscribers,
    claim_delivery,
    record_delivery,
)

from news_fetch import fetch_news
from send_email import send_email
from timezone_utils import get_timezone

load_dotenv()

# Configure logging.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)

# Comma-separated RSS feed URLs in .env.
RSS_FEEDS = [
    url.strip()
    for url in os.getenv("RSS_FEEDS", "").split(",")
    if url.strip()
]

# Number of articles to fetch from each RSS feed.
ARTICLES_PER_FEED = int(os.getenv("ARTICLES_PER_FEED", "5"))

# How frequently the scheduler checks for subscribers who are due.
CHECK_INTERVAL = int(os.getenv("SCHEDULER_CHECK_INTERVAL", "30"))
DUE_WINDOW_MINUTES = int(os.getenv("SCHEDULER_DUE_WINDOW_MINUTES", "10"))
DELIVERY_RETRY_SECONDS = int(os.getenv("DELIVERY_RETRY_SECONDS", "300"))

WEEKDAYS = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


def get_due_slot(subscriber, now_utc=None):

    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    elif now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    try:
        timezone_name = subscriber.get(
            "timezone", "Asia/Kolkata"
        )

        local_now = now_utc.astimezone(
            get_timezone(timezone_name)
        )

    except (ZoneInfoNotFoundError, ValueError, TypeError):
        logger.warning(
            "Invalid timezone for subscriber %s",
            subscriber.get("email", "unknown"),
        )
        return None

    preferred_time = subscriber.get("time_of_day")

    if not isinstance(preferred_time, str):
        return None

    try:
        preferred_hour, preferred_minute = map(
            int, preferred_time.split(":")
        )
        if (
            len(preferred_time) != 5
            or preferred_time[2] != ":"
            or not 0 <= preferred_hour <= 23
            or not 0 <= preferred_minute <= 59
        ):
            return None
        scheduled_time = local_now.replace(
            hour=preferred_hour,
            minute=preferred_minute,
            second=0,
            microsecond=0,
        )
    except (TypeError, ValueError):
        return None

    frequency = subscriber.get("frequency")

    if frequency == "daily":
        scheduled_slot = (
            f"daily:{local_now.strftime('%Y-%m-%d')}:"
            f"{preferred_time}"
        )

    elif frequency == "weekly":
        preferred_day = subscriber.get("day_of_week", "monday")

        if not isinstance(preferred_day, str):
            return None

        if local_now.strftime("%A").lower() != preferred_day.lower():
            return None

        scheduled_slot = (
            f"weekly:{local_now.strftime('%Y-%m-%d')}:"
            f"{preferred_time}"
        )

    else:
        logger.warning(
            "Unknown frequency for subscriber %s",
            subscriber.get("email", "unknown"),
        )
        return None

    elapsed_minutes = (local_now - scheduled_time).total_seconds() / 60
    if elapsed_minutes < 0:
        return None

    if elapsed_minutes <= DUE_WINDOW_MINUTES:
        return scheduled_slot

    if (
        subscriber.get("last_attempt_slot") != scheduled_slot
        or subscriber.get("last_delivery_success") is not False
    ):
        return None

    last_attempt_at = subscriber.get("last_attempt_at")
    if not isinstance(last_attempt_at, datetime):
        return None
    if last_attempt_at.tzinfo is None:
        last_attempt_at = last_attempt_at.replace(tzinfo=timezone.utc)

    retry_elapsed = (
        datetime.now(timezone.utc) - last_attempt_at
    ).total_seconds()
    if retry_elapsed < DELIVERY_RETRY_SECONDS:
        return None

    return scheduled_slot


def deliver_newsletter(subscriber, articles, scheduled_slot):
    """Send one newsletter and record the delivery result."""

    email = subscriber.get("email")

    if not email:
        logger.warning(
            "Skipping subscriber without an email address."
        )
        return

    # Atomically claim this delivery slot before sending.
    try:
        claimed = claim_delivery(
            email,
            scheduled_slot,
            retry_after_seconds=DELIVERY_RETRY_SECONDS,
        )

    except Exception:
        logger.exception(
            "Could not claim delivery slot for %s",
            email,
        )
        return

    if not claimed:
        logger.info("Skipping duplicate or inactive subscription")
        return

    try:
        send_email(
            articles=articles,
            recipient=email,
            timezone_name=subscriber.get("timezone", "Asia/Kolkata"),
        )

        record_delivery(
            email=email,
            scheduled_slot=scheduled_slot,
            success=True,
        )

        logger.info("Newsletter delivered")

    except Exception as error:
        logger.exception("Newsletter delivery failed")

        try:
            record_delivery(
                email=email,
                scheduled_slot=scheduled_slot,
                success=False,
                error=str(error)[:500],
            )

        except Exception:
            logger.exception(
                "Could not record delivery failure for %s",
                email,
            )


def run_scheduler_once():
    """Perform one check of all active subscriptions."""

    logger.info("Checking newsletter subscriptions...")

    try:
        subscribers = get_subscribers()

    except Exception:
        logger.exception(
            "Could not retrieve subscribers from Firebase."
        )
        return

    if not subscribers:
        logger.info("No active subscribers found.")
        return

    now_utc = datetime.now(timezone.utc)

    due_subscribers = []

    for subscriber in subscribers:
        scheduled_slot = get_due_slot(
            subscriber,
            now_utc,
        )

        if scheduled_slot:
            due_subscribers.append(
                (subscriber, scheduled_slot)
            )

    if not due_subscribers:
        logger.info("No newsletters are due right now.")
        return

    logger.info(
        "%d newsletter(s) are due.",
        len(due_subscribers),
    )

    if not RSS_FEEDS:
        logger.error(
            "No RSS_FEEDS configured. Add RSS feed URLs to .env."
        )
        return

    try:
        articles = fetch_news(
            RSS_FEEDS,
            limit=ARTICLES_PER_FEED,
        )

    except Exception:
        logger.exception("Failed to fetch technology news.")
        return

    if not articles:
        logger.warning(
            "No articles fetched. Newsletters will not be sent."
        )
        return

    logger.info(
        "Fetched %d articles for the newsletter.",
        len(articles),
    )

    for subscriber, scheduled_slot in due_subscribers:
        deliver_newsletter(
            subscriber=subscriber,
            articles=articles,
            scheduled_slot=scheduled_slot,
        )


def run_scheduler(stop_event=None):
    """Run the scheduler until the supplied event is set."""

    logger.info("Technology newsletter scheduler started.")

    if stop_event is None:
        stop_event = Event()

    while not stop_event.is_set():
        try:
            run_scheduler_once()

        except KeyboardInterrupt:
            logger.info("Scheduler stopped.")
            break

        except Exception:
            logger.exception(
                "Unexpected scheduler error."
            )

        stop_event.wait(CHECK_INTERVAL)

    logger.info("Technology newsletter scheduler stopped.")


def main():
    run_scheduler()


if __name__ == "__main__":
    main()