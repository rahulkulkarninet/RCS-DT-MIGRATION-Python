# Symbos RCS-DT Migration System

## Overview

The Symbos RCS-DT Migration System is a Python based data migration tool designed to transfer and transform customer data from RCS to DT. The system processes financial and accounting data through a staged migration approach, ensuring data integrity and providing comprehensive logging and metrics.

## Architecture

### Core Components

- **`Run_Migration.py`** - Main entry point that orchestrates the entire migration process
- **`customer_processor.py`** - Facade/orchestrator for customer-by-customer processing with the `CustomerProcessor` class
- **`services/`** - Service-layer implementations used by `CustomerProcessor` for focused workflow responsibilities
- **`process_staging.py`** - Manages staging file processing via the `StagingProcessor` class
- **`staging_archive.py`** - The staging archive: `StagingArchiver` copies rows into the archive
  database on every run, `ArchiveSchemaProvisioner` creates the tables it copies into as a one-off
  setup step
- **`DT_query_processor.py`** - Executes SQL migrations using the `SQLMigrationManager` class
- **`config_parser.py`** - Configuration management through the `ConfigParser` class
- **`db_manager.py`** - Database connection and transaction management
- **`memory_manager.py`** - Memory monitoring and optimization

## Directory Structure

```
├── Run_Migration.py          # Main migration script
├── Run_Migration.bat         # Windows batch file to execute migration
├── customer_processor.py      # Orchestrator facade for migration flow
├── services/                  # Service-layer package (canonical implementations)
│   ├── io/                    # File/logging services
│   ├── workflows/             # Staging/status/sql/summary workflow services
│   ├── setup/                 # Migration setup/session/load services
│   ├── execution/             # SQL execution internals
│   ├── orchestration/         # Customer lifecycle orchestration service
│   └── *.py                   # Compatibility shims for legacy service imports
├── requirements.txt          # Python dependencies
├── config/                   # Environment configurations
│   ├── uat.env              # UAT environment settings
│   └── v10.env              # V10 environment settings
├── column mapping/           # CSV column mapping files
│   ├── RC_ACCOUNT_EXTRACT.csv
│   ├── RC_ARRANGEMENT.csv
│   ├── RC_COSTS_EXTRACT.csv
│   ├── RC_DEAL.csv
│   ├── RC_DEBT_CONTACTS.csv
│   ├── RC_DEBTOR.csv
│   ├── RC_DOCHIST_EXTRACT.csv
│   ├── RC_DRDBINVOICE.csv
│   ├── RC_DRDEBTINFO.csv
│   ├── RC_DRDEBTORAUD.csv
│   ├── RC_DRMEDINV.csv
│   ├── RC_EMAIL_EXTRACT.csv
│   ├── RC_NOTES_EXTRACT.csv
│   ├── RC_PAYMENTS.csv
│   ├── RC_POI.csv
│   ├── RC_SMS.csv
│   ├── RC_STATEMENT.csv
│   └── RC_TREATMENT.csv
├── SQL/                      # Migration SQL scripts
│   ├── Migration queries/    # Migration SQL files organized by type
│   │   ├── Direct/          # Direct migration queries
│   │   ├── Exclude/         # Exclusion queries
│   │   ├── Loop/            # Loop-based queries
│   │   └── Metavalue_AccountSpecifics/
│   ├── Procedures/          # Procedures
│   │   ├── DT Delete Migrated Data.sql
│   │   ├── DT Migration - Entity and LoadID.sql
│   │   ├── DT Migration - Table Check.sql
│   │   └── DT Migration.sql
│   └── Schemas/             # Table schema definitions
└── variables/                # Migration variable definitions
    ├── migration_variables.json
    ├── path_config.json
    ├── processing_stats_metrics.json
    ├── schema_sets.json
    ├── staging_metrics.json
    └── table_keywords.json
```

## Features

- **Multi-Environment Support**: Configurable for different environments (UAT, V10)
- **Customer Isolation**: Processes data customer-by-customer to ensure data integrity
- **Memory Management**: Built-in memory monitoring to handle large datasets efficiently
- **Transaction Safety**: SQL execution with rollback capability
- **Comprehensive Logging**: Detailed logging of all migration activities
- **Metrics Collection**: Performance and success metrics tracking
- **Staged Processing**: Data validation through staging tables before final migration
- **Column Mapping**: Flexible CSV-based column mapping for data transformation

