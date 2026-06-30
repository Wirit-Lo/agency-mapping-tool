"""Agency + Field builder and the 18-step enrichment pipeline.

Ported from Helper.cs:
  - ProcessAgencyAndFieldData (build agency scheme + field rows)
  - the enrichment steps it calls, in the SAME order (critical).

Barcode pipeline is handled separately in barcode.py.
"""
from __future__ import annotations

from typing import Any, Optional

from app.models.raw import (
    AgencyMasterRawData,
    AgencyRawData,
    AgentRawData,
    ConfigReceiptRawData,
    DefaultValueRawData,
    DerivedDataRawData,
    DerivedDataRequirementsRawData,
    DropdownValueRawData,
    FieldDataRawData,
    PostingDataRaw,
    ServiceProviderRawData,
    ValidateRawData,
)
from app.pipeline import rules
from app.pipeline.helpers import get_cell_value, get_mapped_field_type, get_attribute_name, to_int
from app.sheets.loaders import _cell, _load_grid

_EXTRA_CHARS = "@.-'/&{space}"


# ---------------------------------------------------------------------------
# Default generators (Helper.cs:2874-2988)
# ---------------------------------------------------------------------------
def _generate_default_field_data(agent_code: int, agent_name: str,
                                  agency_code: str, agency_name: str) -> list[FieldDataRawData]:
    return [
        FieldDataRawData(
            ObjectId=f"{agency_code}_AgentCode", AttributeName="AgentCode",
            FieldType="Alphanumeric", Hidden=1, DisplayOrder=999,
            InitialValue=str(agent_code), SummaryScreen=0,
        ),
        FieldDataRawData(
            ObjectId=f"{agency_code}_Agent", AttributeName="Agent",
            FieldType="Alphanumeric", Caption=str(agent_code), Hidden=1,
            DisplayOrder=999, ReceiptName=str(agent_code),
            InitialValue=agent_name, SummaryScreen=0,
        ),
        FieldDataRawData(
            ObjectId=f"{agency_code}_Agency", AttributeName="Agency",
            FieldType="Alphanumeric", Caption=agency_code, Hidden=1,
            DisplayOrder=999, ReceiptName=agency_code,
            InitialValue=agency_name, SummaryScreen=0,
        ),
    ]


def _generate_default_posting_data(object_id: str, scheme_name: str,
                                   master: list[AgencyMasterRawData]) -> list[PostingDataRaw]:
    am = next((x for x in master if x.ObjectId == object_id), None)
    sense = "Debit" if int(object_id) in rules.WITHDRAWAL_SERVICES else "Credit"
    result = [PostingDataRaw(
        ObjectId=f"Post_{scheme_name}", Account=scheme_name,
        ReceiptItems=["Agent", "Agency"], Sense=sense, Attribute="Amount",
    )]
    if am is not None and (to_int(am.Fee) > 0 or scheme_name == "50982"):
        result.append(PostingDataRaw(
            ObjectId=f"Post_{scheme_name}_Fee", Account="BSFEE",
            ReceiptItems=[], Sense="Credit", Attribute="Fee",
        ))
    return result


def _generate_default_derived_data(object_id: str, scheme_name: str,
                                   master: list[AgencyMasterRawData]) -> list[DerivedDataRawData]:
    am = next((x for x in master if x.ObjectId == object_id), None)
    result: list[DerivedDataRawData] = []
    if am is None:
        return result
    has_fee = am.Fee is not None and (to_int(am.Fee) > 0 or scheme_name == "50982")
    result.append(DerivedDataRawData(
        ObjectId=f"{scheme_name}_Total", Attribute="Total",
        Formula="Fee+Amount" if has_fee else "Amount",
        FixedAmount="", SummaryScreen=1, IncludeInTxn=1, ReceiptName="",
        Caption="THP_Agency_TotalDue_Caption",
    ))
    if has_fee:
        result.append(DerivedDataRawData(
            ObjectId=f"{object_id}_Fee", Attribute="Fee", Formula="",
            FixedAmount=am.Fee if to_int(am.Fee) > 0 else "0",
            SummaryScreen=1, IncludeInTxn=1,
            ReceiptName="THP_Agency_Fee_Caption", Caption="THP_Agency_Fee_Caption",
            Scope=am.Scope,
        ))
    return result


