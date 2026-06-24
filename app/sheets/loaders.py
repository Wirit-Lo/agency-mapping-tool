"""Loaders — read source workbooks into RawData lists.

Ported from Helper.cs Process* methods. Reads cells by 1-based column index
(matching the C# Cells[i,n] semantics) via openpyxl. A later Google-Sheets
loader will expose the same functions over get_all_values() rows.

Column indices come from the config JSON (see tests/fixtures/THP Agency Data Mapping.json)
and hardcoded columns documented in LOGIC_SPEC.md section 1.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import openpyxl

from app.models.raw import (
    AgentRawData,
    AgencyMasterRawData,
    ConfigReceiptDetailRawData,
    ConfigReceiptRawData,
    DefaultValueRawData,
    DerivedDataRequirementsRawData,
    DropdownValueRawData,
    ServiceProviderRawData,
    ValidateRawData,
)
from app.pipeline.helpers import (
    get_cell_value,
    get_fee_value,
    get_validate_function_name,
    to_int,
)
from app.pipeline.rules import PCC_SERVICES


def _excel_grid(path: str, sheet_index: int = 0) -> list[list[Any]]:
    """Default grid provider: read worksheet from a local .xlsx via openpyxl."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[sheet_index]
    grid = [list(row) for row in ws.iter_rows(values_only=True)]
    wb.close()
    return grid


# Active grid provider. runner.py can swap this to a Google-Sheets-backed one.
# Signature: (path_or_filename: str, sheet_index: int) -> list[list[Any]]
_grid_provider = _excel_grid


def set_grid_provider(provider) -> None:
    """Inject an alternate grid provider (e.g. Google Sheets)."""
    global _grid_provider
    _grid_provider = provider


def _load_grid(path: str, sheet_index: int = 0) -> list[list[Any]]:
    """Return worksheet as list-of-rows (1-based access via row[col-1])."""
    return _grid_provider(path, sheet_index)


def _cell(grid: list[list[Any]], row1: int, col1: int) -> str:
    """1-based cell access mirroring C# xlRange.Cells[i,n] + GetCellValue."""
    r, c = row1 - 1, col1 - 1
    if r < 0 or r >= len(grid):
        return ""
    rowdata = grid[r]
    if c < 0 or c >= len(rowdata):
        return ""
    return get_cell_value(rowdata[c])


def _raw(grid: list[list[Any]], row1: int, col1: int) -> Any:
    r, c = row1 - 1, col1 - 1
    if r < 0 or r >= len(grid):
        return None
    rowdata = grid[r]
    if c < 0 or c >= len(rowdata):
        return None
    return rowdata[c]


def _parse_date(raw: Any) -> Optional[datetime]:
    """Handle Excel serial int, datetime, or parseable string."""
    if raw is None:
        return None
    # Replicate C# ProcessAgencyMasterData date handling.
    # In C#, GetCellValue returns Excel's Value2, which for a DATE cell is an
    # OADate serial number string, not a formatted date. The code then tries
    # int.TryParse (integer serial) then DateTime.TryParse.
    #   - midnight datetime  -> integer serial (e.g. "42186") -> FromOADate OK
    #   - datetime with time -> fractional serial (e.g. "37687.41") -> BOTH
    #     parses FAIL -> StartDate stays null (tag omitted).
    # openpyxl gives us a real datetime, so we must drop the time-bearing ones
    # to match the original output.
    if isinstance(raw, datetime):
        if raw.hour or raw.minute or raw.second or raw.microsecond:
            return None
        return raw

    s = str(raw).strip()
    if not s or s == "(blank)":
        return None
    # Excel serial number
    try:
        serial = int(s)
        return datetime(1899, 12, 30) + __import__("datetime").timedelta(days=serial)
    except ValueError:
        pass
    # Normalize malformed separators. Source data has values like "01/10,2018"
    # (comma instead of slash); .NET DateTime.TryParse salvages these to a date.
    normalized = s.replace(",", "/")
    for candidate in (s, normalized):
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(candidate, fmt)
            except ValueError:
                continue
    return None


# ---------------------------------------------------------------------------
# Fixed loaders
# ---------------------------------------------------------------------------
def load_derived_data_requirements(path: str) -> list[DerivedDataRequirementsRawData]:
    grid = _load_grid(path)
    out: list[DerivedDataRequirementsRawData] = []
    for i in range(2, len(grid) + 1):
        object_id = _cell(grid, i, 1)
        attribute = _cell(grid, i, 3)
        source_field = _cell(grid, i, 4)
        formula = _cell(grid, i, 5)
        if not object_id or not attribute or not formula:
            continue
        if any(e.ObjectId == object_id and e.Attribute == attribute for e in out):
            continue
        out.append(DerivedDataRequirementsRawData(
            ObjectId=object_id, Attribute=attribute,
            SourceField=source_field, Formula=formula,
        ))
    return out


