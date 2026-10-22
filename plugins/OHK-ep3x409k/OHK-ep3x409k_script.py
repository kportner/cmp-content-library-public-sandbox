"""
List snapshot action for AWS MariaDB database snapshot.
"""
from resourcehandlers.aws.models import AWSHandler
from common.methods import set_progress
from infrastructure.models import CustomField
from resources.models import Resource, ResourceType


def create_custom_fields_as_needed():
    CustomField.objects.get_or_create(
        name='snapshots_status', defaults={'label': 'AWS MariaDB Snapshots Status', 'type': 'STR',
                'description': 'Used by the AWS MariaDB blueprint', 'show_on_servers':True , 'show_as_attribute':True}
    )
    
def run(job, resource, **kwargs):
    cf_value = resource.get_cf_values_as_dict()

    region = cf_value.get('aws_region', "")
    rh_id = cf_value.get('aws_rh_id', "")
    db_identifier = cf_value.get('db_identifier', "")

    handler: AWSHandler = AWSHandler.objects.get(id=rh_id)

    # get aws client object
    rds = handler.get_boto3_client(region, 'rds')
    
    set_progress(f'Getting all snapshots for "{db_identifier}"')

    # get or create sub resource type
    resource_type, _ = ResourceType.objects.get_or_create(
            name="aws_snapshot", defaults={"label": "AWS Snapshot", "icon": "far fa-file"}
        )
            
    response = rds.describe_db_snapshots(
        DBInstanceIdentifier=db_identifier, SnapshotType='manual'
    )
    
    for snapshot in response['DBSnapshots']:
        snapshot_resource, _ = Resource.objects.get_or_create(
            name=snapshot['DBSnapshotIdentifier'], 
            defaults={
                'blueprint': resource.blueprint,
                'group': resource.group,
                'parent_resource': resource,
                'resource_type': resource_type,
                'lifecycle':  "ACTIVE",
            }
        )
        
        snapshot_resource.snapshot_status =  snapshot['Status']
        snapshot_resource.save()

    return "SUCCESS", "MariaDB database snapshot synced successfully.", ""