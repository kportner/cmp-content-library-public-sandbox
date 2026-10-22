from common.methods import set_progress
from infrastructure.models import Environment
from resourcehandlers.aws.models import AWSHandler
from utilities.logger import ThreadLogger

logger = ThreadLogger(__name__)


def get_aws_rh_and_region(resource):
    rh_aws_id = getattr(resource, 'aws_rh_id', None)
    aws_region = getattr(resource, 'aws_region', None)
    rh_aws = None

    if rh_aws_id:
        rh_aws = AWSHandler.objects.filter(id=rh_aws_id).first()

    if not rh_aws and aws_region:
        env = Environment.objects.filter(aws_region=aws_region).first()
        if env and env.resource_handler:
            rh_aws = env.resource_handler.cast()

    return aws_region, rh_aws


def run(job, logger=logger, **kwargs):
    resource = kwargs.pop('resources').first()

    msg = f"PostgreSQL database Delete plugin running for resource: {resource}"
    set_progress(msg)

    postgresql_database_identifier = resource.db_identifier

    # Get AWS region and resource handler object
    region, aws = get_aws_rh_and_region(resource)

    if not aws or not region:
        return "WARNING", "", "Need a valid aws region and handler context to delete this database"

    set_progress('Connecting to Amazon PostgreSQL Database...')

    # Initialize Boto3 RDS client
    client = aws.get_boto3_client(region, 'rds')

    subnet_group_name = None
    try:
        # Verify PostgreSQL database instance and fetch Subnet Group Name
        rds_resp = client.describe_db_instances(DBInstanceIdentifier=postgresql_database_identifier)
        if rds_resp.get('DBInstances'):
            db_inst = rds_resp['DBInstances'][0]
            subnet_group = db_inst.get('DBSubnetGroup', {})
            subnet_group_name = subnet_group.get('DBSubnetGroupName')
    except Exception as err:
        if "DBInstanceNotFound" in str(err):
            return "WARNING", f"PostgreSQL Database instance {postgresql_database_identifier} not found, it may have already been deleted", ""
        raise RuntimeError(err)

    msg = f'Deleting PostgreSQL Database {postgresql_database_identifier}...'
    set_progress(msg)

    # Delete PostgreSQL Database from AWS
    client.delete_db_instance(
        DBInstanceIdentifier=postgresql_database_identifier,
        SkipFinalSnapshot=True,
        DeleteAutomatedBackups=True,
    )

    waiter = client.get_waiter('db_instance_deleted')
    waiter.config.max_attempts = 100
    waiter.wait(DBInstanceIdentifier=postgresql_database_identifier)

    # Delete DB Subnet Group if associated and unused by other DB instances
    if subnet_group_name:
        try:
            # Check if any other DB instance is currently using this Subnet Group
            all_instances = client.describe_db_instances().get('DBInstances', [])
            other_instances_using_group = [
                inst['DBInstanceIdentifier'] for inst in all_instances
                if inst.get('DBSubnetGroup', {}).get('DBSubnetGroupName') == subnet_group_name
                and inst['DBInstanceIdentifier'] != postgresql_database_identifier
            ]

            if other_instances_using_group:
                shared_msg = f"Subnet group '{subnet_group_name}' is shared with DB(s): {', '.join(other_instances_using_group)}. Leaving intact."
                set_progress(shared_msg)
            else:
                msg = f"Attempting to delete DB Subnet Group '{subnet_group_name}'..."
                set_progress(msg)

                client.delete_db_subnet_group(DBSubnetGroupName=subnet_group_name)

                success_msg = f"DB Subnet Group '{subnet_group_name}' deleted successfully."
                set_progress(success_msg)

        except Exception as e:
            warn_msg = f"Could not delete DB Subnet Group '{subnet_group_name}': {str(e)}"
            logger.warning(warn_msg)
            set_progress(f"Notice: DB Subnet Group '{subnet_group_name}' was left intact ({str(e)}).")

    final_msg = f"PostgreSQL database {postgresql_database_identifier} deleted successfully"
    set_progress(final_msg)

    return 'SUCCESS', final_msg, ''