def load_service_providers(path: str) -> list[ServiceProviderRawData]:
    grid = _load_grid(path)
    out: list[ServiceProviderRawData] = []
    for i in range(2, len(grid) + 1):
        object_id = _cell(grid, i, 1)
        if not object_id:
            continue
        if any(e.ObjectId == object_id for e in out):
            continue
        out.append(ServiceProviderRawData(
            ObjectId=object_id,
            Type=_cell(grid, i, 2),
            ProviderName=_cell(grid, i, 3),
            WorkflowId=_cell(grid, i, 4),
            BarcodeRequired=_cell(grid, i, 5),
        ))
    return out


def load_dropdown_values(path: str) -> list[DropdownValueRawData]:
    grid = _load_grid(path)
    out: list[DropdownValueRawData] = []
    for i in range(2, len(grid) + 1):
        dropdown_name = _cell(grid, i, 5)
        if not dropdown_name:
            continue
        out.append(DropdownValueRawData(
            ObjectId=_cell(grid, i, 2),
            DropdownId=_cell(grid, i, 3),
            DropdownCaption=_cell(grid, i, 4),
            DropdownName=dropdown_name,
            FieldName=_cell(grid, i, 6),
            DerivedData=_cell(grid, i, 8),
            SourceField=_cell(grid, i, 9),
        ))
    return out


def load_default_values(path: str) -> list[DefaultValueRawData]:
    grid = _load_grid(path)
    out: list[DefaultValueRawData] = []
    for i in range(2, len(grid) + 1):
        default_value = _cell(grid, i, 4)
        reference_field = _cell(grid, i, 5)
        if not default_value or not reference_field:
            continue
        out.append(DefaultValueRawData(
            ObjectId=_cell(grid, i, 1),
            DefaultValue=default_value,
            ReferenceField=reference_field,
        ))
    return out


def load_agent_master(path: str) -> list[AgentRawData]:
    grid = _load_grid(path)
    out: list[AgentRawData] = []
    for i in range(4, len(grid) + 1):
        agent_code_int = to_int(_cell(grid, i, 3))
        if agent_code_int <= 0:
            continue
        agent_code = str(agent_code_int)
        existing = next((e for e in out if e.AgentCode == agent_code), None)
        data = dict(
            AgentCode=agent_code,
            AgentName=_cell(grid, i, 4),
            FullNameTH=_cell(grid, i, 5),
            FullNameEN=_cell(grid, i, 6),
            TaxNumber=_cell(grid, i, 7),
            BillName=_cell(grid, i, 11),
            BillAddress=_cell(grid, i, 12),
        )
        if existing:
            for k, v in data.items():
                setattr(existing, k, v)
        else:
            out.append(AgentRawData(**data))
    return out


def load_config_receipt(path: str) -> list[ConfigReceiptRawData]:
    """Grouped by service (col1), details from row 4. Mirrors Helper.cs:348."""
    grid = _load_grid(path)
    out: list[ConfigReceiptRawData] = []
    service = ""
    current: Optional[ConfigReceiptRawData] = None
    details: list[ConfigReceiptDetailRawData] = []

    for i in range(4, len(grid) + 1):
        temp_service = _cell(grid, i, 1)
        if service != temp_service:
            if current is not None and details:
                current.Details.extend(details)
                out.append(current)
                details = []
            service = temp_service
            current = ConfigReceiptRawData(Service=service)
        if service and current is not None:
            line_number = to_int(_cell(grid, i, 5))
            line_condition = _cell(grid, i, 6)
            mapping_condition = _cell(grid, i, 8)
            decimal_condition = _cell(grid, i, 9)
            details.append(ConfigReceiptDetailRawData(
                LineNumber=line_number,
                LineCondition=line_condition,
                MappingCondition=mapping_condition,
                DecimalCondition=decimal_condition,
            ))
    if current is not None and details:
        current.Details.extend(details)
        out.append(current)

    _extract_service_id_and_field_name(out)
    return out


