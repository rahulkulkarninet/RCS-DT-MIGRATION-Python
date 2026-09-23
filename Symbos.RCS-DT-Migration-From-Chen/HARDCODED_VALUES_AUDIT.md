# Hardcoded-Value Audit — Direct & Loop Migration Queries

**Scope:** all 63 SQL files in `SQL/Migration queries/Direct/` (59) and `SQL/Migration queries/Loop/` (4).
**Date:** 2026-08-21
**Status:** findings only. No SQL, JSON, or Python has been changed by this audit.

**Purpose.** The migration already has two mechanisms for externalising values, but adoption is patchy. Many files still carry magic FK integers, `CASE WHEN '<legacy code>' THEN <magic id>` blocks, and name-based joins against reference tables. Several are producing wrong data today. This document catalogues every finding, assigns each to the correct mechanism, and sequences the remediation.

**How to use it.** §2 is the catalogue, grouped into four classes with very different effort/risk profiles. §4 is the per-file checklist. §5 is the phased plan. Class A needs business sign-off on the values before anything is implemented; Phase 0 in §5 needs none and can start immediately.

---

## §1 Mechanism reference

### The two mechanisms

|  | **SQL token substitution** | **Python workflow service** |
|---|---|---|
| **Config** | `variables/migration_variables.json` — one file, four groups: `vwHost`, `lookup_variables`, `metafield_variables`, `constant_variables` | one JSON per domain: `variables/account_status_codes.json`, `bank_transaction_method_codes.json`, `arrangement_type_codes.json`, `closure_reason_codes.json`, `cost_codes.json` |
| **Syntax** | `{{VarName}}` — regex `\{\{(\w+)\}\}`, [`DT_query_processor.py:74`](DT_query_processor.py). No spaces, `\w+` only: `{{ LoadID }}` and `{{Load-ID}}` will **not** match and survive into the executed SQL. | n/a — the service rewrites the staging column in place |
| **Action** | value substituted into the SQL text at prepare time, [`replace_variables_in_sql`](DT_query_processor.py) `DT_query_processor.py:451` | staging data normalised **before** the SQL runs, so the SQL's plain `JOIN ON label = label` succeeds |
| **Cardinality** | one value per name | many source codes → one target label |
| **Failure mode** | **silent** — a missing name logs a warning and emits `NULL` into the SQL (`get_variable_value`, `DT_query_processor.py:448`) | **loud** — `update_*` returns `success: False` and aborts the customer; `check_*` lists every unmapped value and names the JSON to edit |
| **Use for** | scalar IDs: `LoadID`, `AddressTypeID_Legal`, `ContactTypeID_*`, MetaField group IDs | many-to-one code vocabularies: legacy status / payment / arrangement / closure codes |

**Decision rule:** many-to-one legacy code vocabulary → workflow service. Single scalar ID → `{{token}}`.

### Token resolution order

`get_variable_value` (`DT_query_processor.py:417-449`) resolves in this order:

1. **Runtime constructor values, checked first** (`:419-424`) — `LoadID`, `CurrentSessionID`, `EntityID`. These come from `SQLMigrationManager.__init__`, not from JSON.
2. **`AccountSpecificsGroupID_<NAME>` prefix** (`:427-441`) — strips the prefix, looks the remainder up in `metafield_variables` (exact, then `.upper()`); warns and returns `None` if absent.
3. **Everything else** → `ConfigParser.get_variable` (`config_parser.py:261-272`), which uppercases the name and searches **all categories in dict insertion order**, first hit wins. A name colliding across categories resolves to whichever was inserted first.
4. Miss → warning + `None` → the literal text `NULL` in the SQL.

**Value → SQL literal rules** (`replace_var`, `DT_query_processor.py:453-467`): a `str` already wrapped in `'...'` is emitted as-is; a `str` containing `NULL`/`GETDATE()`/`NEWID()` is emitted unquoted; any other `str` is wrapped in single quotes **with no escaping of embedded apostrophes**; `None` → `NULL`; int/float → `str(value)`.

### How the four groups resolve

| Group | Resolver | Behaviour | Fallback |
|---|---|---|---|
| `vwHost` (12 vars) | `_resolve_vw_host`, `config_parser.py:107-150` | **one** query for all vars, `SELECT ISNULL([col], default) AS [name], … FROM [vwHost] LEFT JOIN [vwHost2] ON …`. Reads `result.iloc[0]` — first row only, no HostID filter | per-var `default` |
| `lookup_variables` (5) | `_resolve_lookups`, `config_parser.py:152-176` | **one query per variable**, `SELECT [col] FROM [table] WHERE [filter_col] = 'filter_value'` | per-var `default` (may itself be `null`) |
| `metafield_variables` (13) | `_resolve_metafields`, `config_parser.py:178-204` | one query per variable against `tblMetaField_AccountSpecificsGroup` | **`None`** — no default supported |
| `constant_variables` (20) | `load_configs`, `config_parser.py:57-60` | no DB query; `config.get('default')` straight from JSON | n/a |

> **Documentation trap:** the `query_template` and `join_type` keys in `migration_variables.json` (`:6`, `:9`, `:76`, `:124`) are **ignored by the code**. `_resolve_vw_host` hardcodes `LEFT JOIN` at `config_parser.py:128`, and the `ISNULL(...)` wrapper in the `lookup_variables` template is not used — the default is applied in Python instead. Do not trust those keys when reasoning about behaviour.

### Loop 06/07/08 fan-out

`{{AccountSpecificsGroupID}}` never reaches `replace_variables_in_sql`. At **scan** time, `DT_query_processor.py:291-293` routes sequences 6/7/8 in the `Loop` subfolder to `_generate_loop_files` (`:322-350`), which emits one in-memory copy of the file per non-`None` metafield variable (`06.tblentity_AccountSpecifics_MIMO`, `_MTTP`, `_BILL`, …) with a plain `content.replace()`. With the current JSON that turns 3 files into 39. The sibling `_process_metavalue_file` (`:352-391`) handles `{{AccountSpecificsGroupID_<NAME>}}` for the `Metavalue_AccountSpecifics` subfolder.

### Execution split

Files 1–77 run through SQLAlchemy; file 78 runs through `sqlcmd` — see `services/workflows/customer_sql_workflow_service.py:26` and `db_manager.execute_sqlcmd` (`db_manager.py:476-640`), which uses idle-based timeouts (`sqlcmd_idle_timeout = 900`) because file 78's `WHILE` loops run silently for a long time. Note `db_manager.py:530-533` exposes sqlcmd's separate `-v` / `$(name)` variable mechanism — it is **not** the `{{}}` mechanism and is currently invoked with `variables=None`.

### Adding a new code-mapping domain — the 8-step scaffold

Derived from `arrangement_type_service.py` + `services/workflows/customer_arrangement_type_workflow_service.py`. All four existing domains follow it identically.

