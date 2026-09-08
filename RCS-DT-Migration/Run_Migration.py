import argparse
import sys
import os
import logging
import site

from customer_processor import CustomerProcessor
from interaction import APPROVE_CHOICES, APPROVE_NONE, resolve_policy, stdin_is_interactive


KNOWN_ENVIRONMENTS = ('dev', 'uat', 'v10', 'scratch')


def resolve_environment(selected: str | None) -> str:
    """Resolve target environment from CLI argument or interactive prompt."""
    if selected:
        return selected.strip()

    if not stdin_is_interactive():
        return 'dev'

    allowed = '/'.join(KNOWN_ENVIRONMENTS)
    while True:
        choice = input(f'Select environment [{allowed}] (default: dev): ').strip().lower()
        if not choice:
            return 'dev'
        if choice in KNOWN_ENVIRONMENTS:
            return choice
        print(f"Invalid environment '{choice}'. Choose one of: {allowed}")

parser = argparse.ArgumentParser(
    description='Run the RCS to DT migration.',
    epilog='Unattended example: Run_Migration.py scratch --non-interactive '
           '--auto-approve all',
)
parser.add_argument('environment', nargs='?', default=None,
                    help='Target environment. If omitted, you will be prompted in interactive runs.')
parser.add_argument('--non-interactive', action='store_true',
                    help='Never prompt. Requires --auto-approve, since gates that '
                         'are not pre-approved get declined.')
parser.add_argument('--auto-approve', choices=APPROVE_CHOICES, default=APPROVE_NONE,
                    help="Which approval gates to pre-approve: 'none' (default), "
                         "'staging', or 'all'.")
parser.add_argument('--resume-load-id', type=int, default=None, metavar='N',
                    help='Continue an interrupted migration: adopt this existing '
                         'LoadID and skip the SQL files already recorded complete '
                         'in DT_Migration_SQLProgress.')
args = parser.parse_args()

environment = resolve_environment(args.environment)

# Add user site-packages to Python path 

user_site = site.getusersitepackages() 
if user_site not in sys.path: 
    sys.path.insert(0, user_site) 


# Setup logging with user-writable location 
log_file = os.path.join(os.path.expanduser('~'), 'migration_process.log') 

# Setup logging 
logging.basicConfig( 
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    handlers=[ 
        logging.FileHandler(log_file), 
        logging.StreamHandler() 
    ] 
) 

logger = logging.getLogger(__name__) 
logger.info(f'Log file location: {log_file}') 
logger.info(f'Starting migration for environment: {environment}')

try:

    approval_policy = resolve_policy(args.non_interactive, args.auto_approve, logger)

    if args.resume_load_id:
        logger.info(f'RESUME: adopting LoadID {args.resume_load_id}; SQL files already '
                    f'recorded complete for it will be skipped')

    # Initialize customer processor
    processor = CustomerProcessor(environment, approval_policy=approval_policy,
                                 resume_load_id=args.resume_load_id)

    if processor.initialize(): 
        logger.info('Customer Processor initialized successfully') 
        
        # Run the complete staging to migration process 
        customer_results = processor.process_staging_to_migration() 

        has_failures = any(
            result.get('overall_status') == 'FAILED'
            or result.get('processing_success') is False
            or result.get('setup_failed', False)
            for result in customer_results.values()
        )

        if has_failures:
            logger.error('Migration completed with failures')
            sys.exit(1)
        
    else: 
        logger.error('Failed to initialize Customer Processor') 
        sys.exit(1) 
        
except KeyboardInterrupt: 
    logger.info('Process interrupted by user') 
    sys.exit(0) 
    
except Exception as e: 
    logger.error(f'Process failed with error: {e}') 
    import traceback 
    logger.error(f'Traceback: {traceback.format_exc()}') 
    sys.exit(1) 
    
finally: 
    # Cleanup 
    if 'processor' in locals(): 
        processor.cleanup() 
    logger.info('Process completed') 
