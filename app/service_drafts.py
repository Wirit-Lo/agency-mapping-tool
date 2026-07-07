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

from app.sheets.google_sheets import SPREADSHEET_IDS

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


class DeleteDraftRequest(BaseModel):
    service_id: str


class DeleteDraftResponse(BaseModel):
    service_id: str
    spreadsheet_id: str
    deleted_rows: dict[str, int]
    deleted_at: str


class ApplyMainResponse(BaseModel):
    service_id: str
    applied_at: Optional[str] = None
    dry_run: bool
    rows: dict[str, int]
    targets: list[dict[str, str]]
    warnings: list[str]


class RollbackMainRequest(BaseModel):
    service_id: str


class RollbackMainResponse(BaseModel):
    service_id: str
    rolled_back_at: str
    deleted_rows: dict[str, int]
    targets: list[dict[str, str]]


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



def _col_name(index: int) -> str:
    name = ""
    while index:
        index, rem = divmod(index - 1, 26)
        name = chr(65 + rem) + name
    return name


def _style_service_config(spreadsheet) -> None:
    requests = []
    for sheet_name, header in SHEET_HEADERS.items():
        try:
            ws = spreadsheet.worksheet(sheet_name)
        except Exception:
            continue
        sheet_id = ws.id
        values = _with_backoff(ws.get_all_values)
        row_count = max(len(values), 1)
        col_count = max(len(header), 1)
        requests.extend([
            {
                "repeatCell": {
                    "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": col_count},
                    "cell": {"userEnteredFormat": {"backgroundColor": {"red": 0.24, "green": 0.45, "blue": 0.74}, "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True}, "horizontalAlignment": "CENTER"}},
                    "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
                }
            },
            {
                "updateSheetProperties": {
                    "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
                    "fields": "gridProperties.frozenRowCount",
                }
            },
            {
                "setBasicFilter": {
                    "filter": {"range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": max(row_count, 2), "startColumnIndex": 0, "endColumnIndex": col_count}}
                }
            },
        ])
        if row_count > 1:
            current_service = None
            block_start = 1
            color_toggle = False
            for idx in range(1, row_count + 1):
                row_service = values[idx - 1][0].strip() if idx - 1 < len(values) and values[idx - 1] else ""
                boundary = idx == row_count or (idx > 1 and row_service != current_service)
                if idx == 2:
                    current_service = row_service
                    block_start = 1
                if boundary and idx > 2:
                    color = {"red": 0.92, "green": 0.96, "blue": 1.0} if color_toggle else {"red": 1.0, "green": 1.0, "blue": 1.0}
                    requests.append({
                        "repeatCell": {
                            "range": {"sheetId": sheet_id, "startRowIndex": block_start, "endRowIndex": idx - 1, "startColumnIndex": 0, "endColumnIndex": col_count},
                            "cell": {"userEnteredFormat": {"backgroundColor": color, "borders": {"bottom": {"style": "SOLID", "width": 1, "color": {"red": 0.80, "green": 0.86, "blue": 0.92}}}}},
                            "fields": "userEnteredFormat(backgroundColor,borders)",
                        }
                    })
                    color_toggle = not color_toggle
                    current_service = row_service
                    block_start = idx - 1
            if row_count == 2:
                requests.append({
                    "repeatCell": {
                        "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 2, "startColumnIndex": 0, "endColumnIndex": col_count},
                        "cell": {"userEnteredFormat": {"backgroundColor": {"red": 0.92, "green": 0.96, "blue": 1.0}}},
                        "fields": "userEnteredFormat.backgroundColor",
                    }
                })
    if requests:
        _with_backoff(lambda: spreadsheet.batch_update({"requests": requests}))