def _get_transaction_type_from_fee(object_id: str, master: list[AgencyMasterRawData]) -> str:
    s = next((x for x in master if x.ObjectId == object_id), None)
    return s.TransactionType if s else ""


# ---------------------------------------------------------------------------
# ProcessAgencyAndFieldData (Helper.cs:691)
# ---------------------------------------------------------------------------
def build_agency_and_field_data(
    path: str, cfg_as: dict, cfg_fd: dict,
    master: list[AgencyMasterRawData],
) -> list[AgencyRawData]:
    grid = _load_grid(path, cfg_as["SheetNo"] - 1)
    master_ids = {m.ObjectId for m in master}
    agency_data: list[AgencyRawData] = []

    agent_code = 0
    agent_name = ""
    service_id = 0
    is_service_exist = False
    current: Optional[AgencyRawData] = None
    raw_fields: list[FieldDataRawData] = []

    n = len(grid)
    for i in range(cfg_as["RowNo"], n + 1):
        temp_agent = to_int(_cell(grid, i, 1))
        if temp_agent > 0:
            agent_code = temp_agent
            agent_name = _cell(grid, i, 2)
        if agent_code <= 0:
            continue

        temp_scheme_name = _cell(grid, i, cfg_as["SchemeNameColNo"])
        if "/" in temp_scheme_name:
            temp_scheme_name = temp_scheme_name[:temp_scheme_name.find("/")]

        if temp_scheme_name.isdigit():
            temp_service_id = int(temp_scheme_name)
            if len(str(temp_service_id)) == 5 or temp_service_id == 1819:
                # NEW SERVICE boundary
                agency = next((e for e in master if e.ObjectId == str(temp_service_id)), None)
                is_service_exist = agency is not None

                if service_id > 0 and current is not None:
                    if raw_fields:
                        current.FieldData.extend(raw_fields)
                        agency_data.append(current)
                        raw_fields = []

                if is_service_exist:
                    service_id = temp_service_id
                    as_id = f"{cfg_as['IdPrefix']}{service_id}"
                    as_name = str(service_id)
                    description = _cell(grid, i, cfg_as["SchemeDescriptionColNo"])
                    scheme_id_start = 1 if service_id in rules.NO_PIPE_SERVICE_IDS else 2
                    account_code = "51106" if as_id == "51107" else as_id
                    availability = (
                        "Zone132" if int(as_id) in rules.AVAILABILITY_SET_132
                        else "Zone164" if int(as_id) in rules.AVAILABILITY_SET_164
                        else "Zone486" if int(as_id) in rules.AVAILABILITY_SET_486
                        else None
                    )
                    current = AgencyRawData(
                        AgentCode=str(agent_code), AgentName=agent_name,
                        AccountCode=account_code, ObjectId=as_id, SchemeName=as_name,
                        SchemeDescription=description, AllowInvokeList=1,
                        PrimaryBarcode="", SchemeIdStart=scheme_id_start,
                        SchemeIdString="", ExtractId=cfg_as["ExtractId"],
                        AllowInvokeButton=1, TxnType=cfg_as["TransactionType"],
                        TransactionType=_get_transaction_type_from_fee(as_id, master),
                        Tags=[],
                        FieldData=_generate_default_field_data(agent_code, agent_name, as_name, description),
                        PostingData=_generate_default_posting_data(as_name, as_id, master),
                        DerivedData=_generate_default_derived_data(as_name, as_id, master),
                        StartDate=agency.StartDate if agency else None,
                        EndDate=agency.EndDate if agency else None,
                        AvailabilitySet=availability,
                    )
                else:
                    service_id = 0
                    current = None
            else:
                # FIELD ROW (4xxx etc.)
                if is_service_exist and current is not None:
                    if temp_service_id != 0 and service_id != temp_service_id:
                        _append_field(grid, i, cfg_fd, current, raw_fields, service_id, temp_service_id)

    # tail
    if is_service_exist and service_id > 0 and current is not None and raw_fields:
        current.FieldData.extend(raw_fields)
        agency_data.append(current)

    return agency_data


