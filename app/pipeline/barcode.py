"""Barcode pipeline — ported from Helper.cs ProcessBarcodeAndBarcodeParsingData
and ExtractBarcodeDataBySheet (state machine over 6 sheets).

This also runs the two post-passes that mutate field Mandatory/AllowChange
across ALL services:
  - SetNonMandatoryToReadOnlyFields
  - SetMandatoryFieldsAndHideLookupFieldsInSummaryScreen
"""
from __future__ import annotations

from typing import Optional

from app.models.raw import (
    AgencyMasterRawData,
    AgencyRawData,
    BarcodeParsingRawData,
    BarcodeRawData,
    ServiceProviderRawData,
)
from app.pipeline import rules
from app.pipeline.helpers import get_cell_value, to_int
from app.sheets.loaders import _cell, _load_grid

# Sheet order in PayAtPost-SpecBarcode (1-based in C#): BOT-STD, NotBOT-STD,
# ScriptText, Bank@Post, InputData, Sukhothai University มสธ.
_BARCODE_SHEET_INDICES = [0, 1, 2, 3, 4, 5]


def _get_required_from_provider(service_id: int, providers: list[ServiceProviderRawData]) -> str:
    p = next((e for e in providers if to_int(e.ObjectId) == service_id), None)
    if p is not None and p.BarcodeRequired:
        return p.BarcodeRequired
    return "1"


def _extract_barcode_by_sheet(grid, cfg_as, cfg_bd, cfg_bpd,
                              master, agency_data, barcode_data, providers) -> None:
    master_ids = {m.ObjectId for m in master}
    ctr = 0
    service_id = 0
    current_impulse = ""
    is_service_exist = False
    raw_data = BarcodeRawData()
    raw_parsing: list[BarcodeParsingRawData] = []

    def find_agency(sid: int) -> Optional[AgencyRawData]:
        return next((e for e in agency_data if e.SchemeName == str(sid)), None)

    n = len(grid)
    for i in range(cfg_bd["RowNo"], n + 1):
        temp_service_id = _cell(grid, i, cfg_bd["SchemeNameColNo"])
        suffix = _cell(grid, i, cfg_bd["SuffixColNo"])
        fd_name = _cell(grid, i, 6)
        agency_field = _cell(grid, i, 9)
        temp_start_pos = to_int(_cell(grid, i, cfg_bpd["StartColNo"]))

        if "/" in temp_service_id:
            temp_service_id = temp_service_id[:temp_service_id.find("/")]

        # --- ServiceId row ---
        if len(temp_service_id) == 5 or temp_service_id == "1819":
            is_service_exist = temp_service_id in master_ids

            if service_id > 0 and raw_parsing:
                raw_data.ParsingRules = [e.Id for e in raw_parsing]
                raw_data.BCParsingRawData = raw_parsing
                barcode_data.append(raw_data)
                raw_parsing = []
                agency = find_agency(service_id)
                if agency is not None:
                    agency.PrimaryBarcode = raw_data.Id

            if is_service_exist:
                ctr = 1
                service_id = to_int(temp_service_id)
                current_impulse = ""
                bd_id = f"{cfg_bd['IdPrefix']}_{cfg_as['IdPrefix']}{service_id}"
                bd_name = str(service_id)
                max_length = 32 if service_id == 51106 else 33 if service_id == 51107 else 0
                required = _get_required_from_provider(service_id, providers)
                raw_data = BarcodeRawData(
                    AllowManualEntry=1,
                    BCParsingRawData=[],
                    Id=bd_id,
                    MaxLength=max_length,
                    Name=bd_name,
                    ParsingRules=[],
                    Prompt=cfg_bd["Prompt"],
                    Required=to_int(required),
                    CheckDigitName="",
                    ImpulseName="",
                )

        # --- Impulse (SchemeIdString) row ---
        elif len(temp_service_id) > 5 and temp_service_id.isdigit() and len(temp_service_id) < 20:
            if is_service_exist:
                current_impulse = f"{temp_service_id}{suffix}"
                if raw_data.ImpulseName == "":
                    raw_data.ImpulseName = current_impulse
                    agency = find_agency(service_id)
                    if agency is not None:
                        agency.SchemeIdString = current_impulse

        # --- Parsing data row ---
        elif raw_data.ImpulseName == current_impulse and len(suffix) > 0:
            if is_service_exist and temp_start_pos > 0:
                temp_agency = find_agency(service_id)
                if temp_agency is None:
                    continue
                temp_field = None
                if agency_field:
                    af = "AcctNo" if agency_field == "REFNO3" else "Amount" if agency_field == "AMT" else agency_field
                    temp_field = next((f for f in temp_agency.FieldData if f.AttributeName == af), None)
                elif fd_name:
                    temp_field = next((f for f in temp_agency.FieldData if f.AttributeName == fd_name), None)

                if temp_field is None:
                    continue

                attrib_name = temp_field.AttributeName
                attrib_name = "REFNO3" if attrib_name == "AcctNo" else "AMT" if attrib_name == "Amount" else attrib_name

                # BRCDE/REFNO3 read-only logic
                if (attrib_name in ("BRCDE", "REFNO3")) and service_id not in rules.ALLOW_CHANGE_REFNO3:
                    agency = find_agency(service_id)
                    if agency is not None:
                        field = next((f for f in agency.FieldData if f.AttributeName == temp_field.AttributeName), None)
                        if field is not None:
                            if not field.ValidateMethod:
                                if agency.SchemeName != "51020":
                                    field.AllowChange = 0
                            else:
                                field.AllowChange = 1

                field_id = f"{cfg_as['IdPrefix']}{service_id}_{attrib_name}"
                if not any(e.FieldId == field_id for e in raw_parsing):
                    start = 2 if temp_start_pos == 1 else temp_start_pos
                    if temp_start_pos == 1 and service_id in rules.NO_PIPE_SERVICE_IDS:
                        start = temp_start_pos
                    end = to_int(_cell(grid, i, cfg_bpd["LengthColNo"]))
                    length = (end - start) + 1 if end > 0 else 0
                    parse_id = f"{cfg_as['IdPrefix']}{raw_data.Name}_{cfg_bpd['IdPrefix']}{ctr:02d}"
                    ctr += 1
                    raw_parsing.append(BarcodeParsingRawData(
                        FieldId=field_id, Id=parse_id, Length=length,
                        Start=start, Suffix=to_int(suffix),
                    ))
                    temp_field.MinLength = length
                    temp_field.MaxLength = length
                    if temp_field.AttributeName == "Amount":
                        temp_field.FieldEmptyWhenEditing = False

    # tail
    if is_service_exist and raw_parsing:
        raw_data.ParsingRules = [e.Id for e in raw_parsing]
        raw_data.BCParsingRawData = raw_parsing
        barcode_data.append(raw_data)
        agency = find_agency(service_id)
        if agency is not None:
            agency.PrimaryBarcode = raw_data.Id


