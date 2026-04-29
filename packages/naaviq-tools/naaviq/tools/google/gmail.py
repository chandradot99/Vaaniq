"""Gmail tools.

Tools:
    gmail_send_email — send an email via Gmail
"""
import asyncio
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from googleapiclient.discovery import build
from naaviq.tools.base import BaseTool
from naaviq.tools.google.auth import build_google_credentials


def _build_service(org_keys: dict):
    creds = build_google_credentials(org_keys)
    return build("gmail", "v1", credentials=creds)


class GmailSendEmail(BaseTool):
    name = "gmail_send_email"
    description = "Send an email via Gmail."
    required_integration = "google"
    input_schema = {
        "type": "object",
        "properties": {
            "to": {
                "type": "string",
                "description": "Recipient email address.",
            },
            "subject": {
                "type": "string",
                "description": "Email subject line.",
            },
            "body": {
                "type": "string",
                "description": "Email body (plain text).",
            },
            "cc": {
                "type": "string",
                "description": "Optional CC email address.",
            },
        },
        "required": ["to", "subject", "body"],
    }

    async def run(self, input: dict, org_keys: dict) -> dict:
        to = input["to"]
        subject = input["subject"]
        body = input["body"]
        cc = input.get("cc")

        if cc:
            msg = MIMEMultipart()
            msg["to"] = to
            msg["cc"] = cc
            msg["subject"] = subject
            msg.attach(MIMEText(body, "plain"))
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        else:
            mime = MIMEText(body, "plain")
            mime["to"] = to
            mime["subject"] = subject
            raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()

        def _send():
            service = _build_service(org_keys)
            return service.users().messages().send(
                userId="me",
                body={"raw": raw},
            ).execute()

        result = await asyncio.to_thread(_send)

        return {
            "message_id": result.get("id"),
            "thread_id": result.get("threadId"),
            "status": "sent",
        }