1. `variables/<x>_codes.json` — pick the shape (below).
2. Root-level `<x>_service.py` — module-scope `SOURCES` / `LOOKUP_TABLE` / `LOOKUP_ID_COLUMN` / `LOOKUP_LABEL_COLUMN` (cf. `bank_transaction_method_service.py:14-22`), plus `load_<x>_mapping_frame` / `build_<x>_resolution_frame` / `bulk_update_<x>` / `get_invalid_<x>_from_db`, normalising through `text_normalization.normalize_lookup_key` / `match_key`.
3. `<X>UpdateResult` / `<X>CheckResult` TypedDicts in `result_types.py`.
4. `services/workflows/customer_<x>_workflow_service.py` — resolve the JSON path as `Path(__file__).resolve().parents[2] / 'variables' / '<x>_codes.json'`, guard `.exists()`, `json.load(encoding='utf-8')`, guard `isinstance(dict)`.
5. Export in `services/workflows/__init__.py` **and** `services/__init__.py`.
6. Instantiate in `customer_processor.py` (~L80-88) and add the thin delegators.
7. Insert the update+check pair into `customer_sql_workflow_service.execute_mixed_sql_methods`, **before** the `GATE_SQL` approval (~L172).
8. Simplify the SQL to a label JOIN, matching `Loop/76:153-154`.

**Two JSON shapes, and when each applies:**

```jsonc
// flat — no default needed
{ "Target Label": ["CODE1", "CODE2"] }              // account_status_codes, bank_transaction_method_codes

// nested — "default" fills NULL/blank source values
{ "default": "Payment Plan", "mapping": { … } }      // arrangement_type_codes

// nested — "default_for_unmapped" leaves NULL alone, catches values that failed to map
{ "default_for_unmapped": "Other Reason - Please see notes", "mapping": { … } }   // closure_reason_codes

// two lookups plus explicit exclusions — the source code is a column NAME, not a value
{ "default_master_cost": "…", "cost_types": { … }, "master_costs": { … }, "not_costs": { … } }  // cost_codes
```

The rationale for the two different default keys is documented in-code at `customer_closure_reason_workflow_service.py:60-62`.

**Where the cost domain departs from the scaffold.** Steps 1-7 are identical. Step 8 cannot be, and neither can the "rewrite the staging column in place" premise in the table above: a cost code is part of the column name (`Chg_COL`), one per cost type across a single wide row per debtor, so there is no value to rewrite. `cost_service.py` unpivots the charged columns into `RC_STAGING_COSTS` — a table of its own, `SQL/Schemas/RC_STAGING_COSTS Schema.sql`, deployed once per environment like `RC_STAGING_TREATMENTS` — with both FKs already resolved, and step 8 becomes a plain `INSERT … SELECT` from that instead of a label JOIN. It is also the only domain where an unmapped value is **fatal** rather than a NULL FK plus a warning; see A3 for why.

---

## §2 Findings by class

### Class A — Business code→ID maps

Many-to-one legacy vocabularies. **Each needs business sign-off on the values before implementation.** Target the workflow-service pattern from §1.

| # | Location | Current state | Proposed |
|---|---|---|---|
| ~~**A1**~~ **DONE** | `Loop/76…:139-147` | `Frequency 'W'→2, 'F'→3, 'M'→4, 'BM'→7, 'Q'→12, 'Y'→5, ELSE 0`. **`ELSE 0` wrote a `FrequencyID` FK that does not exist** — silent bad data rather than a failure | **Implemented.** `variables/frequency_codes.json` + `frequency_service.py` + `customer_frequency_workflow_service.py`; the CASE is now `LEFT JOIN tblFrequency F ON AR.Frequency = F.Frequency`. Unmapped codes land as NULL and are reported by the check step instead of becoming `0`. **Requires** `RC_ARRANGEMENT.Frequency` widened to `NVARCHAR(100)` — see the note under §5 Phase 2 |
| **A2** | `Loop/76…:134-138` and `Direct/75:35-39` | `ArrangementStatusID` derived as 2 (Successful) / 4 (Failed) / 1 (In Progress); labels exist only as comments. **Also flag for the business:** the Failed test `DATEDIFF(DAY, Last_Instal_Date, GETDATE()) < 0` fires when the last instalment is in the *future*, which is the in-progress case — the branches look inverted. Duplicated across two files with no shared source | tokens + confirm the rule |
| ~~**A3**~~ **DONE** | `Direct/51.tblcosts.sql:9-67` | 59 hardcoded `('ADM', ISNULL([Chg_ADM],0))` code↔column pairs in a `CROSS APPLY (VALUES …)`. ~~Note `CostTypeID` itself is already correctly resolved via the `CSRC_CostTypeMapping` table (`:107`) — only this list is hard~~ **That note was wrong, and it was the most expensive line in this document.** `CSRC_CostTypeMapping` is reference data seeded per environment; it had no row for `COL`, and `:107` was an `INNER JOIN`, which drops what it cannot match. On dev load 238 that silently discarded all 11,038 `COL` charges — $403,234.13, of which $358,488.29 was still outstanding — and left `tblCost` **completely empty**. Accounts whose `COL` charge had been paid finished with a negative balance, because `49.tblpayment.sql:43` copies the payment's `AllocatedCost` across regardless. Found via account `1002793147`, balance −42.25 | **Implemented.** `variables/cost_codes.json` + `cost_service.py` + `customer_cost_workflow_service.py`. The wide `Chg_<code>` columns are unpivoted into `RC_STAGING_COSTS` with both FKs resolved before the SQL runs, and 51 is now a plain `INSERT … SELECT` from it. A charged code that the JSON neither maps nor excludes **fails the customer** — the one failure mode this whole document exists to prevent. `CSRC_CostTypeMapping` is left untouched: the migration neither reads nor writes it now, matching the way `account_status_codes.json` owns its vocabulary outright |
| ~~**A4**~~ **DONE** | `Direct/51.tblcosts.sql:93-95` | `CASE WHEN CostField = 'COL' THEN 12 ELSE 2 END` → `MasterCostID`. Two magic FKs keyed off a literal code | **Implemented** with A3. `default_master_cost` plus per-code `master_costs` overrides in `cost_codes.json`, resolved against `tblMasterCost.MasterCost` by label. The two literals were `tblMasterCost` 2 = "Default Master Cost" and 12 = "Collection Costs"; that second one is also what settled `COL`'s cost type, since `tblMasterCost[12].CostTypeID` is 22 (ADMIN FEE RECOVERY) rather than the 1 (MERCANTILE) every row of `CSRC_CostTypeMapping` uses |
| ~~**A5**~~ **DONE** | `Direct/45.tblaccountincident.sql:17-23` | `Cause_Description LIKE '%THEFT%'→2, '%FIRE%'→3, '%WATER%'→4 (commented "Flood"), '%DAMAGE%'→8, ELSE 9`. Keyword order was a significant but undocumented precedence rule; IDs 1, 5, 6, 7 unreachable | **Implemented.** `variables/incident_type_codes.json` + `incident_type_service.py`. The ordered `rules` array preserves precedence exactly (verified: "WATER DAMAGE FROM FIRE" still resolves to Fire, not Flood); file 45 is now `LEFT JOIN tblIncidentType IT ON AE.Cause_Description = IT.IncidentType`. **Still for the business:** the `WATER`→`Flood` keyword/label mismatch, and whether the unreachable types should be reachable |
| ~~**A6**~~ **DONE** | `Direct/28…related_parties.sql:15-22` | `'GTR'/'ACH'/'SPO'/'REF'/'SOL'/'WIT'` → `{{RelationshipID_*}}`. The targets were soft but the legacy code list was not; `ELSE {{RelationshipID_Other}}` swallowed unknown codes with no reporting | **Implemented.** `variables/related_party_type_codes.json` + `related_party_type_service.py`; file 28 is now `LEFT JOIN tblRelationship R ON RPA.Related_Party_Type_Code = R.Relationship`. `default_for_unmapped: "Other"` reproduces the old ELSE, but the swept values are now reported. Adding a code is a JSON edit |
| **A7** | `Direct/73.tblCallHistory.sql:39` and `:76` | `DC.Type IN ('I','O','V')` — the same list duplicated in two statements **in a different order**. Drift risk | shared config list |
| **A8** | `Direct/72:57`, `:81` | `IIF(DC.Type = 'V','IVR','Phone')` — the same literal mapping written out three times | mapping |
| **A9** | `Direct/49.tblpayment.sql:28` + `Direct/75.tblinvoice.sql:24` | The Direct/Trust pair: `IIF(P.Payment_Code = 'PAYD', 2, 1)` in 49, and `'2' , --Direct` in 75 — passed there as a **string literal** for a numeric selection. Two copies, no shared source of truth | shared token |
| **A10** | `Direct/22:28` vs `Direct/27:21` | The IsPerson classification rule: 22 checks `A_B_N IS NULL AND A_C_N IS NULL`, 27 checks `A_B_N IS NULL` only. Same job, two different rules | reconcile, then externalise |
| **A11** | 12 sites | Legacy Y/N sentinel spelled inconsistently: `'Yes'` at `25:36`, `26:34`; `'Y'` at `35:38`, `40:53`, `58:50`, `60:54`, `65:56`, `72:58`, `76:76,83,238,245`. All are exact case-sensitive comparisons, so `'y'`/`'1'`/`'TRUE'` silently mean "no" | normalise |
| **A12** | `Direct/61:21`, `62:28`, `63:28`, `64:38`, `65:35`, `65:72` | `D.Doc_Link_Via != 'H'` exclusion repeated across 5 files, uncommented — nobody reading the SQL knows what `'H'` means | shared config + comment |
| **A13** | `Direct/29:17`, `32:14` | **All** phone numbers forced to `{{ContactDetailTypeID_Mobile}}` regardless of value. No prefix classification exists (04→Mobile, 02/03/07/08→Home, 1300/1800→Work) | phone-prefix classification map |
| ~~**A14**~~ **DONE** | `Direct/44.tbladdress_Assign_StateID.sql:4` | `LEFT JOIN tblState S ON ADR.State = S.StateShort` — short code only, so `New South Wales`, `N.S.W.`, `VIC.` all left `StateID` NULL | **Implemented.** `variables/state_codes.json` + `state_service.py`. File 44's SQL is **unchanged** (it stays the exact-match fast path); the service runs **after** the SQL batch and resolves the rows it left NULL. Post-batch because `tblAddress.State` is populated mid-batch by files 37-43 from eleven different sources, which have all collapsed into that one column by then. **Not covered:** there is still no `CountryID` equivalent — `{{DefaultCountryID}}` is force-set in 37-43 with no country parsing |
| **A15** | `Direct/75:40` | `FrequencyID` always `NULL`, commented "Deal is an Ad-hoc arrangement, no frequency". No Weekly/Fortnightly/Monthly mapping applied at all | resolve alongside A1 |
| **A16** | `Direct/22:30`, `Direct/70` | `C.Title` and `POI.Type` copied through raw with no normalisation (`MR`/`Mr.`/`MISTER`). Needs confirming whether the target columns are constrained lists | normalise if constrained |
| **A17** | `Direct/60:19`, `:22` | Email `Subject` hardcoded to the literal `'Document'` for every migrated email; `FromEmailAddress` hardcoded to `''` | config |