## Installation

1. **Clone the repository**

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**
   - Update environment files in `config/` directory
   - Set database connection parameters
   - Configure migration paths and settings

## Configuration

### Environment Files
Environment configurations are stored in the `config/` directory:
- `uat.env` - UAT environment settings
- `v10.env` - Production V10 settings

Optional keys:
- `ARCHIVE_DATABASE` - database on the same server that `tools/sweep_archive.py` moves archived
  tables on to. Named per environment (`test-migration-data` on testse, `dev-migration-data` on
  uat); an env file that omits it falls back to `migration_data`. A migration run never connects
  to it - the archive step renames tables within the run's own database, and the sweep is what
  crosses into this one.

### Schema deployment (once per environment, and after a schema change)

A run refuses to start if a staging table is missing, and deploys none of them itself.
`tools/deploy_schemas.py` runs a named set of `SQL/Schemas/` files against one environment's
connection. The sets live in `variables/schema_sets.json`:

| Set | What it deploys |
| --- | --- |
| `staging` (default) | every table a run needs - the `table_keywords.json` extracts plus `RC_STAGING_COSTS` and `RC_STAGING_NOTES_ACCOUNT` |
| `support` | `RC_Entity_Mapping`, `RC_PaymentMethod_Mapping`, `RC_Processing_Stats` - all protected, see below |
| `migrations` | the additive, re-runnable `Migrations/001-003` and `006` (the archive schema) |
| `new-environment` | `staging` + `support` + `migrations`, in that order |

Three files in `SQL/Schemas/` are in no set on purpose: `tblentity_product Schema.sql` changes the
DT target schema rather than staging, and `RC_STAGING_TREATMENTS` / `RC_STAGING_TREATMENT_LINES`
lost their only writer when `69.rc_staging_treatments.sql` was deleted. Run one with `--file` if
an old environment ever needs it.

```bash
python tools/deploy_schemas.py <env> --list      # the sets and what is in them
python tools/deploy_schemas.py <env> --dry-run   # the plan, and the rows at risk
python tools/deploy_schemas.py <env>             # run it, after confirming
```

`--set <name>` (repeatable) picks the set, `--file "<name> Schema.sql"` runs individual files,
and `--database <name>` runs them against another database on the same server - the schema files
carry no `USE` of their own. `--config` takes an environment file outside the repo, exactly as the
archive tools do. `--yes` answers the confirmation prompt in advance, which is what an unattended
run needs.

Every one of these files opens with `DROP TABLE`, so this is not a migration tool: it recreates
the table and whatever it held is gone. For the staging extracts that costs nothing - they are
truncated per customer anyway - but `protected_tables` in the set list names the ones where it is
permanent (run history, hand-maintained mappings), and a file that would drop one while it holds
rows is refused unless `--force` says otherwise. The plan printed before the prompt gives the row
count of every table it would drop, so a wrong environment is visible before anything happens.

Batches are split on `GO` the way sqlcmd splits them and committed one at a time. A file that
fails part way is therefore applied as far as the batch that failed; fix the cause and run it
again - the `DROP` guards make that safe - rather than assuming it rolled back.

### Archive

The staging tables are truncated and reloaded per customer, so each customer's raw extract only
exists between its load and the next customer's truncate. The archive keeps it - by moving the
table rather than copying it:

```
dbo.RC_ACCOUNT_EXTRACT  ->  archive.SM9641_RC_ACCOUNT_EXTRACT
```

`sp_rename` plus `ALTER SCHEMA TRANSFER`, then the staging table is rebuilt empty from its own
`SQL/Schemas/` file - all in one transaction, all catalog operations. It costs the same whether the
table holds ten rows or ten million: measured on `dev`, 20 tables and 2,595,695 rows in **0.53s**.

This replaced a bcp copy into a separate database. Azure SQL has no cross-database queries, so
every row had to be read out to the client and pushed back - twice across the WAN, for data the
next truncate was about to discard anyway. Nothing crosses a database now, so nothing has to.

Three consequences worth knowing:

