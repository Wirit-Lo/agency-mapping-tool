"""WebObject serializers — format authority ported from Consts.cs + Form1.cs.

Each function renders ONE object as a single line. Optional tags are omitted
entirely when empty (never emitted blank). Output files are wrapped with
#ReplaceWebObjectsBegin/End and written as UTF-8 with BOM, LF line endings.
"""
from __future__ import annotations

from typing import Iterable

from app.models.raw import (
    AgencyRawData,
    DerivedDataRawData,
    FieldDataRawData,
    PostingDataRaw,
)
from app.pipeline.rules import PCC_SERVICES

# ---------------------------------------------------------------------------
# File wrapping
# ---------------------------------------------------------------------------
_PATH_PREFIX = "/Configurations/EGA/EGAAgency"


def wrap_file(object_type: str, lines: Iterable[str]) -> str:
    """Wrap serialized objects with the #ReplaceWebObjects header/footer.

    Real output uses LF line endings and a trailing newline after End.
    """
    body = list(lines)
    out = [f"#ReplaceWebObjectsBegin -l {_PATH_PREFIX}/{object_type}/"]
    out.extend(body)
    out.append("#ReplaceWebObjectsEnd")
    return "\n".join(out) + "\n"


def write_file(path: str, content: str) -> None:
    """Write as UTF-8 with BOM + LF (matches .NET StreamWriter output observed)."""
    with open(path, "w", encoding="utf-8-sig", newline="\n") as fh:
        fh.write(content)


# ---------------------------------------------------------------------------
# Date formatting
# ---------------------------------------------------------------------------
_DATE_PARSE_FORMATS = {
    "50628_REFNO4": "<DateParseFormat:YYYYMMDD>",
    "50710_REFNO4": "<DateParseFormat:YYYYMMDD>",
    "51120_REFNO5": "<DateParseFormat:DDMMYYYY>",
    "50982_REFNO6": "<DateParseFormat:DDMMYY><CalendarName:ThaiBuddhist>",
    "50002_REFNO7": "<DateParseFormat:DDMMYY><CalendarName:ThaiBuddhist>",
    "50131_REFNO4": "<DateParseFormat:DDMMYYYY><CalendarName:ThaiBuddhist>",
}


def _date_tag(tag: str, value) -> str:
    return f"<{tag}:{value.strftime('%Y-%m-%d')}>" if value is not None else ""