### Class B — Boilerplate scalars

Mechanical, low risk, high churn. Add to `constant_variables` (no DB round-trip) or `lookup_variables` in `migration_variables.json`, then sweep.

| # | Pattern | Spread | Proposed token |
|---|---|---|---|
| **B1** | `CreateID = 1`, including `ISNULL(OM.ContactIDDestination, 1)` | ~60 sites — nearly every insert in both folders. There is **no `SystemUserID`/`MigrationUserID` variable anywhere in the JSON**. Highest-value single extraction | `{{SystemUserID}}` |
| **B2** | `StatusID = 1` on insert, plus `AND X.StatusID = 1` filters (24 filter sites) | ~70 sites across both folders | `{{StatusID_Active}}` |
| **B3** | `AddressStatusID = 1` | `37:45`, `38:45`, `39:45`, `40` (×5: `:20,40,60,81,102`), `41:45`, `42:45`, `43:21` | `{{AddressStatusID_Active}}` |
| **B4** | `@ReminderMethodID = 2` (Email) / `= 1` (SMS) | `Loop/76:78-80`, `:85-87`, and duplicated at `:240-242`, `:247-249` for the RC_ARRANGEMENT loop. No lookup against a reminder-method table | `{{ReminderMethodID_Email}}` / `{{ReminderMethodID_SMS}}` |
| **B5** | `@User_SessionID = 1` | `Loop/76:78`, `:85`, `:240`, `:247` — while `:445-447` in the same file correctly uses `{{CurrentSessionID}}`. Clearly an oversight | `{{CurrentSessionID}}` |
| **B6** | Single-literal FKs | `50:19` `InsuranceRefTypeID = 2`; `52:9` `ContactID = 1`; `53:18`/`55:19`/`57:18` `AllocationTypeID` 1/4/2; `54:15` + `76:402` `PoliceAttended = 0`; `58:16` `SMSOutputStatusID` 2/5; `58:52`/`60:56`/`65:58`/`72:60` `CorrespondenceStatusID`; `62:13` `CommunicationMethodID = 1 --LETTER`; `65:26` `PrintStatusID` 3/0; `66:100`/`67:15`/`69:14` `EntryStatusID = 1`; `72:19` `CallDataSourceID = 1`; `Loop/06:22` `IsOpenOnAccountLoad = 1`; `76:476` + `72` various `@UserContactID = 1` | one token each, `lookup_variables` or `constant_variables` per case |
| **B7** | `CurrencyID = 1` / `CurrencyRate = 1.0` | `48:27` + `51:97`, `48:31` + `51:98`. **Both carry in-file comments admitting they need a mapping table** | `{{CurrencyID_AUD}}` / `{{CurrencyRate_Default}}` |
| **B8** | `SystemContactDetailTypeID = 0 --Email` / `= 1 --Phone` | `47:12`, `47:20` — the only untokenised members of an otherwise fully tokenised `ContactDetailTypeID_*` family | tokens |

### Class C — Missing, wrong, and unused tokens

Highest defect density. Most are drop-in fixes needing no new infrastructure.