def _service_config_rows_to_main_rows(draft: dict[str, Any]) -> dict[str, dict[str, Any]]:
    service = draft.get("service", {}) if isinstance(draft.get("service"), dict) else {}
    barcode = draft.get("barcode", {}) if isinstance(draft.get("barcode"), dict) else {}
    fields = draft.get("fields", []) if isinstance(draft.get("fields"), list) else []
    defaults = draft.get("defaults", []) if isinstance(draft.get("defaults"), list) else []
    derived = draft.get("derived", []) if isinstance(draft.get("derived"), list) else []
    receipt_lines = draft.get("receiptLines", []) if isinstance(draft.get("receiptLines"), list) else []
    validation = draft.get("validation", {}) if isinstance(draft.get("validation"), dict) else {}
    service_id = str(service.get("serviceId", "")).strip()
    service_name = service.get("serviceName", "")
    agent_code = service.get("agentCode", "")
    agent_name = service.get("agentName", "")
    category = service.get("category", "Utilities")
    fee = service.get("fee", "")
    start_date = service.get("startDate", "")
    status = service.get("status", "Open")
    service_type = service.get("serviceType", "OFFLINE")
    barcode_validate = barcode.get("validate", "")
    suffixes = barcode.get("suffixes", []) if isinstance(barcode.get("suffixes"), list) else []
    if not suffixes:
        suffixes = [""]

    stat_row = [""] * 16
    stat_row[0] = service_id
    stat_row[1] = service_name
    stat_row[2] = start_date
    stat_row[4] = status
    stat_row[5] = service_type
    stat_row[6] = "บริการรับชำระ"
    stat_row[7] = category
    stat_row[12] = fee
    stat_row[13] = 0
    stat_row[14] = 0
    stat_row[15] = 100000

    pap_rows = [[agent_code, agent_name, "", "", "", "", "", "", "", "", "", "", "", "", "", ""], ["", service_name, service_id, "", "", "", "", "", "", "", "", "", "", "", "", ""]]
    for field in fields:
        fd_name = str(field.get("fdName", ""))
        pap_rows.append(["", "", field.get("seq", ""), field.get("label", ""), field.get("fieldType", "") or _field_type(fd_name), fd_name, field.get("agencyField", ""), field.get("visible", "1"), field.get("readonly", "1"), "", "", "", "", "", "", ""])

    spec_rows = [[agent_code, agent_name, "", "", "", "", "", "", "", ""], ["", service_name, service_id, "", "", "", "", "", "", ""], ["", "", barcode.get("basePrefix", ""), "00", "", "", "", "", "", ""]]
    for idx, suffix in enumerate(suffixes):
        sample = barcode.get("sampleBarcode", "")
        spec_rows.append(["", "", sample, "100" if idx == 0 else "", "รหัสบาร์โค้ด", "D_TEXT_01", "1", "", "BRCDE", barcode_validate if idx == 0 else ""])
    for field in fields:
        if str(field.get("seq", "")) == "100":
            continue
        spec_rows.append(["", "", "", field.get("seq", ""), field.get("label", ""), field.get("fdName", ""), field.get("sPos", ""), field.get("ePos", ""), field.get("agencyField", ""), ""])

    validation_by_seq = {"100": barcode_validate, "101": validation.get("dueDate", ""), "111": validation.get("amount", "")}
    validate_rows = [[agent_code, agent_name, "", "", "", "", "", "", "", "", "", "", ""], ["", service_name, service_id, "", "", "", "", "", "", "", "", "", ""]]
    for field in fields:
        seq = str(field.get("seq", ""))
        validate_rows.append(["", "", seq, field.get("label", ""), field.get("fieldType", "") or _field_type(str(field.get("fdName", ""))), field.get("fdName", ""), field.get("agencyField", ""), field.get("visible", "1"), field.get("readonly", "1"), "(blank)", "(blank)", validation_by_seq.get(seq, ""), "(blank)"])

    default_rows = []
    for item in defaults:
        attr = str(item.get("attribute", ""))
        default_rows.append([service_id, service_name, _field_label(fields, attr, attr), item.get("value", ""), attr, "", "No" if item.get("editable", "N") == "N" else "Yes"])

    derived_rows = []
    for item in derived:
        formula = str(item.get("formula", "") or "")
        if formula.strip():
            derived_rows.append([service_id, "SBA", item.get("attribute", ""), item.get("sourceField", ""), formula, item.get("sameAttributeSource", "No Match")])

    receipt_rows = []
    pf_fmt_id = _pf_fmt_id(service_id)
    for index, line in enumerate(receipt_lines, start=1):
        if str(line).strip():
            receipt_rows.append([f"{service_id} : {service_name}", pf_fmt_id, 9 + index, 2, index, "NULL", 1, str(line), "NULL", "NULL", "NULL", "NULL"])

    provider_rows = [[service_id, "SBA", "", "", 1, "Added from ServiceConfig"]]
    map_rows = [[agent_code, agent_name, service_id]]
    return {
        "StatSUM": {"filename": "PayAtPost-StatSUM_Master_V1.2.xlsx", "sheet": "Main", "service_col": 1, "rows": [stat_row]},
        "PAP_ALL_Fields": {"filename": "PayAtPost-PAP_ALL_ServiceID_V1.2-1.3.xlsx", "sheet": "Fields", "service_col": 3, "rows": pap_rows},
        "PAP_ALL_MapAgencyID": {"filename": "PayAtPost-PAP_ALL_ServiceID_V1.2-1.3.xlsx", "sheet": "Map Agency ID", "service_col": 3, "rows": map_rows},
        "SpecBarcode_NotBOT_STD": {"filename": "PayAtPost-SpecBarcode_V1.5.xlsx", "sheet": "NotBOT-STD", "service_col": 3, "rows": spec_rows},
        "ValidateScriptText": {"filename": "PayAtPost-ValidateScriptText.xlsx", "sheet": "Functions", "service_col": 3, "rows": validate_rows},
        "DefaultValue": {"filename": "PayAtPost-DefaultValue_V1.0.xlsx", "sheet": "Default", "service_col": 1, "rows": default_rows},
        "DerivedData": {"filename": "AgencyDerivedDataRequirements.xlsx", "sheet": "DerivedData", "service_col": 1, "rows": derived_rows},
        "ConfigReceipt": {"filename": "PayAtPost-ConfigReceipt_V1.0.xlsx", "sheet": "Receipt", "service_col": 1, "rows": receipt_rows},
        "ServiceProviders": {"filename": "AgencyServiceProviders.xlsx", "sheet": "ServiceProvider", "service_col": 1, "rows": provider_rows},
    }