# ---------------------------------------------------------------------------
# AgencyScheme  (Consts.cs:38-42, Form1.cs:305-409)
# ---------------------------------------------------------------------------
def serialize_agency_scheme(d: AgencyRawData) -> list[str]:
    """Returns a LIST of scheme lines.

    Standard services -> 1 line.
    iframe/exe services -> 2 lines: a Custom object (plain id) + an _Actual object.
    Mirrors Form1.cs:322-409.
    """
    start_date = _date_tag("StartDate", d.StartDate)
    end_date = _date_tag("EndDate", d.EndDate)

    # Special Case: 50533 & 50535 University Service — remove end dates
    if d.ObjectId in ("50533", "50535"):
        end_date = ""

    availability = (
        f"<AvailabilitySet:{d.AvailabilitySet}>" if d.AvailabilitySet else ""
    )
    provider = (
        f"<AgencyProviderName:{d.AgencyProviderName}>" if d.AgencyProviderName else ""
    )
    workflow = f"<WorkflowId:{d.WorkflowId}>" if d.WorkflowId else ""

    agency_data = "".join(f"<FieldId:{f.ObjectId}>" for f in d.FieldData)
    postings = "".join(f"<Posting:{p.ObjectId}>" for p in d.PostingData)
    derived = "".join(
        f"<Variables:{dd.ObjectId}>" for dd in d.DerivedData if dd.ObjectId
    )
    tags = "".join(f"<Tag:{t}>" for t in d.Tags)

    is_iframe_or_exe = (
        "iframe" in d.TransactionType.lower() or "exe" in d.TransactionType.lower()
    )

    has_secondary = bool(d.PrimaryBarcode) and not d.SchemeIdString
    lines: list[str] = []

    def obj(object_id: str, body: str) -> str:
        return f"<Object:<Path:{_PATH_PREFIX}/AgencyScheme/{object_id}>><Contents:<Data:{body}>>"

    if is_iframe_or_exe:
        # (1) Custom object — plain ObjectId, only AcctNo + Amount fields,
        #     first posting only, workflow Custom.Agency.Web/Exe<id>
        acct = next((f for f in d.FieldData if f.AttributeName == "AcctNo"), None)
        amount = next((f for f in d.FieldData if f.AttributeName == "Amount"), None)
        agency_data_custom = ""
        if acct is not None:
            agency_data_custom += f"<FieldId:{acct.ObjectId}>"
        if amount is not None:
            agency_data_custom += f"<FieldId:{amount.ObjectId}>"
        postings_custom = f"<Posting:{d.PostingData[0].ObjectId}>"
        prefix = "Custom.Agency.Web" if "iframe" in d.TransactionType.lower() else "Custom.Agency.Exe"
        workflow_custom = f"<WorkflowId:{prefix}{d.ObjectId}>"
        custom_body = (
            f"<SchemeName:{d.SchemeName}><SchemeDescription:{d.SchemeDescription}>"
            f"<AllowInvokeList:1><AllowInvokeButton:1>"
            f"<AgencyData:{agency_data_custom}><Postings:{postings_custom}><Tags:{tags}>"
            f"{workflow_custom}{start_date}{end_date}{availability}{provider}"
        )
        lines.append(obj(d.ObjectId, custom_body))

        # (2) _Actual object
        if has_secondary:
            secondary = f"<BarcodeDetailName:{d.PrimaryBarcode}>"
            actual_body = (
                f"<SchemeName:{d.SchemeName}><SchemeDescription:{d.SchemeDescription}>"
                f"<AccountCode:{d.AccountCode}><AllowInvokeList:0>"
                f"<SchemeIdString:{d.ObjectId}><SecondaryBarcodes:{secondary}>"
                f"<AgencyData:{agency_data}><Postings:{postings}>"
                f"<ExtractId:{d.ExtractId}><AllowInvokeButton:{d.AllowInvokeButton}>"
                f"<TxnType:{d.TxnType}><DerivedData:{derived}>"
                f"{start_date}{end_date}{availability}{provider}"
            )
        else:
            actual_body = (
                f"<SchemeName:{d.SchemeName}><SchemeDescription:{d.SchemeDescription}>"
                f"<AccountCode:{d.AccountCode}><AllowInvokeList:0>"
                f"<PrimaryBarcode:{d.PrimaryBarcode}><SchemeIdStart:{d.SchemeIdStart}>"
                f"<SchemeIdString:{d.SchemeIdString}>"
                f"<AgencyData:{agency_data}><Postings:{postings}>"
                f"<ExtractId:{d.ExtractId}><AllowInvokeButton:{d.AllowInvokeButton}>"
                f"<TxnType:{d.TxnType}><DerivedData:{derived}>"
                f"{start_date}{end_date}{availability}{provider}"
            )
        lines.append(obj(f"{d.ObjectId}_Actual", actual_body))
        return lines

    # Standard (non-iframe/exe) — includes <Tags:>
    if has_secondary:
        secondary = f"<BarcodeDetailName:{d.PrimaryBarcode}>"
        body = (
            f"<SchemeName:{d.SchemeName}><SchemeDescription:{d.SchemeDescription}>"
            f"<AccountCode:{d.AccountCode}><AllowInvokeList:{d.AllowInvokeList}>"
            f"<SchemeIdString:{d.ObjectId}><SecondaryBarcodes:{secondary}>"
            f"<AgencyData:{agency_data}><Postings:{postings}>"
            f"<ExtractId:{d.ExtractId}><AllowInvokeButton:{d.AllowInvokeButton}>"
            f"<TxnType:{d.TxnType}><DerivedData:{derived}><Tags:{tags}>"
            f"{start_date}{end_date}{availability}{provider}{workflow}"
        )
    else:
        body = (
            f"<SchemeName:{d.SchemeName}><SchemeDescription:{d.SchemeDescription}>"
            f"<AccountCode:{d.AccountCode}><AllowInvokeList:{d.AllowInvokeList}>"
            f"<PrimaryBarcode:{d.PrimaryBarcode}><SchemeIdStart:{d.SchemeIdStart}>"
            f"<SchemeIdString:{d.SchemeIdString}>"
            f"<AgencyData:{agency_data}><Postings:{postings}>"
            f"<ExtractId:{d.ExtractId}><AllowInvokeButton:{d.AllowInvokeButton}>"
            f"<TxnType:{d.TxnType}><DerivedData:{derived}><Tags:{tags}>"
            f"{start_date}{end_date}{availability}{provider}{workflow}"
        )
    lines.append(obj(d.ObjectId, body))
    return lines