def _get_field_name_equivalent(field: str) -> str:
    """Helper.cs:1435 GetFieldNameEquivalent."""
    field_values = {
        "SI_INFOREFNO": "D_TEXT",
        "SI_MONEYREFNO": "D_MONEY",
        "SI_DATEREFNO": "D_DATE",
        "SI_INTREFNO": "D_INT",
    }
    idx = field.rfind("_")
    field_no = field[idx + 1:]
    try:
        num = int(field_no)
    except ValueError:
        return ""
    fld = field[:idx]
    if fld not in field_values:
        return ""
    return f"{field_values[fld]}_{num:02d}"


def _extract_service_id_and_field_name(configs: list[ConfigReceiptRawData]) -> None:
    """Helper.cs:2453 ExtractServiceIdAndFieldName."""
    for config in configs:
        service = config.Service.strip()
        length = 0
        if service.find(":") > 0:
            length = service.replace(" ", "").strip().find(":")
        elif service.find(" ") > 0:
            length = service.find(" ")
        if length > 0:
            config.ObjectId = service[:length]
            for detail in config.Details:
                condition = detail.MappingCondition
                lb = condition.find("[")
                if lb >= 0:
                    rb = condition.find("]")
                    field = condition[lb + 1:rb]
                    if field:
                        detail.FD_NAME = _get_field_name_equivalent(field)


# ---------------------------------------------------------------------------
# Config-driven loaders
# ---------------------------------------------------------------------------
def load_agency_master(path: str, cfg: dict) -> list[AgencyMasterRawData]:
    """Helper.cs:523 ProcessAgencyMasterData. cfg = config['DerivedData']."""
    grid = _load_grid(path, cfg["SheetNo"] - 1)
    out: list[AgencyMasterRawData] = []
    for i in range(cfg["RowNo"], len(grid) + 1):
        sid = _cell(grid, i, cfg["IdColNo"])
        if to_int(sid) <= 0 and sid != "0":
            if to_int(sid) == 0 and not sid.isdigit():
                continue
        if not sid.isdigit():
            continue
        status = _cell(grid, i, cfg["StatusColNo"])
        if status.lower() != "open":
            continue
        transaction_type = _cell(grid, i, cfg["TransactionTypeColNo"])
        service_category = _cell(grid, i, cfg["ServiceCategoryColNo"])
        fee, scope = get_fee_value(_raw(grid, i, cfg["FeeAmountColNo"]))
        out.append(AgencyMasterRawData(
            ObjectId=sid,
            Caption=_cell(grid, i, cfg["CaptionColNo"]),
            MinAmount=_cell(grid, i, cfg["MinAmountColNo"]),
            MaxAmount=_cell(grid, i, cfg["MaxAmountColNo"]),
            MaxAmountPerDay=_cell(grid, i, cfg["MaxPerDayColNo"]),
            Fee=fee,
            StartDate=_parse_date(_raw(grid, i, cfg["StartDateColNo"])),
            EndDate=_parse_date(_raw(grid, i, cfg["EndDateColNo"])),
            Status=status,
            TransactionType=transaction_type,
            ServiceType=_cell(grid, i, cfg["ServiceTypeColNo"]),
            ServiceCategory=service_category if service_category else "Others",
            Scope=scope,
        ))
    return out


def load_validation(path: str, cfg: dict, master_ids: set[str]) -> list[ValidateRawData]:
    """Helper.cs:616 ProcessValidationData. cfg = config['ValidationData']."""
    grid = _load_grid(path, cfg["SheetNo"] - 1)
    out: list[ValidateRawData] = []
    service_id = 0
    for i in range(cfg["RowNo"], len(grid) + 1):
        temp = _cell(grid, i, cfg["IdColNo"])
        if not temp.isdigit():
            continue
        temp_service_id = int(temp)
        if len(str(temp_service_id)) == 5 or temp_service_id == 1819:
            service_id = temp_service_id
            temp_service_id = 0
        if str(service_id) not in master_ids:
            continue
        if temp_service_id <= 0:
            continue
        validate = get_validate_function_name(
            _cell(grid, i, cfg["ValidateColNo"]), service_id, temp_service_id
        )
        if not validate:
            continue
        suffix = to_int(_cell(grid, i, cfg["SuffixColNo"]))
        reference_field = _cell(grid, i, 7) or _cell(grid, i, 6)
        if reference_field == "REFNO3":
            reference_field = "AcctNo"
        elif reference_field == "AMT":
            reference_field = "Amount"
        out.append(ValidateRawData(
            ObjectId=str(service_id),
            Suffix=suffix,
            ReferenceField=reference_field,
            ValidateMethod=validate,
        ))
    return out
