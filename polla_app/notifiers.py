"""Notification utilities for the polla pipeline."""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

LOGGER = logging.getLogger(__name__)


def notify_slack(summary: dict[str, Any]) -> None:
    """Send a summary of the run to Slack if a webhook is configured."""
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        return

    decision = summary.get("decision", {})
    status = decision.get("status", "unknown")
    icon = "✅"
    title = "*Polla Scraper Run Summary*"

    if status == "quarantine":
        icon = "⚠️"
        title = "*Polla Scraper DISCREPANCY ALERT*"

    # Only notify if we published something, if it's a failure (quarantine/fail), or prize change
    if status == "skip" and not summary.get("prizes_changed"):
        LOGGER.debug("Skipping Slack notification for unchanged run")
        return

    payload = {
        "text": (
            f"{icon} {title}\n"
            f"• *Status:* `{status.upper()}`\n"
            f"• *Decision:* {summary.get('publish_reason', 'N/A')}\n"
            f"• *Updated Rows:* {summary.get('updated_rows', 0)}\n"
            f"• *Discrepancies:* {decision.get('mismatched_categories', 0)}\n"
            f"• *Run ID:* `{summary.get('run_id', 'n/a')}`\n"
        )
    }

    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        LOGGER.info("Slack notification sent successfully")
    except Exception as exc:
        LOGGER.warning("Failed to send Slack notification: %s", exc)


def notify_quarantine(summary: dict[str, Any], mismatches: list[dict[str, Any]]) -> None:
    """Send a detailed discrepancy report to Slack using Blocks."""
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        return

    decision = summary.get("decision", {})
    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🚨 Polla Scraper Quarantine Alert",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Status:* `{decision.get('status', 'QUARANTINE').upper()}`\n"
                    f"*Reason:* {summary.get('publish_reason', 'N/A')}\n"
                    f"*Run ID:* `{summary.get('run_id', 'n/a')}`"
                ),
            },
        },
    ]

    if mismatches:
        mismatch_lines = []
        for m in mismatches[:15]:  # Slack has block limits
            cat = m.get("categoria", "Unknown")
            # consensus is a dict like {"100": ["source1"]}
            consensus_data = m.get("consensus", {})
            val = next(iter(consensus_data.keys())) if consensus_data else "N/A"
            missing = m.get("missing_sources", [])
            missing_str = f" (Missing: {', '.join(missing)})" if missing else ""
            mismatch_lines.append(f"• *{cat}*: `{val}`{missing_str}")

        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Discrepancies Detail:*\n" + "\n".join(mismatch_lines),
                },
            }
        )

    try:
        response = requests.post(webhook_url, json={"blocks": blocks}, timeout=10)
        response.raise_for_status()
        LOGGER.info("Slack quarantine notification sent successfully")
    except Exception as exc:
        LOGGER.warning("Failed to send Slack quarantine notification: %s", exc)