| # | Location | Problem |
|---|---|---|
| **C1** | `Direct/76.tblarrangement.sql:29` | Hardcodes `1` for `BankTransactionMethodID` with the comment *"to run via mapping table"* — while **`BankTransactionMethodID_DirectPayment` is already defined** at `migration_variables.json:111-118`. Verified: `{{BankTransactionMethodID_DirectPayment}}` appears in **0** of the 63 files. Pure drop-in |
| **C2** | `Direct/67.tblentry_notes.sql` | `EntryTypeID` hardcoded `45`, while sibling `68` uses `{{EntryTypeID_Treatment}}`. **No `EntryTypeID_Note` variable exists.** Finding restated after the notes rewrite: the value was `-1` when this was first recorded and is now `45`, and the row it types is no longer a note but an account's whole consolidated history. 45 is `Note from Previous System`, which is defensible, but worth pairing the variable with a business decision on whether a whole consolidated history should carry its own `tblEntryType` (e.g. *Migrated Note History*). **The two sibling defects this pointed at are now fixed:** `{{EntryTypeID_Treatment}}` filtered on the name `'Treatment'`, which matches no `tblEntryType` row (the type is `'TreatmentService Entry Type'`, 49), so it silently fell to its `-1` default and LoadID 1931 filed **10,608** treatment histories as `-1 System Note`; and `70` hardcoded `49`, which would then have collided with treatments, so it now uses `{{EntryTypeID_Result}}` (13 `Result`). Both files now `RAISERROR` if the lookup returns the `-1` default rather than writing System Notes silently |
| **C3** | `Direct/24:13` (was also `Direct/26:36`) | `RelationshipID = 1 -- Primary Debtor` — the most-used relationship in the whole migration. **The token now exists**: `RelationshipID_PrimaryDebtor` was added to `vwHost` variables for the representative swap guard, and reads 1 on dev/uat/testse/v10. File 26 no longer hardcodes it; file 24 still does, so this closes with a one-line sweep |
| **C4** | `Direct/41.tbladdress_relatedparties_mailing.sql:44` | Uses `{{AddressTypeID_Home}}` on a **mailing** address (`:9` splits `RPA.Mailing_Address`). File 42 also uses Home, correctly — so related parties end up with two Home addresses and no Mail address. Compare `38:44`, which does this correctly for the debtor |
| **C5** | `Direct/31.tblcontactdetail_insurance_phone_details.sql:163` | `{{ContactDetailTypeID_Work}}` under the comment `-- Third Party Driver (mobile)`, feeding `I.TPD_Mobile`. Wrong token — mobiles typed as Work |
| **C6** | `Direct/43.tbladdress_insurance_incident.sql:20` | `{{AddressTypeID_Home}}` for an **incident location**. An accident scene is not a residence, and no `AddressTypeID_Incident` exists — any downstream "primary residence" query will pick these up |
| **C7** | ~~`Direct/25:21`, `Direct/26:18`~~ → `Direct/67:14`, `Direct/75:25` | `ISNULL({{EntryTypeID_Treatment}}, -1)` and `ISNULL({{ArrangementTypeID_Deal}}, 1)` — **double-defaulting**. The JSON already applies its own `default` inside the generated query. These are second, independent copies that will silently diverge the moment the JSON changes. The two 3PDM cases were the original finding; the representative rewrite dropped them, leaving these two |
| **C8** | `migration_variables.json:17-21` and `:67-71` | `ContactDetailTypeID_Home` and `ContactDetailTypeID_Work` both declare `"default": 1`. If `vwHost` returns NULL for either, Home and Work phones collapse into a single type |
| **C9** | `migration_variables.json:79-86` | `AddressTypeID_Legal` has `"default": null` → a missing `'Legal'` row in `tblAddressType` inserts `AddressTypeID = NULL` silently instead of failing. It is also the only address type resolved by name lookup, while Home and Mail come from `vwHost` — inconsistent |
| **C10** | Orphaned definitions | Verified as referenced in **0** of the 63 files: `ContactTypeID_InsuredRep`, `RelationshipID_Insured`, `RelationshipID_InsuredRep`, `RelationshipID_InsuredDriver`, `RelationshipID_ThirdPartyDriver`, `RelationshipID_ThirdPartyOwner`, `RelationshipID_ThirdPartyInsurer`, `BankTransactionMethodID_DirectPayment` (see C1). Files 30 and 40 create the insurance-party contacts and addresses but **never write `tblAccount_Contact` rows for them**, so the six relationship constants have no consumer |

### Class D — Structural / environment

| # | Location | Problem |
|---|---|---|
| **D1** | `30`, `31`, `35`, `40`, `43`, `45`, `50` | The `Z_REF2` role-suffix contract — `'*INS'`, `'*IPR'`, `'*IPD'`, `'*TPD'`, `'*TPO'`, `'*TPI'`, `'*INC'` — magic strings spread across 7 files with no shared definition. **The cast type differs per file:** `CAST(… AS NVARCHAR)` (30, no length → defaults to 30), `nvarchar(10)` (35), `VARCHAR` (40, 43, 45, 50) — a latent join-mismatch bug on the same key. **Two gaps:** no `'*IPR'` contact is ever inserted by 30, though `31:82`, `35:37` and `40:52` all consume it (three unreachable UNION branches); and 40 has no `'*TPI'` address block despite 30/31/35 handling that party |
| **D2** | `04`, `29`, `32`, `33`, `37-39`, `41`, `42`, `78` | The pipe `'\|'` delimiter as a bare literal, plus **three different split helpers for one concept**: `STRING_SPLIT(x,'\|')` (29, 32, 33), `dbo.fnSplitTextIntoTable(x,'\|')` (04, 78 ×3), `dbo.fnPipeDelimitedStringIntoTable(x)` (31:79) |
| **D3** | `37`, `38`, `39`, `41`, `42` (`:17-22` in each) | The positional layout of the legacy pipe-delimited address — `RowNum = 1 → address, 4 → suburb, 5 → state, 6 → postcode` — duplicated verbatim in 5 files. If the legacy export ever emits 5 or 7 segments, all five silently mis-map state into suburb |
| ~~**D4**~~ | ~~`Direct/01:80`, `Loop/78:323`~~ | **FIXED** — was `CSRC_OperatorContactMapping`, a **customer-specific** table name (`CSRC` = a customer code) baked into shared SQL, joined in **seven** files (`01`, `49`, `58`, `60`, `64`, `65`, `67`), not the two originally recorded. Those seven now read `tblContact` directly via `OUTER APPLY`, against an operator column rewritten in place from `variables/operator_contact_codes.json` before the batch runs. The dead join in `78` is deleted. See A18. (`SQL/Procedures/DT Migration.sql:344` still names the table — that is the pre-refactor monolith, not the file-based pipeline) |
| **D5** | all 63 files | Legacy staging table names as bare literals (`RC_ACCOUNT_EXTRACT`, `RC_DEBTOR`, `RC_DRINSURANCE`, `RC_DRDBINVOICE`, `RC_DRMEDINV`, `RC_RELATEDPARTY`, `RC_DEAL`, `RC_ARRANGEMENT`, `RC_COSTS_EXTRACT`, `RC_NOTES_EXTRACT`), and **no `dbo.` schema prefix on target tables** — an implicit default-schema dependency throughout. Re-pointing to a different staging schema means editing every file |
| **D6** | truncation lengths | `01:43` `LEFT(…,250)`, `01:61` `LEFT(…,30)`, `45:25` `LEFT(…,500)`, `56:15` `LEFT(…,500)`, `04:7-9` `VARCHAR(100/500/20)`, `76:344-345` `NVARCHAR(100)` staging columns fed from a pipe-delimited multi-value list then copied into `VARCHAR(MAX)` — a 100-char funnel that can silently truncate |
| **D7** | `66:37`, `76:453`, `76:481` | `DECLARE @AccountsPerBatch INT = 2000`; progress interval `IF @loopIndex % 1000 = 0` duplicated in two loops. No chunking or cap on the outer loops — one `spAccountCalculateTotals` round-trip per account |
| **D8** | `37-39`, `41`, `42` vs `40`, `43` | Line-ending constant reversed: `CHAR(10) + CHAR(13)` in the first group, `CHAR(13) + CHAR(10)` in the second |
| **D9** | `04:68`, `04:76`, `76:69`, `76:231` | `CONVERT(DATE, …, 120)` — ODBC canonical date style as a bare literal, i.e. an undocumented source-format assumption |
| **D10** | `Loop/76:78,85,240,247` vs `:444,476` | Stored-procedure names inconsistently qualified: `spArrangement_ReminderMethodSave` unqualified, `dbo.spAccount_Contact_CorrespondenceRecalculate` and `dbo.spAccountCalculateTotals` qualified. Unqualified calls cost a plan-cache lookup per execution |
| **D11** | `Loop/76:152-153`, `:213` vs `:360` | Two different account-key conventions in one file: joins on `Extended_Debt_Code` at `:152/:213`, on `Debt_Code` at `:360` |

