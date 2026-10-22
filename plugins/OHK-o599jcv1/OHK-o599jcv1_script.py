"""
Delete backup for AWS Dynamo DB.
"""
from resourcehandlers.aws.models import AWSHandler
from common.methods import set_progress
from resources.models import Resource
from infrastructure.models import CustomField

def create_custom_fields_as_needed():
    CustomField.objects.get_or_create(
        name='backup_name', defaults={
            'label': 'Dynamo Db Backup name', 'type': 'STR',
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


def generate_options_for_backup_name(resource, **kwargs):
    if resource is None or resource == "":
        return []
        
    return [(sub_resource.id, sub_resource.name) for sub_resource in Resource.objects.filter(parent_resource=resource, lifecycle="Active")]
    

def run(resource, **kwargs):
    # create custom fields if needed
    create_custom_fields_as_needed()
    
    sub_resource =  Resource.objects.get(id="{{backup_name}}") 

    handler = AWSHandler.objects.get(id=resource.aws_rh_id)
    
    set_progress('Connecting to Amazon Dynamodb')
    
    # get boto3 dynmodb client
    dynamodb = get_boto3_service_client(handler, resource.aws_region)

    
    set_progress('Deleting backup for "{}"'.format(sub_resource.name))

    try:
        # delete backup from AWS server
        backup_rsp = dynamodb.delete_backup(BackupArn=sub_resource.backup_arn)
    except Exception as error:
        return "FAILURE", "", f"{error}"

    sub_resource.delete()

    return "SUCCESS", f"DynamoDB table backup {sub_resource.name} deleted successfully.", ""