- **The rebuild comes from the schema files, not from `sys.columns`.** Nearly every staging table
  carries join indexes the migration's own queries depend on - `RC_SMS Schema.sql` records that
  losing one "turned a 15 second step into hours". Only the schema file has them, so a table in
  `table_keywords.json` with no file in the `staging` set stops the run at startup.
- **The audit values live in `archive.ArchiveCatalog`**, one row per archived table, not in columns
  on every row. A renamed table cannot gain `LoadID`/`CreateTS`/`EntityCode` columns without an
  `ALTER TABLE ADD` that rewrites it, which would cost exactly what the rename saves.
- **Re-archiving a customer replaces its previous tables.** Latest load wins.

Setup is one step per environment, the archive schema and its catalog:

```bash
python tools/deploy_schemas.py <env> --set migrations
```

To run the archive outside a migration - `--entity-code` is required, since it names the tables:

```bash
python tools/archive_staging.py <env> --entity-code <CustomerCode> --load-id <LoadID> --dry-run
python tools/archive_staging.py <env> --entity-code <CustomerCode> --load-id <LoadID>
```

#### Sweeping to the archive database

A rename cannot cross databases, so archived tables accumulate in the migration's own database -
which is also the DebtRak application database. **Watch its size: filling it takes the application
down, not just the archive.** `tools/sweep_archive.py` is the mitigation and should be scheduled:

```bash
python tools/sweep_archive.py <env> --dry-run
python tools/sweep_archive.py <env> --older-than 30d --workers 4
```

It copies each table to `ARCHIVE_DATABASE` and drops the original - but only after counting the
rows on the far side, so an interrupted sweep simply redoes that table next time. On Azure it uses
native-format bcp (no Python in the data path, and binary columns round-trip); on `dev` and `v10`
it uses a cross-database `INSERT ... SELECT` that never leaves the server. Safe to run while a
migration is in flight: it only touches the `archive` schema, which a run adds to and never reads.

`archive.vw_ArchiveSize` reports what the archive currently holds and how much is unswept.

#### Reconciling staging

`tools/setup_archive.py` compares the staging tables against `variables/schema_sets.json` and
reports what is missing and what is there without being in the set:

```bash
python tools/setup_archive.py <env>            # report only, the default
python tools/setup_archive.py <env> --drop     # remove the strays, after confirming
```

It runs against the application database, so it never works by elimination. `drop_scope` in
`schema_sets.json` declares what the migration owns - `dbo` tables prefixed `RC_`, plus the
`archive` schema - and nothing outside it is a candidate under any flag, or even enumerated.
`protected_tables`, `archive.ArchiveCatalog` and any archive table the sweep has not yet copied
out are refused with no override. If more tables come out droppable than `max_drops` allows it
refuses the whole run, on the grounds that this usually means the schema set failed to load. The
decision is `drop_scope.is_droppable`, which needs no database and is covered by
`tests/test_drop_scope.py`.

### Cost codes (one table to deploy, once per environment)

`RC_COSTS_EXTRACT` carries costs as 71 wide `Chg_<code>` columns, one per cost type on a
single row per debtor. `cost_service.py` unpivots the charged ones into
`RC_STAGING_COSTS` before the migration SQL runs, resolving each code's `CostTypeID`
against `tblCostType` and `MasterCostID` against `tblMasterCost` from
`variables/cost_codes.json`. `51.tblcosts.sql` then reads that table, so adding a cost
code or changing where one lands is a JSON edit rather than a SQL edit.

Deploy the table before the first run in a new environment — the cost step fails with a
message naming this file if it is missing:

```bash
SQL/Schemas/RC_STAGING_COSTS Schema.sql
```

A code listed in neither `cost_types` nor `not_costs` in `cost_codes.json` is treated as
undecided: it migrates nothing, and if its `Chg_` column carries money the step **stops
the customer** rather than dropping the charge. That is deliberate. The previous version
of `51.tblcosts.sql` resolved `CostTypeID` with an `INNER JOIN` to the
`CSRC_CostTypeMapping` reference table, which had no row for `COL` — so on dev load 238
all 11,038 `COL` charges ($403,234.13, of which $358,488.29 was still outstanding) were
dropped with no error at all, `tblCost` came out empty, and the accounts whose `COL`
charge had already been paid finished with a negative balance, because
`49.tblpayment.sql` still copied the payment's `AllocatedCost` across.