def _set_non_mandatory_to_readonly(agency_data) -> None:
    """Helper.cs:1041 SetNonMandatoryToReadOnlyFields."""
    for agency in agency_data:
        for field in agency.FieldData:
            if (not field.InitialValue and field.MinLength == 0
                    and field.MaxLength == 0 and field.AllowChange == 0):
                field.Mandatory = 0


def _set_mandatory_and_hide_lookups(agency_data) -> None:
    """Helper.cs:1012 SetMandatoryFieldsAndHideLookupFieldsInSummaryScreen."""
    all_fields = [f for a in agency_data for f in a.FieldData]
    for object_id in rules.FIELDS_TO_SET_AS_MANDATORY:
        field = next((f for f in all_fields if f.ObjectId.lower() == object_id.lower()), None)
        if field is not None:
            field.Mandatory = 1
    for object_id in rules.LOOKUP_FIELDS_TO_HIDE_IN_SUMMARY_SCREEN:
        field = next((f for f in all_fields if f.ObjectId.lower() == object_id.lower()), None)
        if field is not None:
            field.SummaryScreen = 0
            if field.ObjectId.lower() in ("52047_refno8_lookup", "50492_refno10_lookup"):
                field.Mandatory = 1


def process_barcode(path: str, cfg_as: dict, cfg_bd: dict, cfg_bpd: dict,
                    master: list[AgencyMasterRawData], agency_data: list[AgencyRawData],
                    providers: list[ServiceProviderRawData]) -> list[BarcodeRawData]:
    barcode_data: list[BarcodeRawData] = []
    for sheet_index in _BARCODE_SHEET_INDICES:
        grid = _load_grid(path, sheet_index)
        _extract_barcode_by_sheet(grid, cfg_as, cfg_bd, cfg_bpd,
                                  master, agency_data, barcode_data, providers)
    _set_non_mandatory_to_readonly(agency_data)
    _set_mandatory_and_hide_lookups(agency_data)
    return barcode_data
