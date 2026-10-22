from resourcehandlers.aws.models import AWSHandler
from common.methods import set_progress


RESOURCE_IDENTIFIER = ['table_name', 'aws_region']

def get_boto3_service_client(rh: AWSHandler, aws_region, service_name="dynamodb"):
    """
    Return boto connection to the DYNAMODB in the specified environment's region.
    """
    # get aws client object
    client = rh.get_boto3_client(aws_region, service_name)

    return client


def discover_resources(**kwargs):
    discovered_tables = []


    for rh in AWSHandler.objects.all():
        
        # Retrieving unique list of active/imported regions for 'rh' resource handler
        imported_region_list = list(rh.current_regions())
        
        for region in imported_region_list:
           
            dynamodb = get_boto3_service_client(rh, region)
            try:
                tables = dynamodb.list_tables()['TableNames']
            except Exception as e:
                set_progress(e)
                continue
            
            for table in tables:
                data = {
                    'name': table,
                    'aws_rh_id': rh.id,
                    'aws_region': region,
                    'table_name': table,
                }
                

                if data not in discovered_tables:
                    discovered_tables.append(data)
                        
    return discovered_tables