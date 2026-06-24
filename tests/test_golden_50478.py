"""Golden serializer tests — verify serializers reproduce real output byte-for-byte.

Strategy: hand-build the fully-enriched AgencyRawData for ServiceId 50478
(taken from the real WebObjects/*.txt) and assert each serializer emits the
exact golden line. This pins the OUTPUT FORMAT independently of loaders/pipeline.
Once the pipeline is ported, a second test will assert pipeline output == this graph.
"""
from datetime import datetime

import pytest

from app.models.raw import (
    AgencyRawData,
    DerivedDataRawData,
    FieldDataRawData,
    PostingDataRaw,
)
from app.serialize import webobjects as wo


def build_50478() -> AgencyRawData:
    """Reconstruct the enriched 50478 graph from real golden output."""
    fields = [
        FieldDataRawData(
            ObjectId="50478_AgentCode", AttributeName="AgentCode",
            FieldType="Alphanumeric", Caption="", AllowChange=0, Mandatory=0,
            SummaryScreen=0, ReceiptName="", Hidden=1, DisplayOrder=999,
            InitialValue="1",
        ),
        FieldDataRawData(
            ObjectId="50478_Agent", AttributeName="Agent",
            FieldType="Alphanumeric", Caption="1", AllowChange=0, Mandatory=0,
            SummaryScreen=0, ReceiptName="1", Hidden=1, DisplayOrder=999,
            InitialValue="มหาวิทยาลัยสุโขทัยธรรมาธิราช",
        ),
        FieldDataRawData(
            ObjectId="50478_Agency", AttributeName="Agency",
            FieldType="Alphanumeric", Caption="50478", AllowChange=0, Mandatory=0,
            SummaryScreen=0, ReceiptName="50478", Hidden=1, DisplayOrder=999,
            InitialValue="ขึ้นทะเบียนบัณฑิตปริญญาตรี มสธ.16",
        ),
        FieldDataRawData(
            ObjectId="50478_Category", AttributeName="Category",
            FieldType="Alphanumeric", Caption="", AllowChange=0, Mandatory=0,
            SummaryScreen=0, ReceiptName="", Hidden=1, DisplayOrder=999,
            InitialValue="University Service",
        ),
        FieldDataRawData(
            ObjectId="50478_REFNO5", AttributeName="REFNO5",
            FieldType="Alphanumeric", Caption="รหัสบาร์โค้ด", AllowChange=1,
            Mandatory=1, SummaryScreen=1, ReceiptName="รหัสบาร์โค้ด", Hidden=0,
            DisplayOrder=101, ExtraCharacters="@.-'/&{space}",
        ),
        FieldDataRawData(
            ObjectId="50478_REFNO3", AttributeName="AcctNo",
            FieldType="Alphanumeric", Caption="เลขประจำตัวนักศึกษา", AllowChange=1,
            Mandatory=1, SummaryScreen=1, ReceiptName="เลขประจำตัวนักศึกษา",
            Hidden=0, DisplayOrder=102, MinLength=10, MaxLength=10,
            ValidateMethod="StouChkDigit", ExtraCharacters="@.-'/&{space}",
            EditMask="9999999999",
        ),
        FieldDataRawData(
            ObjectId="50478_REFNO4", AttributeName="REFNO4",
            FieldType="Alphanumeric", Caption="ชื่อ-สกุล นักศึกษา", AllowChange=1,
            Mandatory=1, SummaryScreen=1, ReceiptName="ชื่อ-สกุล นักศึกษา",
            Hidden=0, DisplayOrder=103, ExtraCharacters="@.-'/&{space}",
        ),
        FieldDataRawData(
            ObjectId="50478_REFNO7_Lookup", AttributeName="REFNO7_Lookup",
            FieldType="Alphanumeric", Caption="ปีการศึกษา / ภาค", AllowChange=1,
            Mandatory=0, SummaryScreen=1, ReceiptName="ปีการศึกษา / ภาค",
            Hidden=0, DisplayOrder=104, LookupMethod="YearAndSemester",
            ExtraCharacters="@.-'/&{space}",
        ),
        FieldDataRawData(
            ObjectId="50478_REFNO7", AttributeName="REFNO7",
            FieldType="Alphanumeric", Caption="ปีการศึกษา / ภาค", AllowChange=0,
            Mandatory=0, SummaryScreen=0, ReceiptName="ปีการศึกษา / ภาค",
            Hidden=1, DisplayOrder=999, ExtraCharacters="@.-'/&{space}",
        ),
        FieldDataRawData(
            ObjectId="50478_AMT", AttributeName="Amount", FieldType="Currency",
            Caption="จำนวนเงินที่ต้องชำระ", AllowChange=1, Mandatory=1,
            SummaryScreen=1, ReceiptName="จำนวนเงินที่ต้องชำระ", Hidden=0,
            DisplayOrder=105, InitialValue="80000", MinValue=100, MaxValue=5000000,
        ),
    ]

    postings = [
        PostingDataRaw(
            ObjectId="Post_50478", Account="50478",
            ReceiptItems=["Agent", "Agency", "REFNO5", "AcctNo", "REFNO4", "REFNO7"],
            Sense="Credit", Attribute="Amount",
        ),
        PostingDataRaw(
            ObjectId="Post_50478_Fee", Account="BSFEE",
            ReceiptItems=[], Sense="Credit", Attribute="Fee",
        ),
    ]

    derived = [
        DerivedDataRawData(
            ObjectId="50478_Total", Attribute="Total", SummaryScreen=1,
            IncludeInTxn=1, Caption="THP_Agency_TotalDue_Caption",
            Formula="Fee+Amount",
        ),
        DerivedDataRawData(
            ObjectId="50478_Fee", Attribute="Fee", SummaryScreen=1, IncludeInTxn=1,
            Caption="THP_Agency_Fee_Caption", FixedAmount="1000",
            ReceiptName="THP_Agency_Fee_Caption",
        ),
        DerivedDataRawData(
            ObjectId="50478_REFNO7", Attribute="REFNO7", SummaryScreen=0,
            IncludeInTxn=1, Caption="ปีการศึกษา/ภาค",
            Formula="REFNO7_Lookup.Description",
        ),
    ]

    return AgencyRawData(
        ObjectId="50478", AgentCode="1", AgentName="มหาวิทยาลัยสุโขทัยธรรมาธิราช",
        AccountCode="50478", SchemeName="50478",
        SchemeDescription="ขึ้นทะเบียนบัณฑิตปริญญาตรี มสธ.16",
        AllowInvokeList=1, PrimaryBarcode="Barcode_50478", SchemeIdStart=1,
        SchemeIdString="05220216", ExtractId="AgencyPayment", AllowInvokeButton=1,
        TxnType="AgencySaleOffline", TransactionType="Offline",
        Tags=["University Service"],
        FieldData=fields, PostingData=postings, DerivedData=derived,
        StartDate=datetime(2015, 7, 1),
    )


