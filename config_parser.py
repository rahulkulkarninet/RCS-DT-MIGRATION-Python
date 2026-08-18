import json
import os
import logging
from typing import Dict, Any, Optional
from db_manager import DatabaseHelper

class ConfigParser:
    """Simple configuration parser for migration variables."""

    def __init__(self, db_environment: str, variables_folder: str = None, shared_db_helper=None):
        self.variables_folder = variables_folder or os.path.join(os.path.dirname(__file__), 'variables')
        self.db_environment = db_environment
        self.logger = logging.getLogger(__name__)
        
        # Store variables by category
        self.variables = {
            'vwHost': {},
            'lookup_variables': {},
            'metafield_variables': {},
            'constant_variables': {},
            'path': {}
        }
        self.table_keywords = {}
        self.processing_stats = {}
        self.staging_metrics = {}

        # Use shared database helper if provided
        self.db_helper = shared_db_helper
        self._owns_db_connection = shared_db_helper is None
        self._database_vars_resolved = False
    
    def load_json(self, filename: str) -> Dict[str, Any]:
        """Load JSON file safely."""
        try:
            with open(os.path.join(self.variables_folder, filename), 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            self.logger.warning(f"{filename} not found")
            return {}
        except Exception as e:
            self.logger.error(f"Error loading {filename}: {e}")
            return {}
    
    def load_configs(self):
        """Load all configuration files."""
        # Load basic configs
        path_config = self.load_json('path_config.json')
        self.table_keywords = self.load_json('table_keywords.json')
        self.processing_stats = self.load_json('processing_stats_metrics.json')
        self.staging_metrics = self.load_json('staging_metrics.json')
        migration_config = self.load_json('migration_variables.json')
        
        # Add path variables under 'path' category
        for key, value in path_config.items():
            self.variables['path'][key.upper()] = value
        
        # Add constants under 'constant_variables' category
        constants = migration_config.get('migration_variables', {}).get('constant_variables', {}).get('variables', {})
        for name, config in constants.items():
            self.variables['constant_variables'][name.upper()] = config.get('default')
        
        total_vars = sum(len(category) for category in self.variables.values())
        self.logger.info(f"Loaded {total_vars} variables across {len(self.variables)} categories")
    
    def init_database(self):
        """Initialize database connection."""
        if self.db_helper is not None:
            # Using shared connection
            self.logger.info("Using shared database connection")
            return True
        
        try:
            self.db_helper = DatabaseHelper(environment=self.db_environment)
            self._owns_db_connection = True
            if self.db_helper.test_connection().get('sqlalchemy'):
                self.logger.info("Database connected")
                return True
        except Exception as e:
            self.logger.warning(f"Database unavailable: {e}")
        return False
    
    def resolve_database_vars(self):
        """Resolve variables from database."""
        if not self.db_helper:
            return
        
        migration_config = self.load_json('migration_variables.json')
        migration_vars = migration_config.get('migration_variables', {})
        
        # Resolve vwHost variables
        vw_host = migration_vars.get('vwHost', {})
        if vw_host:
            self._resolve_vw_host(vw_host)
        
        # Resolve lookup variables
        lookup_vars = migration_vars.get('lookup_variables', {})
        if lookup_vars:
            self._resolve_lookups(lookup_vars)
        
        # Resolve metafield variables
        metafield_vars = migration_vars.get('metafield_variables', {})
        if metafield_vars:
            self._resolve_metafields(metafield_vars)
        
        self._database_vars_resolved = True 
    
    def _resolve_vw_host(self, config: Dict[str, Any]):
        """Resolve vwHost variables."""
        variables = config.get('variables', {})
        query_details = config.get('query_details', {})
        
        if not variables or not query_details:
            return
        
        try:
            # Build simple query
            columns = []
            for var_name, var_config in variables.items():
                column = var_config.get('column', '')
                default = var_config.get('default', 'NULL')
                if isinstance(default, str) and default != 'NULL':
                    default = f"'{default}'"
                columns.append(f"ISNULL([{column}], {default}) AS [{var_name}]")
            
            query = f"""
            SELECT {', '.join(columns)}
            FROM [{query_details.get('main_table')}] 
            LEFT JOIN [{query_details.get('join_table')}] 
            ON {query_details.get('join_condition')}
            """
            
            result = self.db_helper.execute_query(query)
            if not result.empty:
                row = result.iloc[0]
                for var_name in variables.keys():
                    value = row[var_name]
                    # Convert numpy types to Python types
                    if hasattr(value, 'item'):
                        value = value.item()
                    self.variables['vwHost'][var_name.upper()] = value
            else:
                # Use defaults
                for var_name, var_config in variables.items():
                    self.variables['vwHost'][var_name.upper()] = var_config.get('default')
                    
        except Exception as e:
            self.logger.error(f"Error resolving vwHost variables: {e}")
            # Use defaults
            for var_name, var_config in variables.items():
                self.variables['vwHost'][var_name.upper()] = var_config.get('default')
    
    def _resolve_lookups(self, config: Dict[str, Any]):
        """Resolve lookup variables."""
        variables = config.get('variables', {})
        
        for var_name, var_config in variables.items():
            try:
                query = f"""
                SELECT [{var_config.get('column')}] 
                FROM [{var_config.get('main_table')}] 
                WHERE [{var_config.get('filter_col')}] = '{var_config.get('filter_value')}'
                """
                
                result = self.db_helper.execute_query(query)
                if not result.empty and result.iloc[0, 0] is not None:
                    value = result.iloc[0, 0]
                    # Convert numpy types
                    if hasattr(value, 'item'):
                        value = value.item()
                    self.variables['lookup_variables'][var_name.upper()] = value
                else:
                    self.variables['lookup_variables'][var_name.upper()] = var_config.get('default')
                    
            except Exception as e:
                self.logger.error(f"Error resolving lookup {var_name}: {e}")
                self.variables['lookup_variables'][var_name.upper()] = var_config.get('default')
    
    def _resolve_metafields(self, config: Dict[str, Any]):
        """Resolve metafield variables."""
        variables = config.get('variables', {})
        query_details = config.get('query_details', {})
        
        for var_name, var_config in variables.items():
            try:
                query = f"""
                SELECT [{query_details.get('column')}] 
                FROM [{query_details.get('main_table')}] 
                WHERE [{query_details.get('filter_col')}] = '{var_config.get('filter_value')}' 
                AND [{query_details.get('sec_col')}] = '{query_details.get('sec_value')}'
                """
                
                result = self.db_helper.execute_query(query)
                if not result.empty and result.iloc[0, 0] is not None:
                    value = result.iloc[0, 0]
                    # Convert numpy types
                    if hasattr(value, 'item'):
                        value = value.item()
                    self.variables['metafield_variables'][var_name.upper()] = value
                else:
                    self.variables['metafield_variables'][var_name.upper()] = None
                    
            except Exception as e:
                self.logger.error(f"Error resolving metafield {var_name}: {e}")
                self.variables['metafield_variables'][var_name.upper()] = None
    
    def export_config(self, output_file: str = None):
        """Export configuration to Python file."""
        if output_file is None:
            output_file = os.path.join(os.path.dirname(self.variables_folder), 'migration_config.py')
        
        lines = [
            "# Auto-generated migration configuration",
            "# DO NOT EDIT THIS FILE MANUALLY",
            "",
        ]
        
        # Export table keywords
        if self.table_keywords:
            lines.append("# Table Keywords Dictionary")
            lines.append("TABLE_KEYWORDS = {")
            for key, value in self.table_keywords.items():
                lines.append(f'    "{key}": "{value}",')
            lines.append("}")
            lines.append("")
        
        # Export variables by category
        for category, vars_dict in self.variables.items():
            if vars_dict:  # Only export if category has variables
                lines.append(f"# {category.replace('_', ' ').title()} Variables")
                for key, value in vars_dict.items():
                    if isinstance(value, str):
                        lines.append(f'{key} = "{value}"')
                    elif value is None:
                        lines.append(f"{key} = None")
                    else:
                        lines.append(f"{key} = {repr(value)}")
                lines.append("")
        
        # Export staging metrics
        if self.staging_metrics:
            lines.append("# Staging Metrics")
            lines.append("STAGING_METRICS = {")
            for table_name, config in self.staging_metrics.items():
                lines.append(f'    "{table_name}": {repr(config)},')
            lines.append("}")
            lines.append("")
        
        # Export processing stats
        if self.processing_stats:
            lines.append("# Processing Stats Metrics")
            lines.append("PROCESSING_STATS_METRICS = {")
            for table_name, config in self.processing_stats.items():
                lines.append(f'    "{table_name}": {repr(config)},')
            lines.append("}")
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        
        self.logger.info(f"Configuration exported to: {output_file}")
    
    def get_variable(self, name: str, category: str = None) -> Any:
        """Get a variable value. If category not specified, search all categories."""
        name = name.upper()
        
        if category:
            return self.variables.get(category, {}).get(name)
        
        # Search all categories
        for category_vars in self.variables.values():
            if name in category_vars:
                return category_vars[name]
        return None
    
    def get_category_variables(self, category: str) -> Dict[str, Any]:
        """Get all variables from a specific category."""
        return self.variables.get(category, {})
    
    def get_table_name(self, keyword: str) -> Optional[str]:
        """Get table name from keyword."""
        return self.table_keywords.get(keyword.upper())
    
    def get_staging_metrics(self, table_name: str) -> Optional[Dict[str, Any]]:
        """Get staging metrics for a table."""
        return self.staging_metrics.get(table_name)
    
    def get_processing_config(self, table_name: str) -> Optional[Dict[str, Any]]:
        """Get processing configuration for a table."""
        return self.processing_stats.get(table_name)
    
    def print_summary(self):
        """Print configuration summary."""
        print("\n=== Configuration Summary ===")
        for category, vars_dict in self.variables.items():
            if vars_dict:
                print(f"{category}: {len(vars_dict)} variables")
        print(f"Table Keywords: {len(self.table_keywords)} mappings")
        print(f"Staging Metrics: {len(self.staging_metrics)} configurations")
        print(f"Processing Stats: {len(self.processing_stats)} configurations")
        print("===============================\n")
    
    def run(self):
        """Main execution method."""
        self.load_configs()
        if self.init_database():
            self.resolve_database_vars()
        #self.export_config()
        self.print_summary()
        
        if self.db_helper:
            self.db_helper.close_connections()

    def cleanup(self):
        """Clean up resources - only close connection if we own it."""
        if self.db_helper and self._owns_db_connection:
            self.db_helper.close_connections()
            self.logger.info("ConfigParser closed own database connection")
        elif self.db_helper:
            self.logger.debug("ConfigParser using shared connection - not closing")
    
    
    def __enter__(self):
        """Context manager entry."""
        self.load_configs()
        if self.init_database():
            self.resolve_database_vars()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.cleanup()

# # Usage
# if __name__ == "__main__":
#     logging.basicConfig(level=logging.INFO)
    
#     with ConfigParser(db_environment='v10') as parser:
#         # Access variables by category
#         print(f"vwHost AddressTypeID_Home: {parser.get_variable('ADDRESSTYPEID_HOME', 'vwHost')}")
#         print(f"Lookup AddressTypeID_Legal: {parser.get_variable('ADDRESSTYPEID_LEGAL', 'lookup_variables')}")
#         print(f"Metafield BILL: {parser.get_variable('BILL', 'metafield_variables')}")
        
#         # Access staging metrics
#         account_staging = parser.get_staging_metrics('RC_ACCOUNT_EXTRACT')
#         print(f"Account extract staging metrics: {account_staging}")
        
#         # Get all variables from a category
#         metafields = parser.get_category_variables('metafield_variables')
#         print(f"All metafield variables: {list(metafields.keys())}")
        
#         print("Configuration exported successfully!")