---

## §3 Non-mapping defects found in passing

Not config issues — logged here so they are not lost. Triage separately from the mapping work.

| Location | Defect |
|---|---|
| ~~`Direct/01:67-71`~~ | **FIXED** — was `CROSS APPLY` (not `OUTER APPLY`) on `tblAccountStatus`, dropping any account whose `MA_Status` had no matching row and making the `ISNULL(…, {{AccountStatusID_Creation}})` fallback at `:41` dead code. Now `OUTER APPLY`, so the fallback is live and an unmappable status costs the status, not the account. Measured on uat before the fix: 22 accounts dropped, all of which also failed retention, so the observed impact was zero — it was latent, not active |
| `RC_ACCOUNT_EXTRACT.MA_Status` | Four source values have no `tblAccountStatus` row: `DSPT` (17 rows on uat), `OVERSEAS` (2), `PART9` (2), `PARTW/OF` (1). Every other value in the extract is a full label (`Statute Barred`), so these look like raw Debtrak codes the source did not expand. Before the `Direct/01` fix these accounts were dropped; now they land on the creation status. Mapping them is a data task, not a code one — plausible targets exist (`Account in Dispute`, `Debtor Living Overseas`, `Part IX Debt Agreement`) but must be confirmed, not inferred |
| `Direct/47:7,15,23` | Three `CROSS APPLY`s — a contact lacking **any one** of email / phone / address gets **none** of the three primary IDs set. Given 29/32 only create Mobile rows, most insurance-party contacts are skipped entirely |
| ~~`Loop/78:311-315`~~ | **FIXED** — same defect as `Direct/01`, same lookup table: `CROSS APPLY` silently dropped unmapped status-history audit rows. Now `OUTER APPLY` with `ISNULL(…, {{AccountStatusID_Creation}})`, which is mandatory here because `tblWorkflowLineAudit.AccountStatusID` is `NOT NULL` (unlike `tblAccount.AccountStatusID`, which is nullable). `TOP 1` with no `ORDER BY` is left as-is: `tblAccountStatus.AccountStatus` has no duplicate labels, so it is deterministic today |
| `Loop/07:21` | The `NOT EXISTS` de-dupe compares `MetaValue_AccountSpecificsGroupID` (a surrogate PK) against `{{AccountSpecificsGroupID}}` (a MetaField group ID). The inserted column is `MetaField_AccountSpecificsGroupID`. The guard is meaningless — it can both false-positive-skip and fail to de-dupe |
| `Loop/78:191` | `DECLARE @arSMS NVARCHAR(1)` holds the SMS **mobile number** (`:249` passes it as `@Value`). The equivalent first loop uses `NVARCHAR(500)` at `:29`. Every RC_ARRANGEMENT SMS reminder is saved with a 1-character phone number |
| ~~`Direct/72:52`~~ | **FIXED** — was `DC.[SMS_Key] [int] ,`, a stray `[int]` left over from a DDL paste that aliased the column as `int`. Harmless in an `INSERT … SELECT`, where aliases are ignored and columns bind positionally, so this was cosmetic. The real defect it was hiding was not: `RC_DEBT_CONTACTS` had no `SMS_Key` column at all, so the whole statement failed on `Invalid column name`. The column is now in the schema file and the alias is gone |
| `Direct/65` | The `tblCorrespondenceHistory` insert has **no `NOT EXISTS` dedup guard**, unlike 58/60/73. Re-running duplicates rows |
| `Direct/57:27` | Joins `tblCost` on `AccountID` only — fans out one allocation row per cost row per payment |
| `Direct/73` | The `tblCallHistory` insert sets no `CreateID`/`CreateSessionID` at all, unlike every sibling |
| `Direct/52` | Statement 1 (`:1-18`) has no terminating `;` before the second INSERT |
| `Direct/75` | No `InvoiceStatusID` populated; `InvoiceTotal` is `NULL , --RC TO Provide Field`. `LEFT JOIN tblAccount` at `:33` is negated by `WHERE A.LoadID` at `:34` (effectively an inner join) |
| ~~`35.` filename collision~~ | **FIXED** — `35.Update_tblAccount_name.sql` is now `77.Update_tblAccount_name.sql`, the last file before the loop file, so the sequence is unique and the name update runs after every contact insert rather than in a sort-dependent position. No file reads `tblAccount.AccountName`, so nothing between the old and new position depends on it |
| `Direct/77.Update_tblAccount_name.sql:4-10` | Picks the lowest `ContactID` with **no `RelationshipID = 1` filter**. After 25-30 add 3PDM reps, insureds and related parties, an account can be named after a witness or an insurer. `:5` also formats as `FirstName + ' ' + LastName`, which yields an empty string for entity contacts that carry `EntityName` |
| `Direct/44:4` | `WITH (ROWLOCK)` on the read side of a `LEFT JOIN` to a lookup table — almost certainly unintended |
| `Direct/50:28`, `72:63` | `GETDATE()` for `CreateTS` where sibling files preserve the source timestamp |
| `Direct/76:37`, `Loop/78:136` | Arrangement status tested against `GETDATE()` rather than a fixed load date — non-deterministic across a long run |

---

## §4 Per-file coverage

Domain tokens only; `{{LoadID}}`, `{{CurrentSessionID}}` and `{{EntityID}}` are runtime values and excluded. Rating: **Clean** = nothing to extract; **Partial** = uses tokens but has findings; **None** = no domain tokens at all.

