"""Pure helper functions — ported from Helper.cs.

These are the value-parsing / mapping primitives used throughout the pipeline.
Ported verbatim (with line refs) so output matches byte-for-byte.
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

from app.models.raw import ScopeData

# Excel error sentinel seen in the Fee column (Helper.cs:1466)
_EXCEL_ERROR_SENTINEL = "-2146826246"
_BLANK_SENTINEL = "(blank)"


def get_cell_value(raw) -> str:
    """Helper.cs:1415 GetCellValue.

    None/empty -> "", literal "(blank)" -> "", else str(value).strip().

    openpyxl returns numeric cells as float/int. C# Excel Value2.ToString()
    renders an integer-valued number without a trailing ".0", so we match that:
    1819.0 -> "1819", but 12.5 -> "12.5".
    """
    if raw is None:
        return ""
    if isinstance(raw, float) and raw.is_integer():
        text = str(int(raw))
    else:
        text = str(raw).strip()
    if text == "" or text == _BLANK_SENTINEL:
        return ""
    return text


def to_int(text: Optional[str]) -> int:
    """Helper.cs:1302 ToInt — parse int or 0."""
    if text is None:
        return 0
    try:
        return int(str(text).strip())
    except (ValueError, TypeError):
        return 0


def get_mapped_field_type(field_type: str) -> str:
    """Helper.cs:1343 GetMappedFieldType.

    EditMask/EditMaskYear are intentionally returned as-is for later detection.
    """
    result = field_type
    ft = field_type.lower()
    if ft in ("currencyfield", "paymentfield"):
        result = "Currency"
    elif ft == "datefield":
        result = "Date"
    elif ft == "numberfield":
        result = "Numeric"
    elif ft == "passwordfield":
        result = "PasswordField"
    elif ft in ("textarea", "textfield"):
        result = "Alphanumeric"
    elif ft == "combobox":
        result = "ComboBox"
    return result


_TBC_BY_TYPE = {
    "Button": "TBC_Field_Button",
    "ComboBox": "TBC_Field_ComboBox",
    "Currency": "TBC_Field_Currency",
    "Date": "TBC_Field_Date",
    "Numeric": "TBC_Field_Numeric",
    "EditMask": "TBC_Field_EditMask",
    "Alphanumeric": "TBC_Field_Alphanumeric",
}


def get_attribute_name(field_type: str, attribute_name: str) -> str:
    """Helper.cs:1375 GetAttributeName.

    Empty name -> TBC_Field_<type> (fallback to field_type itself).
    """
    if attribute_name == "":
        return _TBC_BY_TYPE.get(field_type, field_type)
    return attribute_name


def get_fee_value(raw) -> Tuple[Optional[str], Optional[ScopeData]]:
    """Helper.cs:1458 GetFeeValue.

    Returns (fee_string, scope_data).
    - blank / "(blank)" / excel-error -> (None, None)
    - plain int -> (str(int) + "00", None)   # pad satang
    - conditional "1.100,2.150" -> ScopeData(within, outside)
    """
    if raw is None:
        return None, None
    text = str(raw).strip()
    if text == "" or text == _BLANK_SENTINEL or text == _EXCEL_ERROR_SENTINEL:
        return None, None

    fee_split = text.split(",")
    first_length = len(fee_split[0])
    second_length = len(fee_split[1]) if len(fee_split) > 1 else 0

    # plain integer fee
    try:
        fee = int(text)
        s = str(fee)
        return s + "00", None  # pad 2 zeros for satang
    except ValueError:
        pass

    # conditional fees: strip "1." "2." "," then keep digits
    cell_value = text.replace("1.", "").replace("2.", "").replace(",", "")
    fee_values = "".join(ch for ch in cell_value if ch.isdigit())
    if len(fee_values) > 0:
        within = fee_values[0:first_length] + "00"
        outside = fee_values[first_length:first_length + second_length] + "00"
        scope = ScopeData(WithinBangkokFee=within, OutsideBangkokFee=outside)
        return within, scope

    return None, None


_FUNC_NAME_RE = re.compile(r"^([A-Z0-9_]+)", re.IGNORECASE)


def get_validate_function_name(validate: str, service_id: int, suffix: int) -> str:
    """Helper.cs:1505 GetValidateFunctionName.

    Extracts the validation function name following a 'func:' / 'func :' marker.
    Returns the leading [A-Z0-9_]+ token, or "".
    """
    if not validate:
        return ""

    result = ""
    lowered = validate.lower()
    # mirror the C# precedence: func:, then 'func :', then 'func : '
    idx = lowered.find("func:")
    if idx != -1:
        result = validate[idx + 5:].strip()
    else:
        idx = lowered.find("func :")
        if idx != -1:
            result = validate[idx + 6:].strip()
        else:
            idx = lowered.find("func : ")
            if idx != -1:
                result = validate[idx + 7:].strip()

    if result:
        m = _FUNC_NAME_RE.match(result)
        if m:
            result = m.group(1)
    return result
