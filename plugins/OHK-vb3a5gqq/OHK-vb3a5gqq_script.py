from common.methods import set_progress
from resourcehandlers.aws.models import AWSHandler
from infrastructure.models import Environment


RESOURCE_IDENTIFIER = 'aws_function_name'

def get_boto3_service_client(rh: AWSHandler, aws_region, service_name="lambda"):
    """
    Return boto connection to the LAMBDA in the specified environment's region.
    """

    # get aws client object
    client = rh.get_boto3_client(aws_region, service_name)

    return client
    

def discover_resources(**kwargs):
    lambda_functions = []
    for handler in AWSHandler.objects.all():
        set_progress('Connecting to Amazon Lambda for handler: {}'.format(handler))
        for region in handler.current_regions():
            set_progress('Connecting to Amazon Lmabda for handler: {}'.format(handler))
            conn = get_boto3_service_client(handler, region)
            try:
                for lambda_response in conn.list_functions()['Functions']:
                    lambda_functions.append({
                            "aws_region": region,
                            "aws_rh_id": handler.id,
                            "aws_function_name": lambda_response['FunctionName']
                            })
            except Exception as e:
                set_progress('AWS ClientError: {}'.format(e))
                continue

    return lambda_functions