def _append_field(grid, i, cfg_fd, current: AgencyRawData,
                  raw_fields: list[FieldDataRawData], service_id: int, temp_service_id: int) -> None:
    field_type = get_mapped_field_type(_cell(grid, i, cfg_fd["FieldTypeColNo"]))
    if not field_type or field_type.lower() == "button":
        return

    attribute_name = get_attribute_name(field_type, _cell(grid, i, cfg_fd["AttributeNameColNo"]))
    fd_id = get_attribute_name(field_type, _cell(grid, i, cfg_fd["IdColNo"]))
    fd_name = _cell(grid, i, 6)
    caption = _cell(grid, i, cfg_fd["CaptionColNo"])
    read_only = _cell(grid, i, cfg_fd["AllowChangeColNo"])
    visible = _cell(grid, i, cfg_fd["HiddenColNo"]) or "1"
    extra_characters = _EXTRA_CHARS
    mandatory = "0"
    receipt_name = caption
    suffix = temp_service_id
    dropdown_id = _cell(grid, i, 10)
    min_length = to_int(_cell(grid, i, 11))
    max_length = to_int(_cell(grid, i, 12))
    min_value = 0
    max_value = 0
    edit_mask = ""
    hide_in_summary = _cell(grid, i, 13)
    double_captured = to_int(_cell(grid, i, 14))

    is_tbc = "TBC_Field_" in attribute_name
    if is_tbc and visible != "1":
        return

    lookup_method: Optional[str] = None
    if is_tbc:
        attribute_name = fd_name
        fd_id = fd_name

    # REFNO2 filter (allow for PCC)
    if attribute_name == "REFNO2" and service_id not in rules.PCC_SERVICES:
        return

    if "editmask" in field_type.lower():
        ch = "9" if field_type.lower() == "editmask" else "2"
        edit_mask = ch.ljust(max_length, "9")
        field_type = "Alphanumeric"

    if attribute_name == "AMT":
        attribute_name = "Amount"; read_only = "0"; visible = "1"; mandatory = "1"
    elif attribute_name == "REFNO3":
        attribute_name = "AcctNo"; read_only = "0"; visible = "1"; mandatory = "1"
    elif attribute_name == "BRCDE":
        read_only = "1"

    if field_type == "Button":
        visible = "0"
    elif field_type == "ComboBox":
        field_type = "Alphanumeric"
        lookup_method = "SampleLookup"

    if current.ObjectId in ("30078", "30079"):
        if attribute_name == "Amount":
            read_only = "1"; visible = "0"; mandatory = "1"
        elif attribute_name == "AcctNo" and current.ObjectId == "30078":
            read_only = "0"; visible = "0"; mandatory = "1"

    if attribute_name in ("COURSE1", "COURSEMATERIAL1"):
        mandatory = "1"

    display_order = 999 if attribute_name == "DEGREE" else (suffix if visible == "1" else 999)

    raw_fields.append(FieldDataRawData(
        ObjectId=f"{current.ObjectId}_{fd_id}",
        Suffix=suffix,
        AllowChange=0 if read_only == "1" else 1,
        AttributeName=attribute_name,
        Caption=caption,
        FieldType=field_type or "",
        Hidden=0 if visible == "1" else 1,
        Mandatory=1 if mandatory == "1" else 0,
        ReceiptName=receipt_name,
        DisplayOrder=display_order,
        LookupMethod=lookup_method,
        ValidateMethod="",
        MinValue=min_value, MaxValue=max_value,
        FD_NAME=fd_name,
        FieldEmptyWhenEditing=(attribute_name == "Amount"),
        ExtraCharacters=extra_characters if field_type == "Alphanumeric" else "",
        SERV_DATA_ID=dropdown_id or None,
        MinLength=min_length, MaxLength=max_length,
        EditMask=edit_mask,
        HideInSummary=hide_in_summary,
        DoubleCaptured=double_captured,
    ))


