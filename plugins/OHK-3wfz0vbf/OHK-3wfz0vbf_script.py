"""
Teardown service item action for AWS Aurora database.
"""
import time
from common.methods import set_progress
from resourcehandlers.aws.models import AWSHandler
from utilities.logger import ThreadLogger

logger = ThreadLogger(__name__)

def get_boto3_service_client(aws_region, rh: AWSHandler, service_name="rds"):
    """
    Return boto connection to the RDS in the specified environment's region.
    """

    # get aws client object
    client = rh.get_boto3_client(aws_region, service_name)

    return client
    
def run(job, logger=None, **kwargs):
    resource = kwargs.pop('resources').first()
    set_progress(f"Aurora database Delete plugin running for resource: {resource}")
    logger.info(f"Aurora database Delete plugin running for resource: {resource}")

    # Aurora Database Identifier
    cluster_identifier = resource.get_cf_values_as_dict().get('db_cluster_identifier')
    # resource aws region
    region = resource.get_cf_values_as_dict().get('aws_region')
    # aws handler id
    rh_id = resource.get_cf_values_as_dict().get('aws_rh_id')
    # aws resource handler
    rh = AWSHandler.objects.get(id=rh_id)

    set_progress('Connecting to Amazon RDS')

    # rds client
    rds = get_boto3_service_client(region, rh)

    # Find the cluster and it's instances
    try:
        response = rds.describe_db_clusters(DBClusterIdentifier=cluster_identifier)
    except rds.exceptions.DBClusterNotFoundFault:
        return "FAILURE", "Database cluster does not exist", ""
        
    clust = response['DBClusters'][0]
    # WARNING
    if clust['Status'] != 'available':
        return "FAILURE", f"RDS Aurora Db Cluster {cluster_identifier} is in-process state of '{clust['Status']}', try after process state get available.", ""

    instances_to_delete = [inst['DBInstanceIdentifier'] for inst in clust['DBClusterMembers']]

    set_progress("Instance(s) to be deleted: %s" % instances_to_delete)

    for inst_id in instances_to_delete:
        set_progress('Deleting AWS database instance "{}"'.format(inst_id))
        response = rds.delete_db_instance(
            DBInstanceIdentifier=inst_id,
            SkipFinalSnapshot=True,
        )

    set_progress('Deleting AWS Aurora database cluster "{}"'.format(cluster_identifier))
    response = rds.delete_db_cluster(
        DBClusterIdentifier=cluster_identifier,
        SkipFinalSnapshot=True,
    )

    set_progress('Waiting for deletions to finalize...')

    while instances_to_delete:
        time.sleep(5)
        for inst_id in instances_to_delete:
            try:
                response = rds.describe_db_instances(DBInstanceIdentifier=inst_id)
            except rds.exceptions.DBInstanceNotFoundFault:
                # Database is finally deleted
                set_progress('Database instance %s is now deleted' % inst_id)
                instances_to_delete.remove(inst_id)
            else:
                db_instance = response['DBInstances'][0]
                status = db_instance['DBInstanceStatus']
                set_progress('Status of the database instance %s is: %s' % (inst_id, status))


    return 'SUCCESS', f"Aurora database {cluster_identifier} deleted successfully", ''