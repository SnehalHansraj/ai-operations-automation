"""
Notification service — sends the agent's outcome to a human channel.

If SLACK_WEBHOOK_URL is set in .env, a real Slack message is posted.
Otherwise it just logs, so the project still runs end-to-end with zero
external accounts configured.
"""
import os
import logging

import httpx

logger = logging.getLogger("notifications")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")


def notify(case_id: str, issue_type: str, action: str, response_text: str) -> str:
    message = (
        f":package: *Case {case_id}*\n"
        f"Type: `{issue_type}` | Action: `{action}`\n"
        f"Response sent: {response_text}"
    )

    if SLACK_WEBHOOK_URL:
        try:
            httpx.post(SLACK_WEBHOOK_URL, json={"text": message}, timeout=5)
            return "slack"
        except Exception as e:
            logger.warning("Slack notify failed, falling back to log: %s", e)

    logger.info("NOTIFY (%s): %s", case_id, message.replace("\n", " | "))
    return "log"
