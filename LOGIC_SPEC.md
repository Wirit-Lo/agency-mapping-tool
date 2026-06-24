# Agency Data Mapping Tool — Logic Spec (Migration Blueprint)

เอกสารนี้ถอด business logic จาก codebase เดิม (C# WinForms, `Helper.cs` 3,130 บรรทัด + `Form1.cs`) ออกมาเป็น blueprint สำหรับเขียนใหม่เป็น Python + FastAPI + Google Sheets โดยเป้าหมายคือ **output ต้องตรงกับของเดิม byte-for-byte** (ยืนยันแล้วกับ ServiceId 50478)

> หลักการ: ทุก pipeline step, static list, และ special case ในเอกสารนี้คือ business rule ที่สะสมมาหลายปี — ห้ามตัดทิ้งหรือ "ทำให้ง่ายขึ้น" โดยไม่มี golden test ยืนยัน

---

## 0. สถาปัตยกรรมเป้าหมาย

```
Google Sheets (11 sheets)
   │  gspread / google-api-python-client (Service Account, read-only)
   ▼
Loaders (1 ตัวต่อ sheet)  →  RawData models (Pydantic)
   ▼
Pipeline (ProcessAgencyAndFieldData → 18 enrichment steps ตามลำดับเป๊ะ)
   ▼
Serializers (8 ตัว ใช้ format template ตรงจาก Consts.cs)
   ▼
8 WebObject .txt files (UTF-8, #ReplaceWebObjectsBegin/End)
```

**กฎเหล็กของ output format:**
- ทุก object เป็น 1 บรรทัด ไม่มี whitespace ระหว่าง tag
- field ที่เป็น optional: ถ้าค่าว่าง → **ไม่ใส่ tag เลย** (ไม่ใช่ใส่ tag ว่าง)
- encoding = UTF-8 (มีภาษาไทยใน SchemeDescription, Caption)
- แต่ละไฟล์ห่อด้วย `#ReplaceWebObjectsBegin -l /Configurations/EGA/EGAAgency/<Type>/` ... `#ReplaceWebObjectsEnd`
- มี typo ที่ต้องคงไว้: DerivedData ใช้ `<Attibute:>` (สะกดผิด ไม่ใช่ Attribute) — ระบบปลายทางคาดหวังแบบนี้

---

## 1. Source Sheets → Column Mapping

จาก `THP Agency Data Mapping.json` (column number = 1-indexed ตาม Excel)

| Section | Sheet | RowStart | Column map |
|---|---|---|---|
| AgencyScheme | PayAtPost-PAP_ALL_ServiceID_V1.2-1.3 | 5 | SchemeName=3, Description=2 |
| FieldData | (sheet เดียวกัน) | — | Id=7, AttributeName=7, FieldType=5, Caption=4, AllowChange=9, Hidden=8 + **hardcoded**: FD_NAME=6, SERV_DATA_ID=10, MinLength=11, MaxLength=12, HideInSummary=13, DoubleCapture=14 |
| BarcodeDetail | PayAtPost-SpecBarcode_V1.5 | 3 | SchemeName=3, Suffix=4, Prompt="Scan Barcode" |
| BarcodeParsingData | (sheet เดียวกัน) | — | Start=7, Length=8 |
| DerivedData (Fee/Master) | PayAtPost-StatSUM_Master_V1.2 | 5 | Id=1, Caption=7, MinAmount=14, MaxAmount=15, MaxPerDay=16, Fee=13, StartDate=3, EndDate=4, Status=5, TxnType=6, ServiceType=7, ServiceCategory=8 |
| ValidationData | PayAtPost-ValidateScriptText | 5 | Id=3, Suffix=3, Validate=12, ReferenceField=7→fallback 6 |

**Fixed loaders** (โหลดทุกครั้ง ไม่ผ่าน config):
| Loader | Sheet | RowStart | หมายเหตุ |
|---|---|---|---|
| DerivedDataRequirements | AgencyDerivedDataRequirements | 2 | Id=1, Attribute=3, SourceField=4, Formula=5 |
| ServiceProviders | AgencyServiceProviders | 2 | Id=1, Type=2, ProviderName=3, WorkflowId=4, BarcodeRequired=5 |
| DropdownValue | PayAtPost-DropdownValue | 2 | Id=2, DropdownId=3, Caption=4, Name=5, FieldName=6, DerivedData=8, SourceField=9 |
| DefaultValue | PayAtPost-DefaultValue_V1.0 | 2 | Id=1, DefaultValue=4, ReferenceField=5 |
| ConfigReceipt | PayAtPost-ConfigReceipt_V1.0 | 4 | grouped by service (col1) |
| AgentMasterData | AgentMasterData | 4 | AgentCode=3, Name=4, TH=5, EN=6, Tax=7, BillName=11, BillAddress=12 |

> **หมายเหตุ Google Sheets:** ตอนนี้ loader เดิมอ่านด้วย Excel cell index (`Cells[i,n]`). เวลาเขียนใหม่ ให้อ่าน sheet เป็น list-of-lists (`get_all_values()`) แล้ว index ด้วย `row[n-1]` เพื่อรักษา column-number semantics เดิม **ห้ามใช้ header name** เพราะหลาย sheet มี header ซ้อน/merged cell ที่ไม่ใช่ row แรก

---

## 2. Cell Value Rules (สำคัญ — ใช้ทุกที่)

```
GetCellValue(cell):
  - None/empty → ""
  - ค่า == "(blank)" (ตัด trim แล้ว) → ""   ← sentinel ที่ต้องเช็ค
  - อื่นๆ → str(value).strip()

ToInt(text): parse ได้ → int, ไม่ได้ → 0
```

`GetFeeValue` (col 13 ของ Master) — ซับซ้อน มี 3 เคส:
1. ค่าว่าง / "(blank)" / "-2146826246" (Excel error code) → None
2. parse เป็น int ได้ → `fee + "00"` (เติมสตางค์ 2 หลัก) เช่น `100` → `"10000"`
3. conditional fee (เช่น `"1.100,2.150"`) → แตกเป็น ScopeData:
   - ลบ `"1."`, `"2."`, `","` ออก แล้วเก็บเฉพาะ digit
   - `WithinBangkokFee` = substring(0, firstLen) + "00"
   - `OutsideBangkokFee` = substring(firstLen, secondLen) + "00"
   - return WithinBangkokFee เป็นค่าหลัก

---

## 3. Field Type & Attribute Mapping

```
GetMappedFieldType(raw):
  currencyfield|paymentfield → Currency
  datefield                  → Date
  numberfield                → Numeric
  passwordfield              → PasswordField
  textarea|textfield         → Alphanumeric
  combobox                   → ComboBox
  (EditMask/EditMaskYear คงไว้ "as-is" เพื่อ detect ทีหลัง)

GetAttributeName(fieldType, name):
  ถ้า name ว่าง → "TBC_Field_<FieldType>" (Button/ComboBox/Currency/Date/Numeric/EditMask/Alphanumeric)
  ไม่ว่าง → name
```

ตอนสร้าง field (ใน ProcessAgencyAndFieldData):
- `EditMask*` → editMask = ("9" ถ้า EditMask ตรงตัว, ไม่งั้น "2") pad ขวาด้วย "9" ให้ยาว = maxLength, แล้วเปลี่ยน fieldType เป็น Alphanumeric
- `AMT` → AttributeName=Amount, readOnly=0, visible=1, mandatory=1
- `REFNO3` → AttributeName=AcctNo, readOnly=0, visible=1, mandatory=1
- `BRCDE` → readOnly=1
- `Button` → visible=0
- `ComboBox` → fieldType=Alphanumeric, lookupMethod="SampleLookup"
- **filter ออก:** ทุก field ที่ AttributeName=="REFNO2" **ยกเว้น** service อยู่ใน `PCCServices`
- COURSE1 / COURSEMATERIAL1 → mandatory=1
- DisplayOrder: DEGREE→999, ถ้า visible→suffix, ไม่งั้น 999

---

## 4. Static Lists (business rules — คัดลอกตรงตัว)

```python
noPipeServiceIds = [30078,30079,50982,50478,50597,50541,50540,93004,93005,93007]
requiredAgentDataServiceIds = [50002,50387,51020,52059,52093]
hideAmountFieldsDueToDerivedData = [50329,50474,50476,50491,50492,50540,50607,50841,
    50849,50851,50948,52032,52033,52035,52059,52093,90006,90008,90021,90023,90028,
    90030,90032,90035,90037,90039,90040]
availabilitySet132 = [50855]
availabilitySet164 = [50841,50842,51052]
availabilitySet486 = [90001,90006,90008,90023,90028,90030,90032,90035,90037,90039,
    93004,93005,93007,96004,96006]
allowChangeREFNO3 = [30079,50948,51106,51107,52059]
PCCServices = [90001,90006,90008,90023,90028,90030,90032,90035,90037,90039,93004,
    93005,93007,90021,90040]
withdrawalServices = [93004,93005,93007,96004]
hiddenFieldServicesWithMinMaxAmounts = [52093,50948,52059]
servicesWithHiddenREFNO3 = [50855,52093,90006,90008,90023,90028,90030,90032,90035,90037,90039]
lookupFieldsToHideInSummaryScreen = ["52047_REFNO8_lookup","50492_REFNO10_Lookup",
    "50492_REFNO12_Lookup","50492_REFNO14_Lookup"]
fieldsToSetAsMandatory = ["50492_REFNO16"]
```

---

## 5. Pipeline ลำดับเป๊ะ (ProcessAgencyAndFieldData)

อ่าน AgencyScheme+FieldData แล้วเรียง enrichment **ตามลำดับนี้** (ลำดับสำคัญ — บาง step พึ่งผลลัพธ์ step ก่อน):

```
 1. GetValidateMethodFromValidationData
 2. GetTransactionTypeTagMinMaxFromFeeData     ← insert Category field ที่ index 3, set Tags, Min/Max Amount
 3. GetReceiptConfigsFromConfigReceiptData
 4. GetReceiptConfigsFromAgentMasterData       ← เฉพาะ requiredAgentDataServiceIds (เพิ่ม Tax/Address)
 5. GetFieldDefaultValuesFromDefaultValueData
 6. GetLookupMethodValuesFromDropdownValueData
 7. GetProviderNameFromServiceProviderData
 8. GenerateCustomDerivedData                  ← step ใหญ่สุด (บรรทัด 1990-2452 ใน Helper.cs)
 9. HideAmountFieldsDueToDerivedData
10. UpdateTotalDerivedDataAndSetShowInSummaryScreenBasedOnDerivedData
11. UpdateFieldAndDerivedDataSummaryScreenFromHideInSummary
12. UpdatePCCServicesMinMaxValues
13. SetMandatoryFieldsForLookups
14. SetMandatoryFields
15. SetFieldsInSummaryScreen
16. SetWithdrawalMinMaxValues                  ← hardcode 93004/93005/93007 min/max
17. HideBankAtPostREFNO3Fields                 ← servicesWithHiddenREFNO3
18. LogServicesWithoutAccountOrAmount          ← logging เท่านั้น
```

Barcode เป็น pipeline แยก: `ProcessBarcodeAndBarcodeParsingData` → `ExtractBarcodeDataBySheet` (6 sheet: BOT-STD, NotBOT-STD, Scripttext, Bank@Post, InputData, Sukhothai)

### Default generators (ตอนสร้าง AgencyRawData ใหม่)
- **GenerateDefaultFieldData**: AgentCode, Agent, Agency (3 field หัว) — ต่อด้วย Category ที่ถูก insert index 3 ใน step 2
- **GenerateDefaultPostingData**: `Post_{name}` (Account={name}, ReceiptItems=[Agent,Agency], Sense=Debit ถ้า withdrawal ไม่งั้น Credit, Attribute=Amount) + `Post_{name}_Fee` (Account=BSFEE) ถ้า Fee>0 หรือ name==50982
- **GenerateDefaultDerivedData**: `{name}_Total` (Formula="Fee+Amount" ถ้ามี fee ไม่งั้น "Amount") + `{name}_Fee` ถ้ามี fee

### Special cases ใน AgencyScheme creation
- `schemeIdStart` = 1 ถ้าอยู่ใน noPipeServiceIds, ไม่งั้น 2
- `accountCode` = "51106" ถ้า service==51107, ไม่งั้น = ObjectId
- `availabilitySet` = Zone132/Zone164/Zone486 ตาม list (None ถ้าไม่มี)

---

## 6. Output Format Templates (จาก Consts.cs — authority)

ตัวเลข `{n}` = positional arg. Optional tail args ({15}+) = ใส่ก็ต่อเมื่อมีค่า

```
AgencyScheme:
<Object:<Path:.../AgencyScheme/{0}>><Contents:<Data:<SchemeName:{1}><SchemeDescription:{2}>
<AccountCode:{3}><AllowInvokeList:{4}><PrimaryBarcode:{5}><SchemeIdStart:{6}>
<SchemeIdString:{7}><AgencyData:{8}><Postings:{9}><ExtractId:{10}><AllowInvokeButton:{11}>
<TxnType:{12}><DerivedData:{13}><Tags:{14}>{15}{16}{17}{18}{19}>>
  // tail = startDate, endDate, availabilitySet, agencyProviderName, workflowId
  // variants: Custom (iframe/exe), Actual, SecondaryBarcode, SecondaryBarcodeActual

FieldData:
<Object:<Path:.../FieldData/{0}>><Contents:<Data:<AttributeName:{1}><FieldType:{2}>
<Caption:{3}><AllowChange:{4}><Mandatory:{5}><SummaryScreen:{6}><ReceiptName:{7}>
<Hidden:{8}><DisplayOrder:{9}>{10}...{19}>>
  // tail = initialValue, minMaxLength, minMaxValue, lookupMethod, validateMethod,
  //        fieldEmptyWhenEditing, extraCharacters, dateParseFormat, editMask, doubleCaptured

Posting:    <Object:<Path:.../PostingData/{0}>><Contents:<Data:<Account:{1}><ReceiptItems:{2}><Sense:{3}><Attribute:{4}>>>
Derived:    <Object:<Path:.../DerivedData/{0}>><Contents:<Data:<Attibute:{1}><SummaryScreen:{2}><IncludeInTxn:{3}><Caption:{4}>{5}{6}{7}>>   ← Attibute typo!
Barcode:    <Object:<Path:.../BarcodeDetails/{0}>><Contents:<Data:<Prompt:{1}><AllowManualEntry:{2}><Required:{3}><ParsingRules:{4}>{5}>>
BcParsing:  <Object:<Path:.../BarcodeParsingData/{0}>><Contents:<Data:<FieldId:{1}><Start:{2}>{3}>>
Validation: <Object:<Path:.../ValidationData/{0}>><Contents:<Data:<ValidationMethod:{0}>>>
Lookup:     <Object:<Path:.../LookupData/{0}>><Contents:<Data:<LookupMethod:{0}><Caption:{1}><DisplayMode:DropDown><AllowNone:1>>>
DynLookup:  ...<AllowNone:1><IsDynamic:1>{2}{3}>>   ← DependentFields + AdditionalParams
```

### Serialization conditionals (จาก Form1.cs)
- **minMaxLength**: ใส่ถ้า MinLength≠0 หรือ MaxLength≠0
- **minMaxValue**: เฉพาะ Amount และ (MinValue>0 หรือ service∈{50593,96005,96006}); MaxValue ใส่ถ้า>0 — หรือ PCC service ที่ MinValue>0 & MaxValue>0 & Hidden==0
- **dateParseFormat** (hardcode 6 field): 50628_REFNO4/50710_REFNO4=YYYYMMDD, 51120_REFNO5=DDMMYYYY, 50982_REFNO6/50002_REFNO7=DDMMYY+ThaiBuddhist, 50131_REFNO4=DDMMYYYY+ThaiBuddhist
- **51063_REFNO9** → summaryScreen=0
- **50533/50535** → ลบ endDate
- **Scope (conditional fee)**: `<FixedAmount:<$Scope:<$Default:{within}><00:{within}><43:{outside}>>>`
- **DerivedData lookup dependents** (Sukhothai): Semester→YEAR, Course1-4→YEAR,SEMESTER, CourseMaterial1-4→+COURSEn, Nationality→REFNO8_lookup

---

## 7. แผนเขียน Python + กลยุทธ์ทดสอบ

### โครง repo
```
agency-mapping-tool/
├── app/
│   ├── main.py                 # FastAPI: /generate /preview /validate
│   ├── config.py               # spreadsheet IDs, column maps (จาก section 1)
│   ├── sheets/
│   │   ├── client.py           # gspread wrapper + cache (TTL) + force-refresh
│   │   └── loaders.py          # 11 loaders → RawData
│   ├── models/                 # Pydantic: AgencyRawData, FieldDataRawData, ...
│   ├── pipeline/
│   │   ├── rules.py            # static lists (section 4)
│   │   ├── helpers.py          # GetCellValue/ToInt/GetFeeValue/field-type maps
│   │   ├── enrich.py           # 18 steps (section 5) — pure functions
│   │   └── barcode.py
│   └── serialize/
│       └── webobjects.py       # 8 templates (section 6)
├── tests/
│   ├── golden/                 # คัดลอก WebObjects/*.txt เดิมมาเป็น expected
│   └── test_golden.py          # generate แล้ว diff กับ golden เป๊ะ
└── frontend/                   # React (เฟสถัดไป)
```

### Golden test (critical)
1. snapshot source sheets เดิม (Excel ที่อยู่ใน Archive) + output `.txt` 8 ไฟล์ = golden fixture
2. รัน pipeline ใหม่กับ input ชุดเดียวกัน
3. assert ทุกบรรทัด identical — เริ่มจาก ServiceId 50478 (ยืนยันแล้ว) แล้วขยายเป็นทั้งไฟล์
4. ถ้าต่าง → diff บอกตรงไหน ก่อน refactor ต่อ

### ลำดับลงมือ
1. models + helpers + golden harness (เทียบ 1 service ก่อน)
2. loaders (อ่าน Excel เดิมก่อน แล้วค่อยสลับเป็น Google Sheets — input เดียวกันต้องได้ผลเท่ากัน)
3. enrich 18 steps ทีละตัว + รัน golden หลังแต่ละ step
4. serializers → ครบ 8 ไฟล์ผ่าน golden
5. FastAPI endpoints + cache
6. React UI

---

## 8. จุดเสี่ยง / ต้องระวัง
- **Excel serial date**: ของเดิมใช้ `DateTime.FromOADate(int)`. ใน Google Sheets ถ้าตั้ง format เป็น date จะได้ string — ต้อง handle ทั้ง int serial และ string parse
- **ลำดับ field**: Category ถูก `Insert(3,...)` — ต้องรักษาตำแหน่งเป๊ะ ไม่งั้น AgencyData order เพี้ยน
- **typo `Attibute`** ใน DerivedData — คงไว้
- **"(blank)" sentinel** — sheet จริงมีคำนี้เป็นค่า ต้อง treat เป็นว่าง
- **REFNO2 filter** + PCC exception
- **fee "00" padding** = สตางค์ ไม่ใช่ ×100 ในบางจุด (Min/Max ใช้ ×100 แต่ fee ใช้ pad string) — คนละ logic อย่าสลับ
- **encoding (ตรวจจาก output จริงแล้ว)**: ไฟล์เป็น **UTF-8 with BOM** (3 byte แรก = `EF BB BF`) และ **line ending เป็น LF (`\n`) ล้วน ไม่ใช่ CRLF** — ตอนเขียน Python ต้องใช้ `open(path, "w", encoding="utf-8-sig", newline="\n")` เพื่อให้ตรง golden เป๊ะ (utf-8-sig ใส่ BOM, newline="\n" กัน Windows แปลงเป็น CRLF)