`CSRC_CostTypeMapping` is no longer read by the migration, and nothing writes to it. It
is still populated per environment and still read by `SQL/Procedures/DT Migration.sql`,
which is a separate path from the `Direct/` files this pipeline runs. Its own
`CostType` column cannot be matched to `tblCostType.CostType` — they are different
vocabularies (RCS fee names like `SEARCH FEE - RECOVERABLE` against DT categories like
`SEARCH FEES`), and 0 of its 56 rows match by label, which is why the mapping lives in
the JSON as a reviewed per-code decision.

The table is still useful for the two thirds of the domain it does carry — the code
inventory and an RCS description per code — so `cost_codes.json` is reconciled against
it rather than maintained by hand:

```bash
python tools/build_cost_codes.py uat
```

Read-only by default. It compares three sources — the codes `CSRC_CostTypeMapping` has
catalogued, the `Chg_` columns that can actually carry money, and what the JSON decides
— and reports the gaps between them, because that is where the bugs live. **A `Chg_`
column with no mapping row and no JSON entry is exactly what `COL` was**, so running
this would have named it on day one. It also prints the re-categorisation review list
with each code's RCS description, which is what the business needs to sign off the
codes still on MERCANTILE. Exit status is 1 if a charged code has nowhere to go.

`--write` adds newly catalogued codes and refreshes the `code_descriptions` block. It
**never** overwrites a decision: a code already in the file keeps its cost type and
master cost, and a new code is placed under the label its `CostTypeIDDestination`
resolves to, so a generated entry reproduces current behaviour rather than inventing a
category. Re-running it changes nothing.

**Cost types are no longer all MERCANTILE.** `CSRC_CostTypeMapping` set
`CostTypeIDDestination` to 1 (MERCANTILE) for all 56 of its codes regardless of what
the cost was. 25 codes are now categorised properly, where the RCS fee name has one
unmistakable `tblCostType` counterpart — `CRT`→COURT FEES, `SRVI`→INDIVIDUAL SERVICE
FEES, `KIL`→SERVICE KMS, the four `LEGAL COSTS`/`LEGAL DISBURSEMENTS` codes→LEGAL, the
six solicitor codes→SOLICITORS COSTS, and so on. The remaining 31 stay at MERCANTILE
**to preserve today's behaviour, not because they belong there**; they had two or more
plausible targets (`ADM`: ADMIN FEE RECOVERY or ACO ADMIN) or none at all (`DEBR`,
`DEBW`, `CLC`, `SAP`, `UIL`), and await business sign-off. `cost_codes.json` records
which are which and why.

### Operator contacts (nothing to deploy)

Seven files — `01`, `49`, `58`, `60`, `64`, `65`, `67` — attributed each migrated row to
a DebtRak contact by joining `CSRC_OperatorContactMapping`. `CSRC` is a customer code, so
that was customer-specific reference data named in shared SQL: a customer without the
table broke the batch at file 01.

It is now an in-place rewrite, the same mechanism as `MA_Status` and `Payment_Method` and
for the same reason — an operator code is an ordinary value in an ordinary column, so it
can simply be corrected. (Costs needed a staging table only because a cost code is part
of a *column name*, `Chg_ADM`, leaving nothing to rewrite.)
`operator_contact_service.py` rewrites the operator column of each extract to the
canonical `tblContact.UserName` from `variables/operator_contact_codes.json` —
`{tblContact.UserName: [legacy operator codes]}`, the same shape as
`account_status_codes.json` — and the seven files then read `tblContact` directly. No new
table, nothing to deploy.

They read it with `OUTER APPLY (SELECT TOP 1 … ORDER BY …)` rather than a plain
`LEFT JOIN`, because `UserName` is **not unique** — 4,670 populated values cover 4,099
distinct ones on testse, so a `LEFT JOIN` would fan out rows. An active contact wins,
then the lowest `ContactID`; the check names any username that needed that tie-break
rather than resolving it quietly. `01.tblaccount.sql` already used the same idiom for
`tblAccountStatus` and `tblProduct`.

**A code needs an entry only when it differs from the username**, and a code with no
entry at all is not an error:

