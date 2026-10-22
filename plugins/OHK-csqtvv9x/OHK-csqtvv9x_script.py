"""
Take snapshot action for AWS MariaDB database.
"""
from resourcehandlers.aws.models import AWSHandler
from common.methods import set_progress
from botocore.client import ClientError
from infrastructure.models import CustomField
from resources.models import Resource, ResourceType

def create_custom_fields_as_needed():
    CustomField.objects.get_or_create(
        name='snapshot_status', defaults={'label': 'AWS MariaDB Snapshots Status', 'type': 'STR',
            'description': 'Used by the AWS MariaDB blueprint', 'show_on_servers':True , 'show_as_attribute':True}
    )
    
def run(job, resource, **kwargs):
    snapshot_identifier = '{{ snapshot_identifier }}'
    
    cf_value = resource.get_cf_values_as_dict()
    
    region = cf_value.get('aws_region', "")
    rh_id = cf_value.get('aws_rh_id', "")
    db_identifier = cf_value.get('db_identifier', "")
    
    create_custom_fields_as_needed()
    
    handler: AWSHandler = AWSHandler.objects.get(id=rh_id)
    
    # get or create sub resource type
    resource_type, _ = ResourceType.objects.get_or_create(
            name="aws_snapshot", defaults={"label": "AWS Snapshot", "icon": "far fa-file"})
            
    # get aws client object
    rds = handler.get_boto3_client(region, 'rds')

    set_progress('Creating a snapshot for "{}"'.format(db_identifier))
    
    try:
        snapshot = rds.create_db_snapshot(
            DBSnapshotIdentifier= snapshot_identifier,
            DBInstanceIdentifier= db_identifier,
        )
    except ClientError as e:
        set_progress('AWS ClientError: {}'.format(e))
        return "FAILURE", 'AWS ClientError: {}'.format(e), ""
    
    waiter = rds.get_waiter('db_snapshot_available')
    set_progress("...waiting for DBSnapshot to be ready...")
    waiter.wait(DBSnapshotIdentifier=snapshot_identifier)
    
    snapshot_resource, _ = Resource.objects.get_or_create(
            name = snapshot_identifier,
            defaults = {
                'blueprint': resource.blueprint,
                'group': resource.group,
                'parent_resource': resource,
                'resource_type': resource_type,
                'lifecycle': "ACTIVE"
            }
        )
    snapshot_resource.snapshot_status =  "Available"
    snapshot_resource.save()
        
    return "SUCCESS", "Cluster has succesfully been created", ""