# The exact golden scheme line provided by the user / extracted from output.
GOLDEN_SCHEME = (
    "<Object:<Path:/Configurations/EGA/EGAAgency/AgencyScheme/50478>><Contents:<Data:"
    "<SchemeName:50478><SchemeDescription:ขึ้นทะเบียนบัณฑิตปริญญาตรี มสธ.16>"
    "<AccountCode:50478><AllowInvokeList:1><PrimaryBarcode:Barcode_50478>"
    "<SchemeIdStart:1><SchemeIdString:05220216>"
    "<AgencyData:<FieldId:50478_AgentCode><FieldId:50478_Agent><FieldId:50478_Agency>"
    "<FieldId:50478_Category><FieldId:50478_REFNO5><FieldId:50478_REFNO3>"
    "<FieldId:50478_REFNO4><FieldId:50478_REFNO7_Lookup><FieldId:50478_REFNO7>"
    "<FieldId:50478_AMT>>"
    "<Postings:<Posting:Post_50478><Posting:Post_50478_Fee>>"
    "<ExtractId:AgencyPayment><AllowInvokeButton:1><TxnType:AgencySaleOffline>"
    "<DerivedData:<Variables:50478_Total><Variables:50478_Fee><Variables:50478_REFNO7>>"
    "<Tags:<Tag:University Service>><StartDate:2015-07-01>>>"
)


def test_scheme_50478():
    agency = build_50478()
    assert wo.serialize_agency_scheme(agency) == [GOLDEN_SCHEME]


def _golden_lines(filename: str, needle: str) -> list[str]:
    path = f"tests/golden/{filename}"
    with open(path, encoding="utf-8-sig") as fh:
        return [ln.rstrip("\n") for ln in fh if needle in ln]


def test_fielddata_50478():
    agency = build_50478()
    golden = _golden_lines("RA_AgencyFieldData.txt", "/FieldData/50478_")
    produced = [wo.serialize_field_data(agency, f) for f in agency.FieldData]
    assert produced == golden


def test_posting_50478():
    agency = build_50478()
    golden = _golden_lines("RA_AgencyPostingData.txt", "/PostingData/Post_50478")
    produced = [wo.serialize_posting(p) for p in agency.PostingData]
    assert produced == golden


def test_derived_50478():
    agency = build_50478()
    golden = _golden_lines("RA_AgencyDerivedData.txt", "/DerivedData/50478_")
    produced = [wo.serialize_derived(dd) for dd in agency.DerivedData]
    assert produced == golden


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