- A code that already *is* a `tblContact.UserName` resolves on its own. Only **7** of the
  564 codes in the extracts are (11,940 rows) — `DENJ`→Denise Jones, `SUZC`→Suzanne
  Chhour, `ABHB`→Abhishek Baratamu, `KATX`, `RITB`, `STAM`, `MARC`.
- A code that matches nothing falls to `ISNULL(…, {{DefaultOperatorContactID}})`. On
  testse that is the other **557** codes and **3.26 million rows**, whose biggest members
  (`DLR` 628k, `APP` 532k, `DL` 474k, `REMOTE` 304k) are automation rather than people.

`DefaultOperatorContactID` is a `lookup_variables` entry in
`variables/migration_variables.json` resolving `tblContact.UserName = 'PRAM'` to a
`ContactID` per environment — 197 on testse — so the id is never written into the SQL.
If that username is absent it falls back to the configured `default` of `1` (`admin`),
which is what every consumer used before. **Note this changes today's behaviour for the
unresolved tail:** those 3.26M rows previously landed on `admin` and now land on `PRAM`,
the same contact the old `CSRC_OperatorContactMapping` pointed all 20 of its rows at. To
send them back to `admin`, change that one `filter_value` to `admin`.

So the file is **added to as needed**, like `account_status_codes.json`, rather than kept
as a complete inventory. The check step names every unresolved code the extracts carry,
busiest first with row counts, and you add the ones for which the fallback is the wrong
answer. Nothing reads `CSRC_OperatorContactMapping` any more — the codes come from the
customer's own data.

The 20 seeded codes all sit under `PRAM`, which is **preserved behaviour, not a
judgement**: every row of the old table pointed at `ContactID 197` whatever the operator
code was, the same placeholder shape as the 31 MERCANTILE cost codes. Eight of them
(`AKSJ`, `AMRA`, `MARC`, `MURK`, `RUSW`, `SABS`, `SHEL`, `SUZC`) are themselves exact
`UserName` values for *different* real people. Giving each its own key is almost certainly
what was intended, but it changes who migrated accounts, payments, notes and letters are
attributed to, so it waits for sign-off. `operator_contact_codes.json` records that, and
the three near-misses (`ABHV`, `ADIU`, `SRAV`) deliberately left alone.

This no longer interacts with note islands. Notes are consolidated by
`notes_consolidation` during the staging load, which runs *before* this rewrite, so
islands break on the original operator codes and no collapse can reach them. The operator
also survives only as display text in a note header now — `67` attributes a consolidated
entry to `DefaultOperatorContactID` rather than resolving a contact per note — so adding
codes here no longer affects `tblEntry` for notes at all. It still affects `01`, `49`,
`58`, `60`, `64` and `65`.

### Notes consolidation (one table to deploy, once per environment)

`RC_NOTES_EXTRACT` carries one row per *display line*, not per note. DebtRak word-wraps
note text and stores each wrapped line as its own PICK multivalue, so a single email or
call log arrives as up to 94 rows — and `67.tblentry_notes.sql` used to insert each of
them as a separate `tblEntry` row.

Business asked for one entry per account instead: the whole note history in a single
readable block, newest note first, each original note headed with its date and operator.
`notes_consolidation.NotesConsolidator` folds the extract as `process_staging` streams it
in, and `67.tblentry_notes.sql` writes one `tblEntry` row per account from the result.
Deploy the table before the first run in a new environment — the run stops at startup
naming it if it is missing:

```bash
SQL/Schemas/RC_STAGING_NOTES_ACCOUNT Schema.sql
```

Three levels of folding, measured on testse:

| | rows |
|---|---|
| display lines (`RC_NOTES_EXTRACT`) | 6,638,549 |
| source lines | 5,676,975 |
| logical notes | 3,049,278 |
| **account entries (`tblEntry`)** | **10,725** |

A note is an *island*: a run of ZID-contiguous rows sharing debtor, timestamp and
operator. The ZID ordering matters — `Date_Entered` is minute-only on 36% of rows, so it
cannot order lines within a note — and the island break on operator change is what keeps
two dialler calls made in the same minute from being welded into one note.

