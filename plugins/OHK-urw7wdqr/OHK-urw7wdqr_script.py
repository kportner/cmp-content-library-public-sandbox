"""
Sync backup for AWS Dynamo DB.
"""
from resourcehandlers.aws.models import AWSHandler
from common.methods import set_progress
from resources.models import Resource, ResourceType
from infrastructure.models import CustomField

def create_custom_fields_as_needed():
    CustomField.objects.get_or_create(
        name='backup_arn', defaults={
            'label': 'Dynamo Db Backup ARN', 'type': 'STR',
            'show_as_attribute': True,
            'description': 'Used while deleting a backup'
        }
    )

    
def get_boto3_service_client(rh: AWSHandler, aws_region, service_name="dynamodb"):
    """
    Return boto connection to the DYNAMODB in the specified environment's region.
    """

    # get aws client object
    client = rh.get_boto3_client(aws_region, service_name)

    return client



def run(resource, **kwargs):
    
    # create custom fields if needed
    create_custom_fields_as_needed()
    
    # get or create new resource type
    resource_type, _ = ResourceType.objects.get_or_create(name='Backup', defaults={"label": "Backup", "icon": "far fa-file"})

    handler = AWSHandler.objects.get(id=resource.aws_rh_id)
    
    set_progress('Connecting to Amazon Dynamodb')
    
    # get boto3 dynmodb client
    dynamodb = get_boto3_service_client(handler, resource.aws_region)
    
    set_progress('Creating backup for "{}"'.format(resource.table_name))

    try:
        # get backup list from AWS server
        backup_rsp = dynamodb.list_backups(TableName=resource.table_name)['BackupSummaries']
    except Exception as error:
        return "FAILURE", "", f"{error}"

    set_progress(f'Backup Response {backup_rsp}')
    
    for backup_obj in backup_rsp:

        # get backup resource
        sbu_res = Resource.objects.filter(name=backup_obj['BackupName'], blueprint=resource.blueprint, resource_type = resource_type).first()
        
        if sbu_res is None:
            # create new backup resource
            sbu_res = Resource.objects.create(name=backup_obj['BackupName'], blueprint=resource.blueprint, resource_type = resource_type, group=resource.group)
            
        sbu_res.backup_arn = backup_obj['BackupArn']
        sbu_res.parent_resource = resource
        sbu_res.lifecycle = 'Active'
        sbu_res.aws_rh_id = resource.aws_rh_id
        sbu_res.aws_region = resource.aws_region
        sbu_res.save()

    return "SUCCESS", f"DynamoDB table backup synced successfully.", ""