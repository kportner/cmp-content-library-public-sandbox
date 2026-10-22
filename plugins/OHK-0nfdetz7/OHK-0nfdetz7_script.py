from common.methods import set_progress
from infrastructure.models import Environment
from resourcehandlers.aws.models import AWSHandler
from utilities.logger import ThreadLogger

logger = ThreadLogger(__name__)

def get_aws_rh_and_region(resource):
    rh_aws_id = resource.aws_rh_id
    aws_region = resource.aws_region
    rh_aws = None

    if rh_aws_id is not None and rh_aws_id != "":
        rh_aws = AWSHandler.objects.filter(id=rh_aws_id).first()

    return aws_region, rh_aws


def run(job, logger=logger, **kwargs):
    resource = kwargs.pop('resources').first()

    msg = f"MySQL database Delete plugin running for resource: {resource}"
    set_progress(msg)

    mysql_database_identifier = resource.db_identifier

    # Get AWS region and resource handler object
    region, aws = get_aws_rh_and_region(resource)

    if not aws:
        return "WARNING", "", "Need a valid aws region to delete this database"

    set_progress('Connecting to Amazon MySQL Database...')

    # Initialize Boto3 RDS client
    client = aws.get_boto3_client(region, 'rds')

    subnet_group_name = None
    try:
        # Verify MySQL database instance and fetch Subnet Group Name
        rds_resp = client.describe_db_instances(DBInstanceIdentifier=mysql_database_identifier)
        if rds_resp.get('DBInstances'):
            db_inst = rds_resp['DBInstances'][0]
            subnet_group = db_inst.get('DBSubnetGroup', {})
            subnet_group_name = subnet_group.get('DBSubnetGroupName')
    except Exception as err:
        if "DBInstanceNotFound" in str(err):
            return "WARNING", f"MySQL Database instance {mysql_database_identifier} not found, it may have already been deleted", ""
        raise RuntimeError(err)

    msg = f'Deleting MySQL Database {mysql_database_identifier}...'
    set_progress(msg)

    # Delete MySQL Database from AWS
    client.delete_db_instance(
        DBInstanceIdentifier=mysql_database_identifier,
        SkipFinalSnapshot=True,
        DeleteAutomatedBackups=True,
    )

    waiter = client.get_waiter('db_instance_deleted')
    waiter.config.max_attempts = 100
    waiter.wait(DBInstanceIdentifier=mysql_database_identifier)

    # Delete DB Subnet Group if associated and unused by other DB instances
    if subnet_group_name:
        try:
            msg = f"Attempting to delete DB Subnet Group '{subnet_group_name}'..."
            set_progress(msg)


            client.delete_db_subnet_group(DBSubnetGroupName=subnet_group_name)

            success_msg = f"DB Subnet Group '{subnet_group_name}' deleted successfully."
            set_progress(success_msg)

        except Exception as e:
            warn_msg = f"Could not delete subnet group {subnet_group_name}: {str(e)}"
            logger.warning(warn_msg)

    final_msg = f"MySQL database {mysql_database_identifier} deleted successfully"
    set_progress(final_msg)

    return 'SUCCESS', final_msg, ''