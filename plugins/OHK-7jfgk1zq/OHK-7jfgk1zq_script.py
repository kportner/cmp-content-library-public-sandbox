"""
Teardown service item action for AWS MariaDB database.
"""
from common.methods import set_progress
from resourcehandlers.aws.models import AWSHandler
from resources.models import Resource

def delete_sub_resources(resource):
    for sub_resource in Resource.objects.filter(parent_resource=resource):
        sub_resource.delete()
        
def run(job, logger=None, **kwargs):
    resource = kwargs.pop('resources').first()
    
    cf_value = resource.get_cf_values_as_dict()
    
    db_identifier = cf_value.get("db_identifier", "")
    
    if db_identifier == "":
        return 'SUCCESS', f"MariaDB Database {db_identifier} deleted successfully", ''
    
    rh: AWSHandler = AWSHandler.objects.get(id=cf_value.get("aws_rh_id", ""))

    # get aws client object
    rds = rh.get_boto3_client(resource.aws_region, 'rds')
    
    set_progress('Deleting AWS MariaDB database "{}"'.format(db_identifier))
    
    try:
        rsp = rds.describe_db_instances(DBInstanceIdentifier=db_identifier)['DBInstances']
    except Exception as err:
        # delete sub resources
        delete_sub_resources(resource)
        return 'SUCCESS', f"MariaDB Database {db_identifier} deleted successfully", ''
            
    # delete all db snapshot
    for snapshot in rds.describe_db_snapshots(
                DBInstanceIdentifier=db_identifier, SnapshotType='manual'
            )['DBSnapshots']:
        
        rds.delete_db_snapshot(
            DBSnapshotIdentifier= snapshot['DBSnapshotIdentifier'],
        )
        
    delete_sub_resources(resource)
    
    rds.delete_db_instance(
        DBInstanceIdentifier=db_identifier,
        SkipFinalSnapshot=True,
    )

    waiter = rds.get_waiter('db_instance_deleted')
    set_progress("...waiting for DBSnapshot to be delete...")
    waiter.wait(DBInstanceIdentifier=db_identifier)

    return 'SUCCESS', f"MariaDB Database {db_identifier} deleted successfully", ''