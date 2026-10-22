"""
Discover MariaDB records with some identifying attributes
return a list of dictionaries from the 'discover_resoures' function
"""
from botocore.client import ClientError
from common.methods import set_progress
from resourcehandlers.aws.models import AWSHandler

RESOURCE_IDENTIFIER = 'db_identifier'


def discover_resources(**kwargs):
    discovered_mariadb = []
    
    handler: AWSHandler
    for handler in AWSHandler.objects.all():
        set_progress('Connecting to Amazon Maria DB for handler: {}'.format(handler))

        for region in handler.current_regions():

            # get aws client object
            rds = handler.get_boto3_client(region, 'rds')
           
            try:
                for db in rds.describe_db_instances()['DBInstances']:
                    if db['Engine'] == 'mariadb':
                        discovered_mariadb.append(
                            {
                                'name': 'RDS MariaDB - ' + db['DBInstanceIdentifier'],
                                'db_address': db['Endpoint']['Address'],
                                'db_port': db['Endpoint']['Port'],
                                'db_identifier': db['DBInstanceIdentifier'],
                                'aws_rh_id': handler.id,
                                'aws_region': region
                            }
                        )
            except ClientError as e:
                set_progress('AWS ClientError: {}'.format(e))
                continue

    return discovered_mariadb