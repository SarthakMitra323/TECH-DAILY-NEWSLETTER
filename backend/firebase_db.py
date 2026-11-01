import json
import os
from datetime import datetime, timezone

import firebase_admin
from dotenv import load_dotenv
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud.firestore_v1.transaction import transactional

load_dotenv()

COLLECTION_NAME = "subscribers"


def get_db():

    if firebase_admin._apps:
        return firestore.client()

    service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")

    if not service_account_json:
        raise RuntimeError(
            "FIREBASE_SERVICE_ACCOUNT_JSON is missing from .env"
        )

    try:
        service_account_info = json.loads(service_account_json)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            "Firebase service-account credentials are invalid JSON."
        ) from error

    credential = credentials.Certificate(service_account_info)

    firebase_admin.initialize_app(credential)

    return firestore.client()


def get_subscribers():

    db = get_db()

    subscribers = db.collection(COLLECTION_NAME).where(
        filter=FieldFilter("active", "==", True)
    ).stream()

    result = []
    for document in subscribers:
        result.append({"id": document.id, **(document.to_dict() or {})})
    return result


def get_subscriber(email):

    db = get_db()

    document = (
        db.collection(COLLECTION_NAME)
        .document(email.lower())
        .get()
    )

    if not document.exists:
        return None

    return {"id": document.id, **(document.to_dict() or {})}


def update_subscriber(email, updates):
    """Update a subscriber's preferences or delivery metadata."""

    db = get_db()

    updates["updated_at"] = datetime.now(timezone.utc)

    (
        db.collection(COLLECTION_NAME)
        .document(email.lower())
        .update(updates)
    )


def claim_delivery(email, scheduled_slot, retry_after_seconds=300):

    db = get_db()
    subscriber_ref = (
        db.collection(COLLECTION_NAME)
        .document(email.lower())
    )

    transaction = db.transaction()

    @transactional
    def claim(transaction):
        snapshot = subscriber_ref.get(transaction=transaction)

        if not snapshot.exists:
            return False

        data = snapshot.to_dict() or {}

        if not data.get("active", False):
            return False

        if data.get("last_sent_slot") == scheduled_slot:
            return False

        if data.get("last_attempt_slot") == scheduled_slot:
            last_attempt_at = data.get("last_attempt_at")
            if last_attempt_at is not None:
                elapsed = (
                    datetime.now(timezone.utc) - last_attempt_at
                ).total_seconds()
                if elapsed < retry_after_seconds:
                    return False

        transaction.update(
            subscriber_ref,
            {
                "last_attempt_slot": scheduled_slot,
                "last_attempt_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            },
        )

        return True

    return claim(transaction)


def record_delivery(email, scheduled_slot, success, error=None):

    db = get_db()

    subscriber_ref = (
        db.collection(COLLECTION_NAME)
        .document(email.lower())
    )

    now = datetime.now(timezone.utc)

    updates = {
        "last_delivery_attempt_at": now,
        "last_delivery_success": success,
        "last_delivery_error": error if not success else None,
        "updated_at": now,
    }

    if success:
        updates["last_sent_slot"] = scheduled_slot
        updates["last_sent_at"] = now

    subscriber_ref.update(updates)