# ===========================================================================
# Enrichment steps (called in order — Helper.cs:989-1005)
# ===========================================================================
_NOT_IMPLEMENTED_VALIDATE = {
    "CheckDupField", "FormatZero", "RevenueControlCode", "SetDateINF",
    "SetValueSubStr", "TrePetchRef2New", "CallSqlServP", "ChkLocalAmt", "EduList",
    "ChkDupBar", "LoadComboSP", "NextOrBackTab", "ServDataCombo", "SPMsgBoxOk",
}


def get_validate_method_from_validation_data(agency_data, validation_data):
    for v in validation_data:
        if v.ValidateMethod.strip() in _NOT_IMPLEMENTED_VALIDATE:
            continue
        agency = next((a for a in agency_data if a.SchemeName == v.ObjectId), None)
        if agency is None:
            continue
        field = next((f for f in agency.FieldData if f.AttributeName == v.ReferenceField), None)
        if field is not None:
            field.ValidateMethod = v.ValidateMethod
            field.Mandatory = 1
            field.AllowChange = 1


def get_txntype_tag_minmax_from_fee(agency_data, master):
    for agency in agency_data:
        min_value = 100
        max_value = 5000000
        am = next((e for e in master if e.ObjectId == agency.SchemeName), None)
        if am is not None:
            category = am.ServiceCategory if am.ServiceCategory else "Others"
            agency.Tags.append(category)
            agency.FieldData.insert(3, FieldDataRawData(
                ObjectId=f"{agency.SchemeName}_Category", AttributeName="Category",
                FieldType="Alphanumeric", Hidden=1, DisplayOrder=999,
                InitialValue=category, SummaryScreen=0,
            ))
            if agency.ObjectId in ("50295", "50961"):
                agency.TxnType = rules.TransactionTypes.AgencySaleOfflineNonReversible
            elif int(agency.ObjectId) in rules.WITHDRAWAL_SERVICES:
                agency.TxnType = rules.TransactionTypes.AgencyWithdrawal
            else:
                agency.TxnType = (
                    rules.TransactionTypes.AgencySaleOnline
                    if "online" in am.TransactionType.lower()
                    else rules.TransactionTypes.AgencySaleOffline
                )
        else:
            agency.Tags.append("Others")
            agency.FieldData.insert(3, FieldDataRawData(
                ObjectId=f"{agency.SchemeName}_Category", AttributeName="Category",
                FieldType="Alphanumeric", Hidden=1, DisplayOrder=999,
                InitialValue="Others",
            ))

        field = next((e for e in agency.FieldData if e.AttributeName == "Amount"), None)
        if field is not None:
            if am is not None:
                if am.MinAmount.isdigit():
                    mn = int(am.MinAmount)
                    min_value = min_value if mn < 1 else mn * 100
                if am.MaxAmount.lstrip("-").isdigit():
                    mx = int(am.MaxAmount)
                    max_value = max_value if (mx <= 0 or mx > 50000) else mx * 100
            field.MinValue = min_value
            field.MaxValue = max_value
            if agency.SchemeName in ("50593", "96005", "96006"):
                field.MinValue = 0


def get_receipt_configs_from_config_receipt(agency_data, config_receipt_data):
    for config in config_receipt_data:
        details = sorted(
            (d for d in config.Details if d.FD_NAME),
            key=lambda o: o.LineNumber,
        )
        if not details:
            continue
        agency = next((e for e in agency_data if e.ObjectId == config.ObjectId), None)
        if agency is None:
            continue
        posting = next((p for p in agency.PostingData if p.Attribute == "Amount"), None)
        for detail in details:
            field = next((f for f in agency.FieldData if f.FD_NAME == detail.FD_NAME), None)
            if field is not None:
                field.Mandatory = 1
                if posting is not None:
                    posting.ReceiptItems.append(field.AttributeName)


