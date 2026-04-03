"""Google Sheets tools.

Tools:
    google_sheets_read_range  — read a range of cells from a spreadsheet
    google_sheets_append_row  — append a row of values to a sheet
"""
import asyncio
from googleapiclient.discovery import build

from vaaniq.tools.base import BaseTool
from vaaniq.tools.google.auth import build_google_credentials


def _build_service(org_keys: dict):
    creds = build_google_credentials(org_keys)
    return build("sheets", "v4", credentials=creds)


class GoogleSheetsReadRange(BaseTool):
    name = "google_sheets_read_range"
    description = "Read a range of cells from a Google Sheets spreadsheet."
    required_integration = "google"
    input_schema = {
        "type": "object",
        "properties": {
            "spreadsheet_id": {
                "type": "string",
                "description": "The spreadsheet ID from the Google Sheets URL.",
            },
            "range": {
                "type": "string",
                "description": "A1 notation range to read, e.g. 'Sheet1!A1:D10' or 'A1:B5'.",
            },
        },
        "required": ["spreadsheet_id", "range"],
    }

    async def run(self, input: dict, org_keys: dict) -> dict:
        spreadsheet_id = input["spreadsheet_id"]
        range_ = input["range"]

        def _fetch():
            service = _build_service(org_keys)
            result = (
                service.spreadsheets()
                .values()
                .get(spreadsheetId=spreadsheet_id, range=range_)
                .execute()
            )
            values = result.get("values", [])
            return values

        rows = await asyncio.to_thread(_fetch)
        return {"rows": rows, "row_count": len(rows)}


class GoogleSheetsAppendRow(BaseTool):
    name = "google_sheets_append_row"
    description = "Append a row of values to a Google Sheets spreadsheet."
    required_integration = "google"
    input_schema = {
        "type": "object",
        "properties": {
            "spreadsheet_id": {
                "type": "string",
                "description": "The spreadsheet ID from the Google Sheets URL.",
            },
            "range": {
                "type": "string",
                "description": "Sheet name or range to append to, e.g. 'Sheet1' or 'Sheet1!A1'.",
            },
            "values": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of cell values for the new row, e.g. ['Alice', '30', 'alice@example.com'].",
            },
        },
        "required": ["spreadsheet_id", "range", "values"],
    }

    async def run(self, input: dict, org_keys: dict) -> dict:
        spreadsheet_id = input["spreadsheet_id"]
        range_ = input["range"]
        values = input["values"]

        def _append():
            service = _build_service(org_keys)
            result = (
                service.spreadsheets()
                .values()
                .append(
                    spreadsheetId=spreadsheet_id,
                    range=range_,
                    valueInputOption="USER_ENTERED",
                    insertDataOption="INSERT_ROWS",
                    body={"values": [values]},
                )
                .execute()
            )
            updates = result.get("updates", {})
            return {
                "updated_range": updates.get("updatedRange"),
                "updated_rows": updates.get("updatedRows", 0),
                "status": "appended",
            }

        return await asyncio.to_thread(_append)
