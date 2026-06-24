"""Orchestrator — load → enrich → serialize → write 7 non-barcode WebObject files.

Barcode files (BarcodeDetails, BarcodeParsingData) are produced by a separate
module once ported; this runner covers Scheme/FieldData/Posting/Derived/
Validation/Lookup.
"""
from __future__ import annotations

import json
import os
from typing import Optional

from app.pipeline import enrich
from app.pipeline import barcode as barcode_mod
from app.sheets import loaders
from app.serialize import webobjects as wo


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8-sig") as fh:
        return json.load(fh)


def build_agency_data(source_dir: str, config: dict):
    """Load all sheets and run the full non-barcode pipeline."""
    def sp(name: str) -> str:
        return os.path.join(source_dir, name)

    master = loaders.load_agency_master(
        sp(config["DerivedData"]["SourceFileName"]), config["DerivedData"]
    )
    master_ids = {m.ObjectId for m in master}
    validation = loaders.load_validation(
        sp(config["ValidationData"]["SourceFileName"]), config["ValidationData"], master_ids
    )
    agent_master = loaders.load_agent_master(sp("AgentMasterData.xlsx"))
    config_receipt = loaders.load_config_receipt(sp("PayAtPost-ConfigReceipt_V1.0.xlsx"))
    default_values = loaders.load_default_values(sp("PayAtPost-DefaultValue_V1.0.xlsx"))
    dropdown_values = loaders.load_dropdown_values(sp("PayAtPost-DropdownValue.xlsx"))
    service_providers = loaders.load_service_providers(sp("AgencyServiceProviders.xlsx"))
    requirements = loaders.load_derived_data_requirements(sp("AgencyDerivedDataRequirements.xlsx"))

    agency_data = enrich.build_agency_and_field_data(
        sp(config["AgencyScheme"]["SourceFileName"]),
        config["AgencyScheme"], config["FieldData"], master,
    )
    enrich.run_enrichment(
        agency_data, master, validation, agent_master, config_receipt,
        default_values, dropdown_values, service_providers, requirements,
    )
    barcode_data = barcode_mod.process_barcode(
        sp(config["BarcodeDetail"]["SourceFileName"]),
        config["AgencyScheme"], config["BarcodeDetail"], config["BarcodeParsingData"],
        master, agency_data, service_providers,
    )
    return agency_data, validation, dropdown_values, barcode_data


def serialize_all(agency_data, validation, dropdown_values, barcode_data) -> dict[str, str]:
    """Return {output_filename: file_content} for the 7 non-barcode files."""
    schemes, fields, postings, deriveds = [], [], [], []
    for d in agency_data:
        schemes.extend(wo.serialize_agency_scheme(d))
        for f in d.FieldData:
            fields.append(wo.serialize_field_data(d, f))
        for p in d.PostingData:
            postings.append(wo.serialize_posting(p))
        for dd in d.DerivedData:
            if dd.ObjectId:
                deriveds.append(wo.serialize_derived(dd))

    # Validation — distinct method names, in first-seen order
    seen, validations = set(), []
    for v in validation:
        if v.ValidateMethod not in seen:
            seen.add(v.ValidateMethod)
            validations.append(wo.serialize_validation(v.ValidateMethod))

    # Lookup — distinct DropdownName, first-seen order
    seen_lk, lookups = set(), []
    for lk in dropdown_values:
        if lk.DropdownName not in seen_lk:
            seen_lk.add(lk.DropdownName)
            lookups.append(wo.serialize_lookup(lk.DropdownName, lk.DropdownCaption))

    bc_details, bc_parsing = [], []
    for b in barcode_data:
        for pd in b.BCParsingRawData:
            bc_parsing.append(wo.serialize_barcode_parsing(pd))
        bc_details.append(wo.serialize_barcode_details(b))

    return {
        "RA_AgencyScheme.txt": wo.wrap_file("AgencyScheme", schemes),
        "RA_AgencyFieldData.txt": wo.wrap_file("FieldData", fields),
        "RA_AgencyPostingData.txt": wo.wrap_file("PostingData", postings),
        "RA_AgencyDerivedData.txt": wo.wrap_file("DerivedData", deriveds),
        "RA_AgencyValidationData.txt": wo.wrap_file("ValidationData", validations),
        "RA_AgencyLookup.txt": wo.wrap_file("LookupData", lookups),
        "RA_AgencyBarcodeDetails.txt": wo.wrap_file("BarcodeDetails", bc_details),
        "RA_AgencyBarcodeParsingData.txt": wo.wrap_file("BarcodeParsingData", bc_parsing),
    }


def generate(source_dir: str, config_path: str, out_dir: Optional[str] = None,
             use_google_sheets: bool = False,
             service_account_file: Optional[str] = None) -> dict[str, str]:
    """Generate all output files.

    By default reads local .xlsx from source_dir. Set use_google_sheets=True
    (with a service_account_file) to read live from Google Sheets instead;
    the pipeline is identical either way.
    """
    if use_google_sheets:
        from app.sheets.google_sheets import SheetsGrids
        from app.sheets import loaders
        grids = SheetsGrids(service_account_file=service_account_file)
        loaders.set_grid_provider(lambda path, idx=0: grids.load(os.path.basename(path), idx))

    config = load_config(config_path)
    agency_data, validation, dropdown_values, barcode_data = build_agency_data(source_dir, config)
    outputs = serialize_all(agency_data, validation, dropdown_values, barcode_data)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        for name, content in outputs.items():
            wo.write_file(os.path.join(out_dir, name), content)
    return outputs