def get_receipt_configs_from_agent_master(agency_data, agent_master):
    for service_id in rules.REQUIRED_AGENT_DATA_SERVICE_IDS:
        agency = next((e for e in agency_data if e.ObjectId == str(service_id)), None)
        if agency is None:
            continue
        agent = next((e for e in agent_master if e.AgentCode == agency.AgentCode), None)
        if agent is None:
            continue
        agency.FieldData.append(FieldDataRawData(
            ObjectId=f"{service_id}_TaxNumber", AttributeName="TaxNumber",
            Caption="TAX ID", FieldType="Alphanumeric", Hidden=1, Mandatory=0,
            ReceiptName="TAX ID", DisplayOrder=999, InitialValue=agent.TaxNumber,
            AllowChange=0,
        ))
        agency.FieldData.append(FieldDataRawData(
            ObjectId=f"{service_id}_Address", AttributeName="Address",
            Caption="", FieldType="Alphanumeric", Hidden=1, Mandatory=0,
            ReceiptName="", DisplayOrder=999, InitialValue=agent.BillAddress,
            AllowChange=0,
        ))
        posting = next((p for p in agency.PostingData if p.Attribute == "Amount"), None)
        if posting is not None:
            posting.ReceiptItems.insert(1, "TaxNumber")
            posting.ReceiptItems.insert(2, "Address")


def get_field_default_values(agency_data, default_value_data):
    for dv in default_value_data:
        agency = next((e for e in agency_data if e.SchemeName == dv.ObjectId), None)
        if agency is None:
            continue
        attr = dv.ReferenceField
        if attr == "REFNO3":
            attr = "AcctNo"
        if attr == "AMT":
            attr = "Amount"
        field = next((e for e in agency.FieldData if e.AttributeName == attr), None)
        if field is None:
            continue
        if field.AttributeName.lower() == "amount":
            field.InitialValue = str(int(dv.DefaultValue))
            field.FieldEmptyWhenEditing = False
        else:
            field.InitialValue = dv.DefaultValue


def get_lookup_method_values(agency_data, dropdown_value_data):
    agency_with_lookup = [
        a for a in agency_data
        if any(f.LookupMethod == "SampleLookup" for f in a.FieldData)
    ]
    for agency in agency_with_lookup:
        for field in (f for f in agency.FieldData if f.LookupMethod == "SampleLookup"):
            dv = next((e for e in dropdown_value_data
                       if e.ObjectId == agency.ObjectId and e.FieldName == field.FD_NAME), None)
            if dv is not None:
                field.LookupMethod = dv.DropdownName

        dropdown_derived = [
            e for e in dropdown_value_data
            if e.ObjectId == agency.ObjectId and e.DerivedData
        ]
        for derived in dropdown_derived:
            derived_field = derived.DerivedData
            source_field = derived.SourceField if derived.SourceField else derived.FieldName
            fn = next((e for e in agency.FieldData if e.FD_NAME.lower() == derived.FieldName.lower()), None)
            sf = next((e for e in agency.FieldData if e.FD_NAME.lower() == source_field.lower()), None)
            if fn is None or sf is None:
                continue
            df = derived_field.lower()
            if df in ("value_name", "course_name"):
                formula = f"{sf.AttributeName}.Description"
            elif df in ("value_id", "course_code"):
                formula = f"{sf.AttributeName}.Id"
            elif df == "book_up":
                formula = f"{sf.AttributeName}.AdditionalData[Bookup]"
            elif df == "amount":
                formula = f"Math.Ceiling(Math.ToNumber({sf.AttributeName}.AdditionalData[Amount]))"
            else:
                formula = ""
            if formula:
                agency.DerivedData.append(DerivedDataRawData(
                    ObjectId=f"{agency.ObjectId}_{fn.AttributeName}",
                    Attribute=fn.AttributeName, FixedAmount="", Formula=formula,
                    SummaryScreen=1, IncludeInTxn=1, ReceiptName="",
                    Caption=derived.DropdownCaption,
                ))


def get_provider_name(agency_data, service_provider_data):
    for provider in service_provider_data:
        agency = next((e for e in agency_data if e.ObjectId == provider.ObjectId), None)
        if agency is not None:
            agency.Type = provider.Type
            agency.AgencyProviderName = provider.ProviderName
            agency.WorkflowId = provider.WorkflowId


