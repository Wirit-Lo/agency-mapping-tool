"""Service draft helpers for the add-service UI.

This module intentionally writes only to the central ServiceConfig workbook.
Applying the draft into the production Pay@Post source sheets should be a
separate explicit step after preview/review.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Optional

from pydantic import BaseModel

SERVICE_CONFIG_SPREADSHEET_ID = os.getenv(
    "SERVICE_CONFIG_SPREADSHEET_ID",
    "1pY-C4OJmTLj8j3tNSe5zGSSF7y1zqxz-rhN_axQlETs",
)

SHEET_HEADERS: dict[str, list[str]] = {
    "Service": ["SERVICE_ID", "SERVICE_NAME", "AGENT_CODE", "AGENT_NAME", "CATEGORY", "STATUS", "START_DATE", "FEE", "SERVICE_TYPE", "NOTES"],
    "Barcode": ["SERVICE_ID", "BASE_PREFIX", "SUFFIX", "SAMPLE_BARCODE", "IS_PRIMARY", "VALIDATE_TEXT"],
    "Fields": ["SERVICE_ID", "SEQ", "LB_NAME", "FD_NAME", "S_POS", "E_POS", "AGENCY_FIELD", "VISIBLE", "READONLY", "FIELD_TYPE"],
    "Validation": ["SERVICE_ID", "SEQ", "FD_NAME", "AGENCY_FIELD", "VALIDATE_TEXT"],
    "DefaultValue": ["SERVICE_ID", "LB_NAME", "DEFAULT_VALUE", "AGENCY_FIELD", "EDITABLE"],
    "Derived": ["SERVICE_ID", "ATTRIBUTE", "SOURCE_FIELD", "FORMULA", "SAME_ATTRIBUTE_SOURCE", "ENABLED"],
    "Receipt": ["SERVICE_ID", "PF_FMT_ID", "SEQ", "SECTION_ID", "LINE_NUMBER", "LINE_COND", "LINE_COL", "TEXT_COL1", "TEXT_COL2", "TEXT_COL3", "TEXT_COL4", "TEXT_COL5"],
    "TestCases": ["SERVICE_ID", "TEST_NAME", "BARCODE", "EXPECTED_AMOUNT", "EXPECTED_VAT", "EXPECTED_REFNO10", "EXPECTED_REFNO11", "EXPECTED_RESULT", "NOTES"],
}

TARGETS = [
    {"section": "Service", "file": "PayAtPost-StatSUM_Master_V1.2.xlsx", "sheet": "Main"},
    {"section": "Service", "file": "PayAtPost-PAP_ALL_ServiceID_V1.2-1.3.xlsx", "sheet": "Map Agency ID"},
    {"section": "Fields", "file": "PayAtPost-PAP_ALL_ServiceID_V1.2-1.3.xlsx", "sheet": "Fields"},
    {"section": "Barcode", "file": "PayAtPost-SpecBarcode_V1.5.xlsx", "sheet": "BOT-STD / NotBOT-STD / ScriptText"},
    {"section": "Validation", "file": "PayAtPost-ValidateScriptText.xlsx", "sheet": "Functions"},
    {"section": "DefaultValue", "file": "PayAtPost-DefaultValue_V1.0.xlsx", "sheet": "Default"},
    {"section": "Derived", "file": "AgencyDerivedDataRequirements.xlsx", "sheet": "DerivedData"},
    {"section": "Receipt", "file": "PayAtPost-ConfigReceipt_V1.0.xlsx", "sheet": "Receipt"},
    {"section": "Provider", "file": "AgencyServiceProviders.xlsx", "sheet": "ServiceProvider"},
]


class ServiceDraftRequest(BaseModel):
    draft: dict[str, Any]


class ServiceDraftResponse(BaseModel):
    service_id: str
    spreadsheet_id: Optional[str] = None
    saved_at: Optional[str] = None
    rows: dict[str, int]
    targets: list[dict[str, str]]
    warnings: list[str]


def _value(data: dict[str, Any], *path: str, default: str = "") -> str:
    cur: Any = data
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    if cur is None:
        return default
    return str(cur)


def _field_type(fd_name: str) -> str:
    if fd_name.startswith("D_DATE"):
        return "DateField"
    if fd_name.startswith("D_MONEY"):
        return "CurrencyField"
    if fd_name.startswith("D_INT"):
        return "NumberField"
    return "TextField"


def _field_label(fields: list[dict[str, Any]], agency_field: str, fallback: str = "") -> str:
    for field in fields:
        if str(field.get("agencyField", "")) == agency_field:
            return str(field.get("label", ""))
    return fallback


def _expected_map(lines: list[Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in lines:
        text = str(raw).strip()
        if not text or "=" not in text:
            continue
        key, value = text.split("=", 1)
        out[key.strip().upper()] = value.strip()
    return out


def _pf_fmt_id(service_id: str) -> str:
    if service_id.isdigit() and len(service_id) >= 3:
        return str(int(service_id[-3:]))
    return service_id


def build_rows(draft: dict[str, Any]) -> dict[str, list[list[Any]]]:
    service = draft.get("service", {}) if isinstance(draft.get("service"), dict) else {}
    barcode = draft.get("barcode", {}) if isinstance(draft.get("barcode"), dict) else {}
    fields = draft.get("fields", []) if isinstance(draft.get("fields"), list) else []
    defaults = draft.get("defaults", []) if isinstance(draft.get("defaults"), list) else []
    derived = draft.get("derived", []) if isinstance(draft.get("derived"), list) else []
    receipt_lines = draft.get("receiptLines", []) if isinstance(draft.get("receiptLines"), list) else []
    expected = _expected_map(draft.get("expectedOutput", []) if isinstance(draft.get("expectedOutput"), list) else [])

    service_id = str(service.get("serviceId", "")).strip()
    rows: dict[str, list[list[Any]]] = {name: [] for name in SHEET_HEADERS}

    rows["Service"].append([
        service_id,
        service.get("serviceName", ""),
        service.get("agentCode", ""),
        service.get("agentName", ""),
        service.get("category", ""),
        service.get("status", "Open"),
        service.get("startDate", ""),
        service.get("fee", ""),
        service.get("serviceType", "OFFLINE"),
        service.get("notes", ""),
    ])

    suffixes = barcode.get("suffixes", []) if isinstance(barcode.get("suffixes"), list) else []
    if not suffixes:
        suffixes = [""]
    for index, suffix in enumerate(suffixes):
        rows["Barcode"].append([
            service_id,
            barcode.get("basePrefix", ""),
            suffix,
            barcode.get("sampleBarcode", ""),
            "Y" if index == 0 else "N",
            barcode.get("validate", ""),
        ])

    for field in fields:
        fd_name = str(field.get("fdName", ""))
        rows["Fields"].append([
            service_id,
            field.get("seq", ""),
            field.get("label", ""),
            fd_name,
            field.get("sPos", ""),
            field.get("ePos", ""),
            field.get("agencyField", ""),
            field.get("visible", "1"),
            field.get("readonly", "1"),
            field.get("fieldType", "") or _field_type(fd_name),
        ])

    validation = draft.get("validation", {}) if isinstance(draft.get("validation"), dict) else {}
    if barcode.get("validate"):
        rows["Validation"].append([service_id, "100", "D_TEXT_01", "BRCDE", barcode.get("validate", "")])
    if validation.get("dueDate"):
        rows["Validation"].append([service_id, "101", "D_DATE_01", "", validation.get("dueDate", "")])
    if validation.get("amount"):
        rows["Validation"].append([service_id, "111", "D_MONEY_02", "AMT", validation.get("amount", "")])

    for item in defaults:
        attr = str(item.get("attribute", ""))
        rows["DefaultValue"].append([
            service_id,
            _field_label(fields, attr, attr),
            item.get("value", ""),
            attr,
            item.get("editable", "N"),
        ])

    for item in derived:
        attr = str(item.get("attribute", ""))
        formula = str(item.get("formula", "") or "")
        rows["Derived"].append([
            service_id,
            attr,
            item.get("sourceField", ""),
            formula,
            item.get("sameAttributeSource", "No Match"),
            "Y" if formula.strip() else "N",
        ])

    pf_fmt_id = _pf_fmt_id(service_id)
    for index, line in enumerate(receipt_lines, start=1):
        text = str(line)
        if not text.strip():
            continue
        rows["Receipt"].append([
            service_id,
            pf_fmt_id,
            9 + index,
            2,
            index,
            "NULL",
            1,
            text,
            "NULL",
            "NULL",
            "NULL",
            "NULL",
        ])

    rows["TestCases"].append([
        service_id,
        "default",
        barcode.get("sampleBarcode", ""),
        expected.get("AMOUNT", ""),
        expected.get("VAT", ""),
        expected.get("REFNO10", ""),
        expected.get("REFNO11", ""),
        expected.get("RESULT", ""),
        "",
    ])
    return rows


def validate_draft(draft: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    service_id = _value(draft, "service", "serviceId")
    if not service_id.isdigit():
        warnings.append("Service ID must be numeric.")
    if not _value(draft, "service", "serviceName"):
        warnings.append("Service name is required.")
    if not _value(draft, "service", "agentCode"):
        warnings.append("Agent code is required.")
    sample = _value(draft, "barcode", "sampleBarcode")
    if sample and not sample.startswith("|"):
        warnings.append("Sample barcode should start with |.")
    fields = draft.get("fields", []) if isinstance(draft.get("fields"), list) else []
    agency_fields = {str(f.get("agencyField", "")) for f in fields}
    for required in ("BRCDE", "AMT"):
        if required not in agency_fields:
            warnings.append(f"Missing field {required}.")
    return warnings


def preview_draft(draft: dict[str, Any]) -> ServiceDraftResponse:
    rows = build_rows(draft)
    return ServiceDraftResponse(
        service_id=_value(draft, "service", "serviceId"),
        rows={name: len(values) for name, values in rows.items()},
        targets=TARGETS,
        warnings=validate_draft(draft),
    )


def _get_gspread_client():
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    raw_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    service_account_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()

    # Prefer JSON because hosted environments commonly store credentials as an
    # env var. A bad GOOGLE_SERVICE_ACCOUNT_FILE should not mask a valid JSON.
    if raw_json:
        try:
            creds = Credentials.from_service_account_info(json.loads(raw_json), scopes=scopes)
        except json.JSONDecodeError as exc:
            raise ValueError(f"GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON: {exc}") from exc
        return gspread.authorize(creds)

    if service_account_file:
        if not os.path.isfile(service_account_file):
            raise ValueError(f"GOOGLE_SERVICE_ACCOUNT_FILE does not exist or is not a file: {service_account_file}")
        if not os.access(service_account_file, os.R_OK):
            raise ValueError(f"GOOGLE_SERVICE_ACCOUNT_FILE is not readable by the app: {service_account_file}")
        try:
            creds = Credentials.from_service_account_file(service_account_file, scopes=scopes)
        except PermissionError as exc:
            raise ValueError(f"GOOGLE_SERVICE_ACCOUNT_FILE permission denied: {service_account_file}") from exc
        return gspread.authorize(creds)

    raise ValueError("Set GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_FILE to save service drafts.")


def _with_backoff(fn):
    from gspread.exceptions import APIError

    delay = 1.0
    for attempt in range(6):
        try:
            return fn()
        except APIError as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status != 429 or attempt == 5:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 16)


def save_draft(draft: dict[str, Any]) -> ServiceDraftResponse:
    rows = build_rows(draft)
    service_id = _value(draft, "service", "serviceId")
    client = _get_gspread_client()
    spreadsheet = _with_backoff(lambda: client.open_by_key(SERVICE_CONFIG_SPREADSHEET_ID))

    for sheet_name, header in SHEET_HEADERS.items():
        try:
            ws = spreadsheet.worksheet(sheet_name)
        except Exception:
            ws = spreadsheet.add_worksheet(title=sheet_name, rows=200, cols=max(len(header), 12))
            _with_backoff(lambda ws=ws, header=header: ws.update("A1", [header], value_input_option="USER_ENTERED"))

        existing = _with_backoff(ws.get_all_values)
        if not existing:
            _with_backoff(lambda ws=ws, header=header: ws.update("A1", [header], value_input_option="USER_ENTERED"))
            existing = [header]

        duplicate = any(row and str(row[0]).strip() == service_id for row in existing[1:])
        if duplicate:
            raise ValueError(f"Service {service_id} already exists in PayAtPost-ServiceConfig sheet {sheet_name}.")

        values = rows[sheet_name]
        if values:
            _with_backoff(lambda ws=ws, values=values: ws.append_rows(values, value_input_option="USER_ENTERED"))

    return ServiceDraftResponse(
        service_id=service_id,
        spreadsheet_id=SERVICE_CONFIG_SPREADSHEET_ID,
        saved_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        rows={name: len(values) for name, values in rows.items()},
        targets=TARGETS,
        warnings=validate_draft(draft),
    )