**Why this moved out of SQL.** `66.RC_STAGING_NOTES.sql` did the first two levels
server-side and is deleted. Measured for the same 6.64M rows: ~290s of Azure SQL time
against ~120s of local CPU, on an instance measured at 88% CPU from other workloads. The
port was checked against the SQL it replaces over 300 accounts and 162,254 display lines —
identical note counts and byte-identical note text — before the SQL was removed.

The README used to argue the opposite, on the grounds that `RC_NOTES_EXTRACT.Text` is
`nvarchar(1000)` while consolidated notes reach 5,095 characters. That objection does not
apply here: the extract still loads raw and unchanged, so staging stays a faithful copy of
what the source sent, and the consolidated block goes to a *separate* table whose `Entry`
is `nvarchar(max)`. Largest account measured: 71,004 characters.

`RC_STAGING_NOTES_ACCOUNT` holds one customer at a time — truncated with the extract
tables at the start of each customer, because it is derived from `RC_NOTES_EXTRACT`, which
is truncated too. It carries no LoadID for the same reason the extracts do not; `67`
reaches it through `tblAccount`, which is where the LoadID filter lives.

**What is lost, and was accepted.** One row per account means `EntryDate` can only carry
the account's most recent note and `CreateID` can only carry the fallback contact. Each
note's own date and operator are preserved as text in its block header, but neither is a
queryable column any more, individual notes are no longer separately addressable, and
`COUNT(*) FROM tblEntry` is no longer a proxy for note volume. The
`RC_STAGING_NOTES_ACCOUNT` metric reports how many original note lines were carried, so
the drop in the `tblEntry` count reads as intended rather than as data loss.

Losslessness is asserted twice: the consolidator fails before anything is loaded if source
rows are not all accounted for, and `67` compares both row count and total bytes across
the bcp hop, rolling the file back if they disagree.

Treatments (`68.tblentry_treatments.sql`) get the same one-row-per-account treatment but
stay in SQL — there is no island detection to port, so the fold is a plain grouped
concatenation the engine does in 1.8s.

### Column Mappings
CSV column mappings in `column mapping/` define the data transformation rules for tables including:
- RC_ACCOUNT_EXTRACT - Account information
- RC_ARRANGEMENT - Financial arrangements  
- RC_COSTS_EXTRACT - Cost data
- RC_DEAL - Deal information
- RC_DEBT_CONTACTS - Debt contact details
- RC_DEBTOR - Debtor information
- And other RC_* tables for comprehensive data coverage