def _create_derived_data(agency: AgencyRawData, attribute: str, formula: str) -> Optional[DerivedDataRawData]:
    base_attr = attribute.replace("Derived", "")
    field = next((e for e in agency.FieldData if e.AttributeName.lower() == base_attr.lower()), None)
    if field is None:
        return None
    return DerivedDataRawData(
        ObjectId=f"{agency.ObjectId}_{field.AttributeName}",
        Attribute=attribute, Formula=formula, SummaryScreen=1,
        IncludeInTxn=0 if "Derived" in attribute else 1,
        Caption=field.Caption,
    )


def generate_custom_derived_data(agency_data, requirements):
    for req in requirements:
        agency = next((e for e in agency_data if e.ObjectId == req.ObjectId), None)
        if agency is None:
            continue
        if any(e.Attribute == req.Attribute for e in agency.DerivedData):
            continue
        dd = _create_derived_data(agency, req.Attribute, req.Formula)
        if dd is not None:
            agency.DerivedData.append(dd)


def hide_amount_fields_due_to_derived_data(agency_data):
    for object_id in rules.HIDE_AMOUNT_FIELDS_DUE_TO_DERIVED_DATA:
        agency = next((e for e in agency_data if e.ObjectId == str(object_id)), None)
        if agency is None:
            continue
        field = next((e for e in agency.FieldData if e.AttributeName.lower() == "amount"), None)
        if field is not None:
            field.AllowChange = 0; field.Mandatory = 0; field.Hidden = 1
            field.SummaryScreen = 0; field.DisplayOrder = 999
            if object_id not in rules.HIDDEN_FIELD_SERVICES_WITH_MINMAX_AMOUNTS:
                field.MinValue = 0


def update_total_derived_and_summary(agency_data):
    for agency in agency_data:
        pw = next((e for e in agency.FieldData if e.FieldType.lower() == "passwordfield"), None)
        if pw is not None:
            pw.AllowChange = 0; pw.Mandatory = 0; pw.Hidden = 1
            pw.SummaryScreen = 0; pw.DisplayOrder = 999
        for derived in agency.DerivedData:
            field = next((e for e in agency.FieldData if e.AttributeName.lower() == derived.Attribute.lower()), None)
            if field is not None:
                field.SummaryScreen = 0
            if derived.Attribute.lower() == "amount":
                total = next((e for e in agency.DerivedData if e.Attribute.lower() == "total"), None)
                if total is not None:
                    total.Formula = total.Formula.replace("Amount", f"({derived.Formula})")


def update_field_derived_summary_from_hide(agency_data):
    for agency in agency_data:
        for field in (e for e in agency.FieldData if e.HideInSummary):
            derived = next((e for e in agency.DerivedData if e.ObjectId == field.ObjectId), None)
            hide_val = int(field.HideInSummary)
            if derived is not None:
                if hide_val == 1:
                    derived.SummaryScreen = 0
                elif hide_val == 0:
                    field.SummaryScreen = 0
                    derived.SummaryScreen = 1
            else:
                if hide_val == 1:
                    field.SummaryScreen = 0
                elif hide_val == 0:
                    field.SummaryScreen = 1


def update_pcc_minmax(agency_data):
    for service in agency_data:
        if int(service.ObjectId) not in rules.PCC_SERVICES:
            continue
        for field in service.FieldData:
            if (field.FieldType.lower() == "currency" and field.Hidden == 0
                    and field.MinLength > 0 and field.MaxLength > 0):
                field.MinValue = field.MinLength * 100
                field.MaxValue = field.MaxLength * 100
                field.MinLength = 0
                field.MaxLength = 0
            else:
                field.MinValue = 0
                field.MaxValue = 0


_MANDATORY_LOOKUPS = {"RegistrationType", "RegistrationFrequency", "Year", "Semester",
                      "RegistrationFee", "MethodOfPayment"}
_MANDATORY_LOOKUP_EXCEPTIONS = {
    "50475_REFNO18_Lookup", "50475_REFNO21_Lookup", "50475_REFNO23_Lookup",
    "50477_REFNO16_Lookup", "50658_REFNO16_Lookup", "50658_REFNO17_Lookup",
}


