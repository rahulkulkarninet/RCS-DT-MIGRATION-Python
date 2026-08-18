# Symbos RCS-DT Migration System

## Overview

The Symbos RCS-DT Migration System is a Python based data migration tool designed to transfer and transform customer data from RCS to DT. The system processes financial and accounting data through a staged migration approach, ensuring data integrity and providing comprehensive logging and metrics.

## Architecture

### Core Components

- **`Run_Migration.py`** - Main entry point that orchestrates the entire migration process
- **`customer_processor.py`** - Facade/orchestrator for customer-by-customer processing with the `CustomerProcessor` class
- **`services/`** - Service-layer implementations used by `CustomerProcessor` for focused workflow responsibilities
- **`process_staging.py`** - Manages staging file processing via the `StagingProcessor` class
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

5. **Metrics & Reporting**
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

## Refactor Compatibility

- Root-level service module names are retained as import shims for backward compatibility.
- New code should prefer canonical imports from subpackages (`services.io.*`, `services.workflows.*`, `services.setup.*`, `services.execution.*`, `services.orchestration.*`); `services.*` remains available as a compatibility layer.