### SQL Scripts
Migration SQL scripts are organized in the `SQL/` directory:
- **Migration queries/**: Core migration logic organized by execution type
- **Procedures/**: Stored procedures for migration management
- **Schemas/**: Table schema definitions for validation

### Variables
Migration variables and parameters are defined in the `variables/` directory with JSON configuration files.

## Usage

### Windows
Run the migration using the batch file:
```batch
Run_Migration.bat
```

### Python Direct Execution
```bash
python Run_Migration.py
```

### Command Line Options
The migration script supports various command-line arguments for customization (check `Run_Migration.py` for available options).

## Migration Workflow

1. **Initialization**
   - Load environment configuration from `config/` files
   - Establish database connections via `db_manager.py`
   - Initialize logging and memory monitoring

2. **Staging Process**
   - Read CSV files matching pattern `*RC_*.csv`
   - Apply column mappings from `column mapping/` directory
   - Validate data format and load into staging tables

3. **Customer Processing**
   - Process each customer sequentially using `customer_processor.py`
   - Delegate focused operations to service implementations in `services/`
   - Apply data transformations based on business rules
   - Validate customer-specific data integrity

4. **SQL Migration**
   - Execute migration SQL scripts from `SQL/Migration queries/`
   - Replace variables dynamically using `variables/` configurations
   - Handle transactions with rollback capability via `DT_query_processor.py`

5. **Staging Archive**
   - Rename every RC_* staging table into the `archive` schema as `<CustomerCode>_<table>`, and
     rebuild the staging table empty from its `SQL/Schemas/` file - one transaction, all catalog
     operations, so the cost does not grow with the extract. See [Archive](#archive)
   - Runs per customer, after the SQL migration; a failed archive fails that customer, and rolls
     back whole - staging is left intact and still holding the extract
   - Nothing is copied and nothing crosses a database, so the path is identical on Azure SQL and
     on a normal instance, and the next customer is never waiting on it
   - `LoadID`, `CreateTS` and `EntityCode` go to `archive.ArchiveCatalog`, one row per archived
     table, rather than onto every row
   - `tools/sweep_archive.py` moves those tables on to `ARCHIVE_DATABASE` out of band - that is
     where bcp still lives, and the only part that streams through the client
   - Run it on its own with
     `python tools/archive_staging.py <env> --entity-code <code> --dry-run`

6. **Metrics & Reporting**
   - Collect migration statistics using `memory_manager.py`
   - Generate success/failure reports
   - Update processing metrics in `variables/` directory

## Data Tables

The system processes comprehensive financial data tables including:
- **RC_ACCOUNT_EXTRACT** - Account information and details
- **RC_ARRANGEMENT** - Financial arrangements and agreements
- **RC_COSTS_EXTRACT** - Cost and expense data
- **RC_DEAL** - Deal and transaction information
- **RC_DEBT_CONTACTS** - Debt collection contact details
- **RC_DEBTOR** - Debtor information and status
- **RC_PAYMENTS** - Payment history and transactions
- **RC_STATEMENT** - Account statements
- **RC_TREATMENT** - Treatment and resolution data
- And additional RC_* tables for complete data migration

## Error Handling

- **Transaction Rollback**: Automatic rollback on failures to maintain data integrity
- **Detailed Error Logging**: Comprehensive error tracking and reporting
- **Customer-Level Isolation**: Prevents cascading failures across customers
- **Memory Monitoring**: Prevents out-of-memory errors during large data processing
- **Validation Checks**: Built-in data validation at multiple stages

## Monitoring

The system provides comprehensive monitoring capabilities:
- Real-time memory usage tracking via `memory_manager.py`
- Migration progress indicators per customer and table
- Success/failure metrics collection
- Detailed execution logs with timestamps
- Performance metrics stored in `variables/processing_stats_metrics.json`

## Requirements

See `requirements.txt` for Python package dependencies.

### System Requirements
- Python 3.11+
- Sufficient memory for dataset processing (monitored automatically)
- Database connectivity (SQL Server/Oracle/etc.)
- Windows OS (for .bat execution) or Unix/Linux compatible

## Troubleshooting

### Common Issues
- **Memory Issues**: Monitor via `memory_manager.py` logs
- **Database Connectivity**: Check `config/` environment files
- **Data Validation Errors**: Review column mappings in `column mapping/` directory
- **SQL Execution Failures**: Check `SQL/Procedures/DT Migration - Table Check.sql` for table validation

### Debug Tools
- Use `SQL/Procedures/DT Migration - Table Check.sql` to validate table structures
- Check `variables/staging_metrics.json` for staging process status
- Review migration logs for detailed error information

#### Why an account did not migrate

The account population is decided entirely by two filters in
`SQL/Migration queries/Direct/01.tblaccount.sql` — a retention window, and the
`tblAccountStatus` lookup. When a count looks short downstream (notes that did not
migrate, an account nobody can find), this reports which filter dropped what and
reconciles the answer against `tblAccount`:

```bash
python tools/audit_account_filter.py uat --load-id 237 --by-status
```

Read-only; every statement is a SELECT. `--closed-months` / `--pay-months` ask what a
different retention window would have kept, without changing anything.

Do **not** hand-write this check as `WHERE NOT (<the filter>)`. `Last_Pay_Date` is
nullable, so that clause is `UNKNOWN` rather than `FALSE` on those rows and the whole
OR chain goes `UNKNOWN`; since `NOT UNKNOWN` is `UNKNOWN`, the negation quietly finds
only a fraction of the excluded rows. On uat it reports 408 against a true 3,376. The
tool evaluates the filter into a per-row flag and tests the flag, which is what makes
it agree with the migration.

#### "carries charges under cost codes that cost_codes.json neither maps nor excludes"

The cost step found money in a `Chg_<code>` column that `variables/cost_codes.json`
says nothing about, and stopped the customer instead of migrating an incomplete set of
costs. The message names each code with its row count and total. Resolve it by adding
the code to `cost_types` under its `tblCostType` label — with `master_costs` too if it
should not take `default_master_cost` — or to `not_costs` with the reason it is not a
cost. Both are JSON edits; nothing in the SQL changes.

The related errors from the same step are all config, and all name what to fix: a cost
type or master cost label absent from `tblCostType`/`tblMasterCost`, a code that is not
a valid code name, or `RC_STAGING_COSTS` not yet deployed. A configured code with no
matching `Chg_` column is only a warning — it cannot be carrying a charge.

#### "operator code(s) in the extracts resolve to no tblContact.UserName"

Not an error, and not a reason to stop. Those rows are attributed to the contact
`{{DefaultOperatorContactID}}` names — `197 (PRAM)` on testse, which the message prints
in full — on testse that is 557 of the 564 codes in the data. The warning names the
busiest 20 with row counts so you can decide which are worth mapping; add those to
`variables/operator_contact_codes.json` under the `tblContact.UserName` they act as, and
leave the rest.

Two things from this step **are** fatal. A username in the JSON that `tblContact` does not
have: that is deliberate, because a username nothing matches rewrites nothing and every
code under it falls silently through to the fallback contact, so a typo would look like a
working mapping — fix the username or remove the key. And an operator column too narrow
for a configured username, which names the exact `ALTER TABLE` that fixes it; the longest
username in use is 42 characters and the narrowest operator column is `NVARCHAR(50)`, so
this is not expected to fire.

#### Costs are in tblCost but do not show on the account

Check `tblCost.CostDate` first. `RC_COSTS_EXTRACT` carries no date — only `Debtor_Code`,
`Client_Code`, `Client_Group` and the `Chg_`/`Paid_` pairs — and `RC_TRANSACTION` has no
cost transaction type either (only `DEB`, `PAYT`/`PAYD`, `COMT`/`COMD`), so there is no
dated cost line in the extracts to take. Leaving it NULL is **not** neutral:
`fnAccountCalculateTotals_EventList` dates a cost as `ISNULL(CostDate, @Today)` and
`@Today` is *end* of the current day, so the cost transaction lands in the future. On
load 247 that put all 8,304 of them at `23:59:59.100` on the migration date — after the
payments that had already paid them, at the top of a newest-first ledger, and outside
any view or statement showing activity as at now.

`51.tblcosts.sql` now sets `CostDate` from `tblAccount.RecoveryStartDate`, which is
populated on every account in the load and always in the past. The DebtRak procs
themselves are fine — `spCostSelectSummaryByAccountID_Extended` and
`spTransactionSelectSummaryPaginationByAccountID_Extended` both return the cost row —
so if a cost is missing from a grid, compare it against a cost the application created
(`tblCost WHERE LoadID IS NULL`) and look at which columns that row populates.

#### "maximum row size exceeds the allowed maximum of 8060 bytes"

Creating a wide staging table prints this. It is expected on 14 of the 30 tables in
`SQL/Schemas/`, it refers to the **declared** column widths rather than the data, and the table
is created and works. Nothing about it is silent — a row that genuinely does not fit is rejected
with Msg 511 and fails the load.

Whether it matters is a question about the extracts, not the schema, so measure them:

```bash
python tools/check_row_size.py <env> --table RC_DRDEBTINFO --recursive
```

Read-only and needs no database — the schema comes from `SQL/Schemas/` and the rows from the
extract CSVs, so it can be run before the tables are deployed. `--no-data` reports the schema
arithmetic for every table without reading any CSV; `--csv-path` replaces the environment's
network share. Exit status is 1 if any row could exceed the limit.

For 13 of those 14 tables a fully populated row still fits, so the warning can never bite.
`RC_DRDEBTINFO` is the exception — 504 columns, of which 326 can hold data before a row becomes
unstorable. Measured 2026-09-08 across 412 extract files and 645,378 rows, the widest row uses
3,005 bytes of the 8,060, with the most populated row filling 67 of the 504 columns. The header
of `SQL/Schemas/RC_DRDEBTINFO Schema.sql` carries the full arithmetic and explains why
right-sizing the columns would not clear the warning.

## Refactor Compatibility

- Root-level service module names are retained as import shims for backward compatibility.
- New code should prefer canonical imports from subpackages (`services.io.*`, `services.workflows.*`, `services.setup.*`, `services.execution.*`, `services.orchestration.*`); `services.*` remains available as a compatibility layer.


