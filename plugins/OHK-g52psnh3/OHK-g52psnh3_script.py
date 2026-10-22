from common.methods import set_progress
from resourcehandlers.aws.models import AWSHandler

def get_boto3_service_client(rh: AWSHandler, aws_region, service_name="dynamodb"):
    """
    Return boto connection to the DYNAMODB in the specified environment's region.
    """
    # get aws client object
    client = rh.get_boto3_client(aws_region, service_name)

    return client


def run(resource, *args, **kwargs):
    rh = AWSHandler.objects.get(id=resource.aws_rh_id)

    dynamodb = get_boto3_service_client(rh, resource.aws_region)
    
    try:
        response = dynamodb.delete_table(
            TableName=resource.table_name
        )
    except Exception as err:
        return "FAILURE", "", f"{err}"
        
    return "SUCCESS", f"Dynamodb table {resource.table_name} deleted successfully.", ""