# ---------------------------------------------------------------------------
# FieldData  (Consts.cs:43, Form1.cs:411-519)
# ---------------------------------------------------------------------------
def serialize_field_data(d: AgencyRawData, f: FieldDataRawData) -> str:
    summary_screen = f.SummaryScreen

    min_max_length = ""
    if f.MinLength != 0 or f.MaxLength != 0:
        min_max_length = f"<MinLength:{f.MinLength}><MaxLength:{f.MaxLength}>"

    min_max_value = ""
    if f.AttributeName == "Amount":
        if f.MinValue > 0 or d.SchemeName in ("50593", "96005", "96006"):
            min_max_value = f"<MinValue:{f.MinValue}>"
            if f.MaxValue > 0:
                min_max_value += f"<MaxValue:{f.MaxValue}>"
    elif (
        int(d.ObjectId) in PCC_SERVICES
        and f.MinValue > 0
        and f.MaxValue > 0
        and f.Hidden == 0
    ):
        min_max_value = f"<MinValue:{f.MinValue}><MaxValue:{f.MaxValue}>"

    lookup_method = f"<LookupMethod:{f.LookupMethod}>" if f.LookupMethod else ""
    validate_method = f"<ValidateMethod:{f.ValidateMethod}>" if f.ValidateMethod else ""
    initial_value = f"<InitialValue:{f.InitialValue}>" if f.InitialValue else ""
    field_empty = "<FieldEmptyWhenEditing:1>" if f.FieldEmptyWhenEditing else ""
    extra_chars = f"<ExtraCharacters:{f.ExtraCharacters}>" if f.ExtraCharacters else ""

    date_parse_format = ""
    if f.ObjectId in _DATE_PARSE_FORMATS and f.FieldType == "Date":
        date_parse_format = _DATE_PARSE_FORMATS[f.ObjectId]

    # Special Case: 51063 REFNO9 hidden in summary
    if d.ObjectId == "51063" and f.AttributeName == "REFNO9":
        summary_screen = 0

    edit_mask = f"<EditMask:{f.EditMask}>" if f.EditMask else ""
    double_captured = f"<DoubleCaptured:{f.DoubleCaptured}>" if f.DoubleCaptured == 1 else ""

    head = f"<Object:<Path:{_PATH_PREFIX}/FieldData/{f.ObjectId}>><Contents:<Data:"
    body = (
        f"<AttributeName:{f.AttributeName}><FieldType:{f.FieldType}>"
        f"<Caption:{f.Caption}><AllowChange:{f.AllowChange}><Mandatory:{f.Mandatory}>"
        f"<SummaryScreen:{summary_screen}><ReceiptName:{f.ReceiptName}>"
        f"<Hidden:{f.Hidden}><DisplayOrder:{f.DisplayOrder}>"
        f"{initial_value}{min_max_length}{min_max_value}{lookup_method}"
        f"{validate_method}{field_empty}{extra_chars}{date_parse_format}"
        f"{edit_mask}{double_captured}"
    )
    return f"{head}{body}>>"


# ---------------------------------------------------------------------------
# Posting  (Consts.cs:44, Form1.cs:522-531)
# ---------------------------------------------------------------------------
def serialize_posting(p: PostingDataRaw) -> str:
    receipt_items = "".join(f"<ReceiptItem:{ri}>" for ri in p.ReceiptItems)
    return (
        f"<Object:<Path:{_PATH_PREFIX}/PostingData/{p.ObjectId}>><Contents:<Data:"
        f"<Account:{p.Account}><ReceiptItems:{receipt_items}>"
        f"<Sense:{p.Sense}><Attribute:{p.Attribute}>>>"
    )


# ---------------------------------------------------------------------------
# Derived  (Consts.cs:45, Form1.cs:534-554) — NOTE: <Attibute:> typo preserved
# ---------------------------------------------------------------------------
def serialize_derived(dd: DerivedDataRawData) -> str:
    formula = f"<Formula:{dd.Formula}>" if dd.Formula else ""

    if dd.Scope is not None:
        scope_data = (
            f"<$Scope:<$Default:{dd.Scope.WithinBangkokFee}>"
            f"<00:{dd.Scope.WithinBangkokFee}><43:{dd.Scope.OutsideBangkokFee}>>"
        )
        fixed_amount = f"<FixedAmount:{scope_data}>"
    else:
        fixed_amount = f"<FixedAmount:{dd.FixedAmount}>" if dd.FixedAmount else ""

    receipt_name = f"<ReceiptName:{dd.ReceiptName}>" if dd.ReceiptName else ""

    return (
        f"<Object:<Path:{_PATH_PREFIX}/DerivedData/{dd.ObjectId}>><Contents:<Data:"
        f"<Attibute:{dd.Attribute}><SummaryScreen:{dd.SummaryScreen}>"
        f"<IncludeInTxn:{dd.IncludeInTxn}><Caption:{dd.Caption}>"
        f"{formula}{fixed_amount}{receipt_name}>>"
    )