| File | Domain tokens used | A | B | C | D | Rating |
|---|---|:-:|:-:|:-:|:-:|---|
| `Direct/01.tblaccount` | `AccountStatusID_Creation` | – | 2 | – | 2 | Partial |
| `Direct/02.tblWorkflowLine` | – | – | 2 | – | 1 | None |
| `Direct/03.tblprincipal` | – | – | 2 | – | 1 | None |
| `Direct/04.getmedinv_for_tblprincipal` | – | – | 2 | – | 3 | None |
| `Loop/06.tblentity_AccountSpecifics` | `AccountSpecificsGroupID` | – | 3 | – | – | Partial |
| `Loop/07.tblMetaValue_AccountSpecificsGroup` | `AccountSpecificsGroupID` | – | 2 | – | 1 | Partial |
| `Loop/08.tblaccountSpecifics` | `AccountSpecificsGroupID` | – | 2 | – | – | Partial |
| `Direct/22.tblcontact` | `ContactTypeID_Individual`, `_Entity` | 2 | 3 | – | – | Partial |
| `Direct/23.tblcontactaudit` | `ContactTypeID_Individual`, `_Entity` | 1 | 3 | – | – | Partial |
| `Direct/24.tblaccount_contact` | – | – | 3 | **1** | – | None |
| `Direct/25.tblcontact_thirdpartycontacts` | `ContactTypeID_3PDM` | 1 | 4 | – | – | Partial |
| `Direct/26.tblaccount_contact_thirdpartycontacts` | `ContactTypeID_3PDM`, `RelationshipID_3PDM`, `_3PDM_Adhoc`, `_PrimaryDebtor`, `SecondaryRelationshipID_3PDM` | 1 | 6 | – | – | Partial |
| `Direct/27.tblcontact_related_parties` | `ContactTypeID_Individual`, `_Entity` | 1 | 4 | – | – | Partial |
| `Direct/28.tblaccount_contact_related_parties` | 7 × `RelationshipID_*` | **1** | 2 | – | – | Partial |
| `Direct/29.tblcontactdetail_phonenumbers_for_related_party` | `ContactDetailTypeID_Mobile` | **1** | 2 | – | 1 | Partial |
| `Direct/30.tblcontact_insurance` | 5 × `ContactTypeID_*` | 1 | 4 | – | **1** | Partial |
| `Direct/31.tblcontactdetail_insurance_phone_details` | `ContactDetailTypeID_Mobile`, `_Home`, `_Work` | – | 2 | **1** | **2** | Partial |
| `Direct/32.tblcontactdetail_create_phone_details` | `ContactDetailTypeID_Mobile`, `_Home`, `ContactTypeID_3PDM` | **1** | 4 | – | 1 | Partial |
| `Direct/33.tblcontactdetail_create_email_details` | `ContactDetailTypeID_Email` | – | 2 | – | 1 | Partial |
| `Direct/34.tblcontactdetail_create_email_details_relatedparties` | `ContactDetailTypeID_Email` | – | 2 | – | – | Partial |
| `Direct/35.tblcontactdetail_create_email_insurance` | `ContactDetailTypeID_Email` | 1 | 2 | – | **1** | Partial |
| `Direct/36.tblcontactdetailaudit` | – | – | 3 | – | – | None |
| `Direct/37.tbladdress_street` | `AddressTypeID_Home`, `DefaultCountryID` | – | 3 | – | 3 | Partial |
| `Direct/38.tbladdress_mailing` | `AddressTypeID_Mail`, `DefaultCountryID` | – | 3 | – | 3 | Partial |
| `Direct/39.tbladdress_legal` | `AddressTypeID_Legal`, `DefaultCountryID` | – | 3 | **1** | 3 | Partial |
| `Direct/40.tbladdress_insurance` | `AddressTypeID_Mail`, `DefaultCountryID` | 1 | 3 | – | **2** | Partial |
| `Direct/41.tbladdress_relatedparties_mailing` | `AddressTypeID_Home`, `DefaultCountryID` | – | 3 | **1** | 3 | Partial |
| `Direct/42.tbladdress_relatedparties_street` | `AddressTypeID_Home`, `DefaultCountryID` | – | 3 | – | 3 | Partial |
| `Direct/43.tbladdress_insurance_incident` | `AddressTypeID_Home`, `DefaultCountryID` | – | 3 | **1** | 2 | Partial |
| `Direct/44.tbladdress_Assign_StateID` | – | **1** | – | – | – | None |
| `Direct/45.tblaccountincident` | – | **1** | 2 | – | 2 | None |
| `Direct/46.tbladdressaudit` | – | – | 1 | – | – | **Clean** (exemplar) |
| `Direct/47.tblcontact_update_contactdetailid` | – | – | **3** | – | – | None |
| `Direct/48.tblbanktransaction` | `BankAccountID_DefaultHost` | – | 4 | – | – | Partial (exemplar) |
| `Direct/49.tblpayment` | – | **1** | 3 | – | – | None |
| `Direct/50.tblaccountInsurance` | – | – | 3 | – | 2 | None |
| `Direct/51.tblcosts` | – | **2** | 4 | – | – | None |
| `Direct/52.tblTimeOnAccount_resultcode` | – | – | 3 | – | 2 | None |
| `Direct/53.tblallocation_principals` | – | – | 3 | – | – | None |
| `Direct/54.tblIncidentPolice` | – | – | 3 | – | – | None |
| `Direct/55.tblallocation_overpayments` | – | – | 3 | – | – | None |
| `Direct/56.tblIncidentWitness` | – | – | 2 | – | 1 | None |
| `Direct/57.tblallocation_costs` | – | – | 3 | – | – | None |
| `Direct/58.tblsmsoutput` | – | 3 | 4 | – | – | None |
| `Direct/59.tblcommunication_emails` | – | – | 2 | – | – | None |
| `Direct/60.tblemail` | – | **3** | 4 | – | – | None |
| `Direct/61.tblcommunication_dochist` | – | 1 | 3 | – | – | None |
| `Direct/62.tblcommunication_contact_dochist` | – | 1 | 4 | – | – | None |
| `Direct/63.tblmetavalue_documentgroup` | – | 1 | 3 | – | – | None |
| `Direct/64.tbldocument` | – | 1 | 3 | – | – | None |
| `Direct/65.tblletter` | – | 3 | 5 | – | – | None |
| `Direct/67.tblentry_notes` | – | – | 3 | **1** | 1 | None |
| `Direct/68.tblentry_treatments` | `EntryTypeID_Treatment` | 1 | 3 | – | – | Partial |
| ~~`Direct/69.rc_staging_treatments`~~ | – | – | – | – | – | **Removed from the pipeline** (was clean, and the exemplar cited below) |
| `Direct/70.tblentry_resultcodes` | `EntryTypeID_Result` | 1 | 3 | – | – | Partial |
| `Direct/71.tblproofofidentity` | – | 1 | 2 | – | – | None |
| `Direct/72.tblDebtContact` | – | 1 | 2 | – | 1 | None |
| `Direct/73.tblCallHistory` | – | **3** | 3 | – | – | None |
| `Direct/74.tblaccount_update_debtcontact` | – | 1 | 2 | – | – | None |
| `Direct/75.tblinvoice` | – | **1** | 3 | – | – | None |
| `Direct/76.tblarrangement` | `ArrangementTypeID_Deal` | 2 | 2 | **1** | – | Partial |
| `Direct/77.Update_tblAccount_name` | – | 1 | – | – | – | None |
| `Loop/78.final loops and sps to run` | – | **3** | **5** | – | **5** | None |

**Totals:** 63 files — 28 use at least one domain token, **35 use none**. 2 files are Clean.

