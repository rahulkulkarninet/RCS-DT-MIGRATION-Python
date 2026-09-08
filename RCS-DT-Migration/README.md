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
- `ARCHIVE_DATABASE` - database on the same server holding the archived copy of the staging
  tables. Named per environment (`test-migration-data` on testse, `dev-migration-data` on uat);
  an env file that omits it falls back to `migration_data`.

### Archive setup (once per environment)

The archive database and its tables are provisioned separately from the migration. A migration run
only inserts rows, so both steps below have to have been done before the first run in a new
environment - after that they are not run again unless the staging schema changes.

1. Create the database and grant the migration account access:
   `SQL/Schemas/Migrations/004.migration_data_archive.sql` (privileged, run by hand once per server)
2. Create the archive tables - one per table in `variables/table_keywords.json`, generated from
   that staging table's own columns plus `LoadID`, `CreateTS` and `EntityCode`:

```bash
python tools/setup_archive.py <env>
```

`--dry-run` prints the DDL without running it, and `--table <name>` limits it to one table. The
step is re-runnable: an already-correct table is left untouched, a missing audit column is added
nullable, and no rows are read or written. Re-run it after a staging schema change adds a column -
a staging column with no archive column is reported and silently not archived, and the way to pick
it up is to drop that archive table and let this recreate it.

Both archive tools take the environment from `config/<env>.env` and the table list from
`variables/table_keywords.json`. `--config` points at another environment file, or at the directory
holding one, for an environment whose credentials are kept outside the repo; `--variables` points
at another folder holding `table_keywords.json`. When `--config` names a file, that file's name is
the environment and the positional argument can be left off:

```bash
python tools/setup_archive.py --config D:\secrets\testse.env --dry-run
```

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
   - Copy every RC_* staging table into the environment's `ARCHIVE_DATABASE` on the same server
   - Archive tables mirror the staging columns plus `LoadID`, `CreateTS` and `EntityCode`. They
     are created by a separate one-off setup step, not by the migration - see
     [Archive setup](#archive-setup-once-per-environment)
   - Runs per customer, after the SQL migration and before the next customer truncates staging;
     a failed archive fails that customer
   - Rows only: a run issues no DDL against the archive database, and fails the customer with a
     message naming the setup step if a table is missing or lacks an audit column
   - On SQL Server the copy is a cross-database `INSERT ... SELECT` and never leaves the server;
     on Azure SQL, which has no cross-database queries, rows stream through the client and are
     loaded with bcp - always, at any row count. There is no executemany fallback: a table bcp
     cannot load safely (binary columns, generated columns, or an archive column nothing supplies)
     fails with the reason rather than quietly taking a second path
   - Run it on its own with `python tools/archive_staging.py <env> --dry-run`

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

## Refactor Compatibility

- Root-level service module names are retained as import shims for backward compatibility.
- New code should prefer canonical imports from subpackages (`services.io.*`, `services.workflows.*`, `services.setup.*`, `services.execution.*`, `services.orchestration.*`); `services.*` remains available as a compatibility layer.


