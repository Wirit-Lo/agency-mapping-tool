"""RawData models — ported 1:1 from C# Classes/RawData/*.cs.

Field names match the C# property names so the porting of Helper.cs logic
stays line-for-line traceable. Defaults mirror the C# initializers.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ScopeData(BaseModel):
    WithinBangkokFee: str = ""
    OutsideBangkokFee: str = ""


class FieldDataRawData(BaseModel):
    Suffix: int = 0
    ObjectId: str = ""
    AttributeName: str = ""
    FieldType: str = ""
    Caption: str = ""
    AllowChange: int = 0
    Mandatory: int = 0
    LookupMethod: Optional[str] = None
    ValidateMethod: Optional[str] = None
    Hidden: int = 0
    ReceiptName: str = ""
    DisplayOrder: int = 0
    MinLength: int = 0
    MaxLength: int = 0
    MinValue: int = 0
    MaxValue: int = 0
    InitialValue: str = ""
    FD_NAME: str = ""
    FieldEmptyWhenEditing: bool = False
    ExtraCharacters: str = ""
    SERV_DATA_ID: Optional[str] = None
    SummaryScreen: int = 1
    EditMask: str = ""
    HideInSummary: str = ""
    DoubleCaptured: int = 0


class PostingDataRaw(BaseModel):
    ObjectId: str = ""
    Account: str = ""
    ReceiptItems: list[str] = Field(default_factory=list)
    Sense: str = ""
    Attribute: str = ""


class DerivedDataRawData(BaseModel):
    ObjectId: str = ""
    Attribute: str = ""
    Formula: str = ""
    FixedAmount: str = ""
    SummaryScreen: int = 0
    IncludeInTxn: int = 0
    ReceiptName: str = ""
    Caption: str = ""
    Scope: Optional[ScopeData] = None


class AgencyRawData(BaseModel):
    ObjectId: str = ""
    AgentCode: str = ""
    AgentName: str = ""
    AccountCode: str = ""
    SchemeName: str = ""
    SchemeDescription: str = ""
    AllowInvokeList: int = 0
    PrimaryBarcode: str = ""
    SchemeIdStart: int = 0
    SchemeIdString: str = ""
    ExtractId: str = ""
    AllowInvokeButton: int = 0
    TxnType: str = ""
    Tags: list[str] = Field(default_factory=list)
    TransactionType: str = ""
    FieldData: list[FieldDataRawData] = Field(default_factory=list)
    PostingData: list[PostingDataRaw] = Field(default_factory=list)
    DerivedData: list[DerivedDataRawData] = Field(default_factory=list)
    StartDate: Optional[datetime] = None
    EndDate: Optional[datetime] = None
    AvailabilitySet: Optional[str] = None
    Type: Optional[str] = None
    AgencyProviderName: Optional[str] = None
    WorkflowId: Optional[str] = None


class AgencyMasterRawData(BaseModel):
    ObjectId: str = ""
    Caption: str = ""
    MinAmount: str = ""
    MaxAmount: str = ""
    MaxAmountPerDay: str = ""
    Fee: Optional[str] = None
    StartDate: Optional[datetime] = None
    EndDate: Optional[datetime] = None
    Status: str = ""
    TransactionType: str = ""
    ServiceType: str = ""
    ServiceCategory: str = ""
    Scope: Optional[ScopeData] = None


class AgentRawData(BaseModel):
    AgentCode: str = ""
    AgentName: str = ""
    FullNameTH: str = ""
    FullNameEN: str = ""
    TaxNumber: str = ""
    BillName: str = ""
    BillAddress: str = ""


class ValidateRawData(BaseModel):
    ObjectId: str = ""
    Suffix: int = 0
    ReferenceField: str = ""
    ValidateMethod: str = ""


class ServiceProviderRawData(BaseModel):
    ObjectId: str = ""
    ProviderName: str = ""
    Type: str = ""
    WorkflowId: str = ""
    BarcodeRequired: str = ""


class DropdownValueRawData(BaseModel):
    ObjectId: str = ""
    DropdownId: str = ""
    DropdownCaption: str = ""
    DropdownName: str = ""
    FieldName: str = ""
    DerivedData: str = ""
    SourceField: str = ""


class DefaultValueRawData(BaseModel):
    ObjectId: str = ""
    DefaultValue: str = ""
    ReferenceField: str = ""


class DerivedDataRequirementsRawData(BaseModel):
    ObjectId: str = ""
    Attribute: str = ""
    SourceField: str = ""
    Formula: str = ""


class ConfigReceiptDetailRawData(BaseModel):
    LineNumber: int = 0
    LineCondition: str = ""
    MappingCondition: str = ""
    DecimalCondition: str = ""
    FD_NAME: str = ""


class ConfigReceiptRawData(BaseModel):
    ObjectId: str = ""
    Service: str = ""
    Details: list[ConfigReceiptDetailRawData] = Field(default_factory=list)


class AccountMapping(BaseModel):
    ServiceId: int = 0
    AccountCode: int = 0


class BarcodeParsingRawData(BaseModel):
    Suffix: int = 0
    Id: str = ""
    FieldId: str = ""
    Start: int = 0
    Length: int = 0


class BarcodeRawData(BaseModel):
    Id: str = ""
    Name: str = ""
    Prompt: str = ""
    ImpulseName: str = ""
    CheckDigitName: str = ""
    AllowManualEntry: int = 0
    Required: int = 0
    MaxLength: int = 0
    ParsingRules: list[str] = Field(default_factory=list)
    BCParsingRawData: list[BarcodeParsingRawData] = Field(default_factory=list)
