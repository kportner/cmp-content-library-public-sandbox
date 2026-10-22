"""
Teardown service item action for AWS Lambda blueprint.
"""
from common.methods import set_progress
from resourcehandlers.aws.models import AWSHandler

def get_boto3_service_client(rh: AWSHandler, aws_region, service_name="lambda"):
    """
    Return boto connection to the LAMBDA in the specified environment's region.
    """

    # get aws client object
    client = rh.get_boto3_client(aws_region, service_name)

    return client

def run(job, logger=None, **kwargs):
    resource = kwargs.pop('resources').first()

    function_name = resource.attributes.get(field__name='aws_function_name').value
    rh_id = resource.attributes.get(field__name='aws_rh_id').value
    region = resource.attributes.get(field__name='aws_region').value
    rh = AWSHandler.objects.get(id=rh_id)

    set_progress('Connecting to AWS...')
    client = get_boto3_service_client(rh, region)
    set_progress('Deleting function "%s"' % function_name)
    client.delete_function(
        FunctionName=function_name
    )

    return "", "", ""