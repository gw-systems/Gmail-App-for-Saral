"""
Background tasks for Gmail integration using django-q2
"""
import logging
from .utils.gmail_api import sync_all_emails

logger = logging.getLogger(__name__)

def sync_emails_task(max_inbox=100, max_sent=100):
    """
    Task to sync emails for all active accounts.
    To be called via async_task.
    """
    logger.info("Background sync task started.")
    try:
        results = sync_all_emails(max_inbox=max_inbox, max_sent=max_sent)
        logger.info(f"Background sync task completed. Synced {results.get('total', 0)} emails.")
        return results
    except Exception as e:
        logger.error(f"Background sync task failed: {e}")
        raise