def _open_target_worksheet(client, filename: str, sheet_name: str):
    spreadsheet_id = SPREADSHEET_IDS[filename]
    ss = _with_backoff(lambda: client.open_by_key(spreadsheet_id))
    return ss, _with_backoff(lambda: ss.worksheet(sheet_name))


def preview_apply_main(draft: dict[str, Any]) -> ApplyMainResponse:
    service_id = _value(draft, "service", "serviceId")
    warnings = validate_draft(draft)
    targets = _service_config_rows_to_main_rows(draft)
    rows = {name: len(info["rows"]) for name, info in targets.items()}
    plan = [{"section": name, "file": info["filename"], "sheet": info["sheet"]} for name, info in targets.items()]
    return ApplyMainResponse(service_id=service_id, dry_run=True, rows=rows, targets=plan, warnings=warnings)


def apply_main(draft: dict[str, Any]) -> ApplyMainResponse:
    service_id = _value(draft, "service", "serviceId")
    warnings = validate_draft(draft)
    if warnings:
        raise ValueError("Cannot apply to main Excel while draft has warnings: " + "; ".join(warnings))
    client = _get_gspread_client()
    targets = _service_config_rows_to_main_rows(draft)

    opened = []
    for name, info in targets.items():
        if not info["rows"]:
            continue
        ss, ws = _open_target_worksheet(client, info["filename"], info["sheet"])
        existing = _with_backoff(ws.get_all_values)
        col = int(info["service_col"]) - 1
        duplicate = any(len(row) > col and str(row[col]).strip().split(" : ")[0] == service_id for row in existing)
        if duplicate:
            raise ValueError(f"Service {service_id} already exists in {info['filename']} / {info['sheet']}.")
        opened.append((name, info, ws))

    for _, info, ws in opened:
        _with_backoff(lambda ws=ws, values=info["rows"]: ws.append_rows(values, value_input_option="USER_ENTERED"))

    rows = {name: len(info["rows"]) for name, info in targets.items()}
    plan = [{"section": name, "file": info["filename"], "sheet": info["sheet"]} for name, info in targets.items()]
    return ApplyMainResponse(
        service_id=service_id,
        applied_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        dry_run=False,
        rows=rows,
        targets=plan,
        warnings=[],
    )


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

    _style_service_config(spreadsheet)

    return ServiceDraftResponse(
        service_id=service_id,
        spreadsheet_id=SERVICE_CONFIG_SPREADSHEET_ID,
        saved_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        rows={name: len(values) for name, values in rows.items()},
        targets=TARGETS,
        warnings=validate_draft(draft),
    )