**Exemplars to copy:**
- `46.tbladdressaudit.sql` and `69.rc_staging_treatments.sql` — both carry `CreateID`, `CreateSessionID`, `StatusID` and type IDs through **from the source row** instead of re-hardcoding them. This is the pattern 23 and 36 should follow. (`69` has since been removed from the pipeline; it remains the clearest illustration of the pattern, and is recoverable from git history.)
- `48.tblbanktransaction.sql` — correct `{{BankAccountID_DefaultHost}}` usage.
- `28.tblaccount_contact_related_parties.sql` — best-tokenised targets in the set (7 relationship tokens), even though its legacy code list is still hard (A6).

---

## §5 Phased remediation plan

### Phase 0 — free wins
No business input, no new infrastructure, no new variables. All are drop-in.

| Item | Change |
|---|---|
| C1 | `75:29` → `{{BankTransactionMethodID_DirectPayment}}` (already defined, currently unused) |
| C4 | `41:44` → `{{AddressTypeID_Mail}}` |
| C5 | `31:163` → `{{ContactDetailTypeID_Mobile}}` |
| C7 | `25:21`, `26:18` → drop the redundant `ISNULL(…, 5)` / `ISNULL(…, 11)` literals |
| C8 | `migration_variables.json:67-71` → give `ContactDetailTypeID_Work` a default distinct from Home |
| C9 | `migration_variables.json:79-86` → give `AddressTypeID_Legal` a non-null default, or make a miss fail loudly |
| B5 | `76:78,85,240,247` → `{{CurrentSessionID}}` |
| ~~D4~~ | ~~`76:323` → delete the dead `CSRC_OperatorContactMapping` join~~ **Done**, as part of A18 — the join is deleted and the other seven sites now read `tblContact` directly |

### Phase 1 — new scalar tokens
Add to `constant_variables` / `lookup_variables` and sweep the SQL. Covers **B1, B2, B3, B4, B6, B7, B8** plus **C2** (`EntryTypeID_Note`), **C3** (`RelationshipID_PrimaryDebtor`), **C6** (`AddressTypeID_Incident`).

Touches ~130 sites. **Do one reviewable pass per token, not per file** — a single sweep across 63 files is unreviewable, and `{{SystemUserID}}` (B1) and `{{StatusID_Active}}` (B2) alone account for most of the volume.

Also decide during this phase whether to resolve **C10** by wiring the six orphaned insurance `RelationshipID_*` constants into new `tblAccount_Contact` inserts, or by deleting them as dead config. Right now files 30/40 create the parties but never relate them to the account, so the constants have no consumer either way.

### Phase 2 — new code-mapping domains
Each follows the 8-step scaffold in §1. **Business sign-off on the values is a prerequisite for every one of these.** Priority order reflects data-correctness impact:

1. ~~**A1**~~ — frequency. **Done.** Two follow-ups it carries:
   - **DDL prerequisite:** `RC_ARRANGEMENT.Frequency` ships as `NVARCHAR(10)`, but the canonical label `Fortnightly` is 11 characters, so the in-place rewrite cannot fit. `SQL/Schemas/RC_ARRANGEMENT Schema.sql` has been widened to `NVARCHAR(100)` (matching its already-rewritten siblings `Arrangement_Type` and `Payment_Method`), but that file is manual DDL — **apply it, or run `ALTER TABLE RC_ARRANGEMENT ALTER COLUMN Frequency NVARCHAR(100) NOT NULL;`, before the next load.** `FrequencyService.check_source_column_fits` fails loudly with that exact ALTER if it has not been applied.
   - **Label confirmation:** `variables/frequency_codes.json` assumes the `tblFrequency` labels are `Weekly / Fortnightly / Monthly / Bi-Monthly / Quarterly / Yearly`. These were inferred from the IDs the old CASE produced (2/3/4/7/12/5) and are **not yet verified against the database.** If any differ, the check step names the unmatched value and the fix is a JSON edit only.
2. ~~**A5**~~ — incident type. **Done.** `tblIncidentType` labels (`Theft / Fire / Flood / Damage / Property`) were inferred from the IDs the old CASE produced (2/3/4/8/9) and are **not yet verified against the database**; if any differ the step fails loudly naming the label, and the fix is a JSON edit.
3. ~~**A14**~~ — state synonyms. **Done**, post-batch. See the A14 row above.
4. ~~**A6**~~ — related-party types. **Done.** `tblRelationship` labels were inferred from the `constant_variables` IDs (Guarantor 19, Additional Card Holder 21, Spouse 2, Reference 20, Solicitor 6, Witness 17, Other 22) and are likewise unverified. Note `RC_RELATEDPARTY` has no schema file in `SQL/Schemas/`, so `Related_Party_Type_Code`'s width could not be checked statically — the service pre-flights it at runtime and fails with the required `ALTER` if the canonical labels will not fit.
5. **A15** — `76.tblarrangement.sql:40` still hardcodes `FrequencyID` to `NULL` for deals. `RC_DEAL` has no frequency column, so this needs a business decision rather than a mapping; not resolved by A1.
6. ~~**A3 + A4**~~ — cost codes. **Done**, and it was not only hardcoding: the `CSRC_CostTypeMapping` `INNER JOIN` this document had recorded as already correct was dropping every `COL` charge in the load. See A3. What it leaves for the business:
   - **The 31 codes still on `MERCANTILE`.** `CSRC_CostTypeMapping` mapped all 56 of its codes to `CostTypeIDDestination` 1 regardless of the cost, so those 31 preserve today's behaviour rather than assert anything. 25 were re-categorised where the RCS fee name has one unmistakable `tblCostType` counterpart; the rest had two or more plausible targets (`ADM`: ADMIN FEE RECOVERY vs ACO ADMIN; `AFF`/`BAR`: PROFESSIONAL COSTS vs SOLICITORS COSTS; `ARC`/`AHF`/`LIST`: ADMIN FEE RECOVERY vs RECOVERY FEE vs COMMISSION) or none at all (`DEBR`, `DEBW`, `CLC`, `SAP`, `UIL`). `cost_codes.json` records the reasoning per group.
   - **Do not try to derive these by joining `CSRC_CostTypeMapping.CostType` to `tblCostType.CostType`.** Measured: **0 of 56 match** on the repo's own `match_key` normalisation. They are different vocabularies — RCS fee names (`SEARCH FEE - RECOVERABLE`, `BARRISTER FEE`) against DT categories (`SEARCH FEES`, `PROFESSIONAL COSTS`). Every one of the 56 is a per-code decision, which is why they were all left at 1.
   - **The table is still the code inventory**, though, and `tools/build_cost_codes.py` reconciles `cost_codes.json` against it — read-only by default, `--write` to add newly catalogued codes and refresh the RCS descriptions, never overwriting a recorded decision. It is a three-way comparison (catalogued codes / `Chg_` columns that can hold money / what the JSON decides) and **a column in the third group but neither of the first two is precisely what `COL` was**, so this is the standing check against a repeat. It also prints the re-categorisation review list with descriptions attached, which is the artefact the sign-off above actually needs.
   - **`COL`'s cost type** is `ADMIN FEE RECOVERY`, because that is `tblMasterCost[12].CostTypeID` for the "Collection Costs" master cost the old CASE already routed `COL` to — a one-line JSON change if the business wants `MERCANTILE` or `COMMISSION` instead.
   - **`IBS` / `IAJ`** are deliberately left undecided, as is every `Chg_` column the old CROSS APPLY never read (`IBJ`, `ACOM`, `INT`, `BCOM`, `PMA`, `LATE`, `AKF`, `EST`, `BRE`, `DAR`). None carries a charge in any load seen so far, so there was nothing to infer a cost type from; if one ever does, the step stops the customer and names it rather than dropping it.