def set_mandatory_fields_for_lookups(agency_data):
    for agency in agency_data:
        for field in agency.FieldData:
            if field.LookupMethod and field.Mandatory == 0:
                if field.LookupMethod in _MANDATORY_LOOKUPS:
                    field.Mandatory = 1
                if (field.LookupMethod == "RegistrationFrequency"
                        and field.ObjectId in _MANDATORY_LOOKUP_EXCEPTIONS):
                    field.Mandatory = 0


def set_mandatory_fields(agency_data):
    agency = next((e for e in agency_data if e.ObjectId == "52047"), None)
    if agency is not None:
        for attr in ("REFNO10", "REFNO11", "REFNO13", "REFNO7", "REFNO8_lookup"):
            f = next((e for e in agency.FieldData if e.AttributeName == attr), None)
            if f is not None:
                f.Mandatory = 1
    agency = next((e for e in agency_data if e.ObjectId == "90021"), None)
    if agency is not None:
        for attr in ("REFNO4", "REFNO5"):
            f = next((e for e in agency.FieldData if e.AttributeName == attr), None)
            if f is not None:
                f.Mandatory = 1
        for attr in ("BRCDE", "REFNO3"):
            f = next((e for e in agency.FieldData if e.AttributeName == attr), None)
            if f is not None:
                f.Mandatory = 0


def set_fields_in_summary_screen(agency_data):
    agency = next((e for e in agency_data if e.ObjectId == "52059"), None)
    if agency is not None:
        for attr in ("REFNO6", "REFNO7", "REFNO8", "REFNO9", "REFNO10", "VAT"):
            f = next((e for e in agency.FieldData if e.AttributeName == attr), None)
            if f is not None:
                f.SummaryScreen = 1


def set_withdrawal_minmax(agency_data):
    limits = {
        "93004": (100, 500000),
        "93005": (100, 500000),
        "93007": (100, 5000000),
    }
    for sid, (mn, mx) in limits.items():
        agency = next((e for e in agency_data if e.ObjectId == sid), None)
        if agency is not None:
            f = next((e for e in agency.FieldData if e.AttributeName.lower() == "amount"), None)
            if f is not None:
                f.MinValue = mn
                f.MaxValue = mx


def hide_bankatpost_refno3(agency_data):
    for service_id in rules.SERVICES_WITH_HIDDEN_REFNO3:
        agency = next((e for e in agency_data if e.ObjectId == str(service_id)), None)
        if agency is None:
            continue
        f = next((e for e in agency.FieldData if e.AttributeName.lower() == "acctno"), None)
        if f is not None:
            f.AllowChange = 0; f.Mandatory = 0; f.Hidden = 1
            f.SummaryScreen = 0; f.DisplayOrder = 999
        f = next((e for e in agency.FieldData if e.AttributeName.lower() == "brcde"), None)
        if f is not None:
            f.AllowChange = 1; f.Mandatory = 1; f.Hidden = 0; f.SummaryScreen = 1


def run_enrichment(agency_data, master, validation_data, agent_master,
                   config_receipt_data, default_value_data, dropdown_value_data,
                   service_provider_data, requirements):
    """Runs all 18 steps in the exact Helper.cs order (989-1005)."""
    get_validate_method_from_validation_data(agency_data, validation_data)
    get_txntype_tag_minmax_from_fee(agency_data, master)
    get_receipt_configs_from_config_receipt(agency_data, config_receipt_data)
    get_receipt_configs_from_agent_master(agency_data, agent_master)
    get_field_default_values(agency_data, default_value_data)
    get_lookup_method_values(agency_data, dropdown_value_data)
    get_provider_name(agency_data, service_provider_data)
    generate_custom_derived_data(agency_data, requirements)
    hide_amount_fields_due_to_derived_data(agency_data)
    update_total_derived_and_summary(agency_data)
    update_field_derived_summary_from_hide(agency_data)
    update_pcc_minmax(agency_data)
    set_mandatory_fields_for_lookups(agency_data)
    set_mandatory_fields(agency_data)
    set_fields_in_summary_screen(agency_data)
    set_withdrawal_minmax(agency_data)
    hide_bankatpost_refno3(agency_data)
    return agency_data