# ---------------------------------------------------------------------------
# Validation  (Consts.cs:48)
# ---------------------------------------------------------------------------
def serialize_validation(method: str) -> str:
    return (
        f"<Object:<Path:{_PATH_PREFIX}/ValidationData/{method}>><Contents:<Data:"
        f"<ValidationMethod:{method}>>>"
    )


# ---------------------------------------------------------------------------
# Lookup  (Consts.cs:49-50)
# ---------------------------------------------------------------------------
_LOOKUP_DEPENDENTS = {
    "semester": ("<DependentFields:YEAR>", "<AdditionalParams:YEAR.Id>"),
    "course1": ("<DependentFields:YEAR,SEMESTER>", "<AdditionalParams:YEAR.Id,SEMESTER.Id>"),
    "course2": ("<DependentFields:YEAR,SEMESTER>", "<AdditionalParams:YEAR.Id,SEMESTER.Id>"),
    "course3": ("<DependentFields:YEAR,SEMESTER>", "<AdditionalParams:YEAR.Id,SEMESTER.Id>"),
    "course4": ("<DependentFields:YEAR,SEMESTER>", "<AdditionalParams:YEAR.Id,SEMESTER.Id>"),
    "coursematerial1": ("<DependentFields:YEAR,SEMESTER,COURSE1>", "<AdditionalParams:YEAR.Id,SEMESTER.Id,COURSE1.Id>"),
    "coursematerial2": ("<DependentFields:YEAR,SEMESTER,COURSE2>", "<AdditionalParams:YEAR.Id,SEMESTER.Id,COURSE2.Id>"),
    "coursematerial3": ("<DependentFields:YEAR,SEMESTER,COURSE3>", "<AdditionalParams:YEAR.Id,SEMESTER.Id,COURSE3.Id>"),
    "coursematerial4": ("<DependentFields:YEAR,SEMESTER,COURSE4>", "<AdditionalParams:YEAR.Id,SEMESTER.Id,COURSE4.Id>"),
    "nationality": ("<DependentFields:REFNO8_lookup>", "<AdditionalParams:REFNO8_lookup.Id>"),
}


def serialize_lookup(name: str, caption: str) -> str:
    dependents = _LOOKUP_DEPENDENTS.get(name.lower())
    if dependents:
        dependent_fields, additional_params = dependents
        return (
            f"<Object:<Path:{_PATH_PREFIX}/LookupData/{name}>><Contents:<Data:"
            f"<LookupMethod:{name}><Caption:{caption}><DisplayMode:DropDown>"
            f"<AllowNone:1><IsDynamic:1>{dependent_fields}{additional_params}>>"
        )
    return (
        f"<Object:<Path:{_PATH_PREFIX}/LookupData/{name}>><Contents:<Data:"
        f"<LookupMethod:{name}><Caption:{caption}><DisplayMode:DropDown><AllowNone:1>>>"
    )


# ---------------------------------------------------------------------------
# Barcode  (Consts.cs:46-47, Form1.cs:559-581)
# ---------------------------------------------------------------------------
def serialize_barcode_details(b) -> str:
    parsing = "".join(f"<ParsingDataId:{pid}>" for pid in b.ParsingRules)
    max_length = f"<MaxLength:{b.MaxLength}>" if b.MaxLength > 0 else ""
    return (
        f"<Object:<Path:{_PATH_PREFIX}/BarcodeDetails/{b.Id}>><Contents:<Data:"
        f"<Prompt:{b.Prompt}><AllowManualEntry:{b.AllowManualEntry}>"
        f"<Required:{b.Required}><ParsingRules:{parsing}>{max_length}>>"
    )


def serialize_barcode_parsing(bpd) -> str:
    length = f"<Length:{bpd.Length}>" if bpd.Length > 0 else ""
    return (
        f"<Object:<Path:{_PATH_PREFIX}/BarcodeParsingData/{bpd.Id}>><Contents:<Data:"
        f"<FieldId:{bpd.FieldId}><Start:{bpd.Start}>{length}>>"
    )
