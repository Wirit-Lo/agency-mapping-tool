"""Static business-rule lists — ported verbatim from Helper.cs #region Static Lists.

DO NOT prune or "simplify". Each ID is a years-accumulated business rule.
Verified against Helper.cs lines 14-188.
"""

# Service Ids without Pipe(|) in barcode. SchemeIdStart and Parsing Start = 1
NO_PIPE_SERVICE_IDS = {
    30078, 30079, 50982, 50478, 50597, 50541, 50540, 93004, 93005, 93007,
}

# Service Ids that require Agent Tax Number and Address in the Session Receipt
REQUIRED_AGENT_DATA_SERVICE_IDS = {
    50002, 50387, 51020, 52059, 52093,
}

# Service Ids to HIDE Amount fields (value comes from Derived Data)
HIDE_AMOUNT_FIELDS_DUE_TO_DERIVED_DATA = {
    50329, 50474, 50476, 50491, 50492, 50540, 50607, 50841, 50849, 50851,
    50948, 52032, 52033, 52035, 52059, 52093, 90006, 90008, 90021, 90023,
    90028, 90030, 90032, 90035, 90037, 90039, 90040,
}

AVAILABILITY_SET_132 = {50855}
AVAILABILITY_SET_164 = {50841, 50842, 51052}
AVAILABILITY_SET_486 = {
    90001, 90006, 90008, 90023, 90028, 90030, 90032, 90035, 90037, 90039,
    93004, 93005, 93007, 96004, 96006,
}

# Allow Change even with Barcode Parsing rule
ALLOW_CHANGE_REFNO3 = {30079, 50948, 51106, 51107, 52059}

# PCC Service Ids with REFNO2
PCC_SERVICES = {
    90001, 90006, 90008, 90023, 90028, 90030, 90032, 90035, 90037, 90039,
    93004, 93005, 93007, 90021, 90040,
}

# Withdrawal Services (<Sense:Debit>)
WITHDRAWAL_SERVICES = {93004, 93005, 93007, 96004}

# Services that keep Min/Max Amount even when hidden
HIDDEN_FIELD_SERVICES_WITH_MINMAX_AMOUNTS = {52093, 50948, 52059}

# Services with hidden REFNO3/AcctNo
SERVICES_WITH_HIDDEN_REFNO3 = {
    50855, 52093, 90006, 90008, 90023, 90028, 90030, 90032, 90035, 90037, 90039,
}

# Lookup Fields to hide in Summary Screen
LOOKUP_FIELDS_TO_HIDE_IN_SUMMARY_SCREEN = [
    "52047_REFNO8_lookup",
    "50492_REFNO10_Lookup",
    "50492_REFNO12_Lookup",
    "50492_REFNO14_Lookup",
]

# Lookup Fields set as Mandatory
FIELDS_TO_SET_AS_MANDATORY = ["50492_REFNO16"]


class TransactionTypes:
    AgencySaleOffline = "AgencySaleOffline"
    AgencySaleOnline = "AgencySaleOnline"
    AgencySaleOfflineNonReversible = "AgencySaleOfflineNonReversible"
    AgencyWithdrawal = "AgencyWithdrawal"