def delete_draft(service_id: str) -> DeleteDraftResponse:
    service_id = str(service_id).strip()
    if not service_id:
        raise ValueError("Service ID is required.")

    client = _get_gspread_client()
    spreadsheet = _with_backoff(lambda: client.open_by_key(SERVICE_CONFIG_SPREADSHEET_ID))
    deleted_rows: dict[str, int] = {}

    for sheet_name in SHEET_HEADERS:
        try:
            ws = spreadsheet.worksheet(sheet_name)
        except Exception:
            deleted_rows[sheet_name] = 0
            continue

        existing = _with_backoff(ws.get_all_values)
        row_numbers = [idx for idx, row in enumerate(existing, start=1) if idx > 1 and row and str(row[0]).strip() == service_id]
        for row_number in reversed(row_numbers):
            _with_backoff(lambda ws=ws, row_number=row_number: ws.delete_rows(row_number))
        deleted_rows[sheet_name] = len(row_numbers)

    _style_service_config(spreadsheet)

    return DeleteDraftResponse(
        service_id=service_id,
        spreadsheet_id=SERVICE_CONFIG_SPREADSHEET_ID,
        deleted_rows=deleted_rows,
        deleted_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )


def _main_targets_for_service_id(service_id: str) -> dict[str, dict[str, Any]]:
    return {
        "StatSUM": {"filename": "PayAtPost-StatSUM_Master_V1.2.xlsx", "sheet": "Main", "service_col": 1},
        "PAP_ALL_Fields": {"filename": "PayAtPost-PAP_ALL_ServiceID_V1.2-1.3.xlsx", "sheet": "Fields", "service_col": 3},
        "PAP_ALL_MapAgencyID": {"filename": "PayAtPost-PAP_ALL_ServiceID_V1.2-1.3.xlsx", "sheet": "Map Agency ID", "service_col": 3},
        "SpecBarcode_NotBOT_STD": {"filename": "PayAtPost-SpecBarcode_V1.5.xlsx", "sheet": "NotBOT-STD", "service_col": 3},
        "ValidateScriptText": {"filename": "PayAtPost-ValidateScriptText.xlsx", "sheet": "Functions", "service_col": 3},
        "DefaultValue": {"filename": "PayAtPost-DefaultValue_V1.0.xlsx", "sheet": "Default", "service_col": 1},
        "DerivedData": {"filename": "AgencyDerivedDataRequirements.xlsx", "sheet": "DerivedData", "service_col": 1},
        "ConfigReceipt": {"filename": "PayAtPost-ConfigReceipt_V1.0.xlsx", "sheet": "Receipt", "service_col": 1},
        "ServiceProviders": {"filename": "AgencyServiceProviders.xlsx", "sheet": "ServiceProvider", "service_col": 1},
    }


def rollback_main(service_id: str) -> RollbackMainResponse:
    service_id = str(service_id).strip()
    if not service_id:
        raise ValueError("Service ID is required.")

    client = _get_gspread_client()
    targets = _main_targets_for_service_id(service_id)
    deleted_rows: dict[str, int] = {}
    plan = []

    for name, info in targets.items():
        _, ws = _open_target_worksheet(client, info["filename"], info["sheet"])
        existing = _with_backoff(ws.get_all_values)
        col = int(info["service_col"]) - 1
        row_numbers = []
        for idx, row in enumerate(existing, start=1):
            if idx == 1:
                continue
            if len(row) <= col:
                continue
            value = str(row[col]).strip()
            if value.split(" : ")[0] == service_id:
                row_numbers.append(idx)
        for row_number in reversed(row_numbers):
            _with_backoff(lambda ws=ws, row_number=row_number: ws.delete_rows(row_number))
        deleted_rows[name] = len(row_numbers)
        plan.append({"section": name, "file": info["filename"], "sheet": info["sheet"]})

    return RollbackMainResponse(
        service_id=service_id,
        rolled_back_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        deleted_rows=deleted_rows,
        targets=plan,
    )