7. ~~**A18**~~ — operator contacts (**D4**). **Done.** `CSRC_OperatorContactMapping` is gone from all seven consumers. `operator_contact_service.py` rewrites each extract's operator column in place to the canonical `tblContact.UserName` from `variables/operator_contact_codes.json` (`{tblContact.UserName: [operator codes]}`), and the seven files read `tblContact` directly with `OUTER APPLY (SELECT TOP 1 …)`. **No DDL and no new table** — an operator code is an ordinary value, so the MA_Status/Payment_Method mechanism applies; costs needed their own table only because a cost code is part of a *column name*. `OUTER APPLY` rather than `LEFT JOIN` because `UserName` is not unique. What it leaves for the business:
   - **Unlisted is safe here, unlike costs.** A code with no entry falls to `ISNULL(OM.ContactID, {{DefaultOperatorContactID}})`, and a code that already *is* a username resolves with no entry at all. The file is therefore **added to as needed**, like `account_status_codes.json`, rather than being a complete inventory — the check names the unresolved codes it finds, busiest first, and a human adds the ones for which the fallback is wrong.
   - **The fallback is now `PRAM`, not `admin`.** `DefaultOperatorContactID` is a new `lookup_variables` entry resolving `tblContact.UserName = 'PRAM'` per environment (197 on testse), with the configured `default` of `1` if that username is absent. This **changes today's behaviour for the unresolved tail** — 3.26M rows move from `admin` to `PRAM`, the contact `CSRC_OperatorContactMapping` pointed all 20 of its rows at. One `filter_value` reverts it.
   - **The scale of that.** Measured on testse: the extracts carry **564 distinct operator codes** and `CSRC_OperatorContactMapping` had **20**. Only **7** of the 564 are already a `tblContact.UserName` (11,940 rows, resolving to the obvious person); the other **557** (3.26M rows) match nothing and were already falling through to `admin`, including `APP` (532,345 note rows) and `AUSUVA` (14,102 account rows — i.e. every account's `AccountManager_ContactID`). Pre-existing behaviour, not a regression, but it is the real size of the mapping decision.
   - ~~**Note islands.**~~ **No longer applicable, and nothing to re-measure.** This used to read: `66.RC_STAGING_NOTES.sql` breaks islands on `(Extended_Debt_Code, Date_Entered, Operator)` and this rewrite runs before it, so codes collapsed onto one username could weld two notes together (measured for the current 20: **0** at-risk `(debtor, timestamp)` groups, with `REMOTE`, `EOD` and `SMS` the members that would have mattered). That file is deleted. Notes are folded by `notes_consolidation` during the staging load, which runs *before* this rewrite, so islands break on the original codes and no collapse can reach them. `67` no longer resolves an operator per note either — a consolidated entry has no single author and takes `DefaultOperatorContactID` — so adding codes here has no effect on `tblEntry` for notes. The operator survives only as display text in a note header, deliberately as the original legacy code: six of the 20 (`AUTOLOAD`, `EDO`, `EOD`, `IVRU`, `REMOTE`, `SMS`) are automation, and showing a person's username above a machine-written note would be worse than showing the code.
   - **The 20 codes on `PRAM`.** All 20 rows of the table pointed at `ContactID 197` (Prashant Mathur) whatever the operator code was, the same placeholder shape as the 31 MERCANTILE cost codes. Preserved, pending sign-off.
   - **Eight of them are exact `tblContact.UserName` values for other people** — `AKSJ`, `AMRA`, `MARC`, `MURK`, `RUSW`, `SABS`, `SHEL`, `SUZC`. Re-pointing each at its own contact is almost certainly intended but **changes who migrated rows are attributed to**, so it is a sign-off item, not a code change. Three more (`ABHV`, `ADIU`, `SRAV`) are one character from a real username and were deliberately left alone.
   - **`tblContact.UserName` is not unique** (4,670 populated / 4,099 distinct on testse). Resolution prefers the active contact, then the lowest `ContactID`, and the check names any username that needed the tie-break.
8. **A7 / A8** — call types
9. **A13** — phone-prefix classification
10. **A2, A9–A12, A16, A17** — the remainder, once the above land

**Where each transform runs.** Nine of the ten run before the SQL batch, in `customer_sql_workflow_service.execute_mixed_sql_methods`, ahead of the `GATE_SQL` approval: status → payment method → arrangement type → frequency → related party type → incident type → closure reason → cost codes → operator contacts. **State is the exception** and runs after `execute_sql_files_step`, because the column it corrects does not exist until the batch has created it. A state failure is logged and reported but does not fail the customer — it leaves `StateID` NULL, which is exactly the pre-existing behaviour.

**How each treats an unmapped value**, which is the distinction that matters when reading the check output:

| Domain | Unmapped value | Why |
|---|---|---|
| Cost codes | **Fatal** — stops the customer | An `INNER JOIN` dropped the money silently; $403,234.13 of `COL` charges vanished on dev load 238 |
| Operator contacts | **Reported** — customer continues | `ISNULL(…, {{DefaultOperatorContactID}})` attributes the row to the fallback contact; nothing is lost, and 557 of 564 codes take that path |
| State | **Reported** — customer continues | Leaves `StateID` NULL, the pre-existing behaviour |
| The rest | **Reported**, some with a configured fallback label | An unmapped value costs a label, not a row |

### Phase 3 — structural
**D1** (one shared definition for the `Z_REF2` suffix contract, one consistent cast type, and close the `'*IPR'` / `'*TPI'` gaps) → **D2 / D3** (one split helper, one address-layout definition) → **D5** (staging table and schema tokens) → **D6–D11**.

### Phase 4 — defect triage
Work the §3 list. Sequence it independently of the mapping work; several items (the `CROSS APPLY` data loss in `01`, `47` and `76:318`, and the `Loop/76:191` `NVARCHAR(1)` truncation) are losing rows or corrupting values on every run and may warrant jumping ahead of Phases 1–3.

---

## Appendix — verification performed

Claims in this document were checked directly, not inferred:

- **File count** — `Get-ChildItem "SQL/Migration queries/Direct","SQL/Migration queries/Loop" -Filter *.sql` → 59 + 4 = **63**.
- **Unused tokens (C1, C10)** — regex `\{\{<name>\}\}` across all 63 files returned **0 matches** for all 8 names listed. Control names in the same sweep returned the expected 1 match each (`EntryTypeID_Treatment` → 67, `EntryTypeID_Result` → 69, `ArrangementTypeID_Deal` → 75, `BankAccountID_DefaultHost` → 48, `AccountStatusID_Creation` → 01).
- **§4 token column** — extracted programmatically with `[regex]::Matches($content, '\{\{(\w+)\}\}')` per file, with the three runtime tokens filtered out. Not hand-transcribed.
- **Mechanism description (§1)** — read against `DT_query_processor.py:413-469` and `config_parser.py:107-204, 261-272`. The `LEFT JOIN` hardcoding at `config_parser.py:128` and the ignored `query_template` keys were confirmed in source.
