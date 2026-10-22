"""
Delete snapshot action for AWS MariaDB database snapshot.
"""
from resourcehandlers.aws.models import AWSHandler
from common.methods import set_progress
from resources.models import Resource, ResourceType
from botocore.client import ClientError


def generate_options_for_snapshots(resource, **kwargs):
    if resource is None or resource == "":
        return []
        
    # get or create sub resource type
    resource_type, _ = ResourceType.objects.get_or_create(
            name="aws_snapshot", defaults={"label": "AWS Snapshot", "icon": "far fa-file"})
            
    return [(sub_resource.id, sub_resource.name) for sub_resource in Resource.objects.filter(parent_resource=resource, resource_type=resource_type, lifecycle="ACTIVE")]
    

def run(job, resource, **kwargs):
    cf_value = resource.get_cf_values_as_dict()

    handler: AWSHandler = AWSHandler.objects.get(id=cf_value.get('aws_rh_id', ""))
    
    snapshot =  Resource.objects.get(id="{{ snapshots }}")
    
    rds = handler.get_boto3_client(resource.aws_region, 'rds')

    set_progress('Deleting snapshot "{}"'.format(snapshot.name))

    try:
        response = rds.delete_db_snapshot(
            DBSnapshotIdentifier= snapshot.name,
        )
    except ClientError as e:
        set_progress('AWS ClientError: {}'.format(e))
        return "FAILURE", 'AWS ClientError: {}'.format(e), ""
    
    snapshot.delete()
    
    return "SUCCESS", "Snapshot deleted succesfully", ""