from common.methods import set_progress
from infrastructure.models import CustomField
from resourcehandlers.aws.models import AWSHandler
from datetime import datetime
from resources.models import Resource
from servicecatalog.models import BlueprintServiceItem,ServiceBlueprint
from orders.models import Order
import boto3,re,ast,time


def get_or_create_custom_fields():
    CustomField.objects.get_or_create(
        name='aws_rh_id_for_hosted_zone',
        defaults={
            "label": 'AWS Resource Handler ID used for hosted zone',
            "type": 'INT',
            'show_as_attribute': False,
            "description": 'Used by the HA Architecture blueprint'
        }
    )
    CustomField.objects.get_or_create(
        name='hosted_zone_id',
        defaults={
            "label": 'Hosted Zone ID',
            "type": 'STR',
            'show_as_attribute': False,
            "description": 'Used by the HA Architecture blueprint'
        }
    )
    CustomField.objects.get_or_create(
        name='ha_endpoint',
        defaults={
            "label": "A Endpoint URL",
            "type": 'URL',
            'show_as_attribute': True,
            "description": 'Used by the HA Architecture blueprint'
        }
    )
    
def get_boto3_client(aws_id, service, region=None):
    try:
        rh = AWSHandler.objects.get(id=aws_id)
        wrapper = rh.get_api_wrapper()
    except Exception:
        return

    client = wrapper.get_boto3_client(
        service,
        rh.serviceaccount,
        rh.servicepasswd,
        region
    )
    return client
    
def get_instance_location_dict(**kwargs):
    raw_list = kwargs.get("raw_list")
    instance_locations_dict = {}
    if len(raw_list)==1 and raw_list[0]=="":
        return instance_locations_dict
    if len(raw_list)==0:
        return instance_locations_dict
    # rh_id = int(raw_list[0].split("@")[-1])
    for val in raw_list:
        temp = val.split(")")[0].split("(") 
        if temp[1] in instance_locations_dict.keys():
            instance_locations_dict[temp[1]].append(temp[0])
        else:   
            instance_locations_dict[temp[1]] = [temp[0]]
    return instance_locations_dict

def generate_options_for_existing_hosted_zone(**kwargs):
    return [
            ('','-- Select Choice --'),
            ('Yes', 'Use Exisitng Hosted Zone'),
            ('No', 'Create New Hosted Zone'),
        ]

def generate_options_for_aws_rh_for_hosted_zone(control_value=None,**kwargs):
    options = [("","First Select to use existing hosted zone or not...")]
    if control_value == 'Yes':
        options = []
        rhs = AWSHandler.objects.all().values("id", "name")
        options = [(f"{rh['id']}/Yes", rh['name']) for rh in rhs]
        
    elif control_value == 'No':
        parent_bp = kwargs.get('blueprint')
        cf_dict = parent_bp.get_cf_values_as_dict()
        if 'global_ha_architecture_rh_id' in cf_dict.keys():
            rh_id = cf_dict['global_ha_architecture_rh_id']
            rh = AWSHandler.objects.get(id=rh_id)
            options = [(f"{rh_id}/No",rh.name)]
    return options
    
def generate_options_for_zone_id(control_value=None, **kwargs):
    options = [("","--Select AWS Resource Handler first--")]
    rh_id = None
    parent_bp = kwargs.get('blueprint')
    if control_value:
        rh_id = int(control_value.split("/")[0])
        existing_hosted_zone = control_value.split("/")[-1]
        if existing_hosted_zone == 'Yes':
            options = [("","-- Select Hosted Zone --")]
            route53_client = get_boto3_client(rh_id, 'route53', region=None)
            zones = route53_client.list_hosted_zones()['HostedZones']
            if zones:
                for z in zones:
                    id = z.get('Id').replace('/hostedzone/', '')
                    name = z['Name'].rstrip(".")
                    options.append((f"{id}:{name}", f"{name}({id})"))
            else:
                options.append(("", "No hosted zones found, please create new or select another resource handler"))
        else:
            options = [("NA","-- Create New Hosted Zone --")]
    return options

def generate_options_for_domain_name(control_value=None, **kwargs):
    options = [("","-- Loading domains --")]
    rh_id = None
    parent_bp = kwargs.get('blueprint')
    if control_value:
        existing_hosted_zone = control_value.split("/")[-1]
        cf_dict = parent_bp.get_cf_values_as_dict()
        if existing_hosted_zone == 'No':
            if 'global_ha_architecture_rh_id' in cf_dict.keys():
                rh_id = cf_dict['global_ha_architecture_rh_id']
                rh = AWSHandler.objects.get(id=rh_id)
                route53domains_client = get_boto3_client(rh_id, 'route53domains', region='us-east-1')  #Currently domain works only for us-east-1 region
                domain_response = route53domains_client.list_domains()
                if domain_response['Domains']:
                    options = [("","-- Select Domain Name --")]
                    options.extend([(domain['DomainName'],domain['DomainName']) for domain in domain_response['Domains']])
                else:
                    options = [("",f"No domains available in '{rh.name}' account, kindly create first and then retry...")]    
        else:
            options = [("NA","--Not Required--")]
    return options

def run(job, *args, **kwargs):
    resource = kwargs.get('resource')
    use_existing_hosted_zone = '{{existing_hosted_zone}}'
    aws_rh_for_hosted_zone = '{{aws_rh_for_hosted_zone}}'
    domain_name = '{{domain_name}}'
    zone_id = '{{zone_id}}'
    
    caller_reference = "HA"+domain_name+str(datetime.now())
    base_name = resource.base_name.replace(" ","-")
    endpoint_url = f'''{base_name}.{zone_id.split(":")[-1]}''' if use_existing_hosted_zone == "Yes" else f'''{base_name}.{domain_name}'''
    rh_id = resource.aws_rh_id
    
    route53_client = get_boto3_client(rh_id, 'route53', region=None)
    
    get_or_create_custom_fields()
    
    if use_existing_hosted_zone == "Yes":
        hosted_zone_id = zone_id.split(":")[0]
        set_progress(f"Exisitng Hosted zone '{hosted_zone_id}' is used")
    else:
        try:
            response = route53_client.create_hosted_zone(
                Name=domain_name,
                CallerReference=caller_reference,
                HostedZoneConfig={
                    'Comment': "Created by HA Architectue blueprint",
                    'PrivateZone': False
                }
            )
        except route53_client.exceptions.HostedZoneAlreadyExists:
            # No need to create hosted zone if it already exist for selected domain
            zones = route53_client.list_hosted_zones()['HostedZones']
            hosted_zone_id = [zone['Id'].replace("/hostedzone/","") for zone in zones if domain_name in zone['Name']][0]
        else:
            hosted_zone_id = response['HostedZone'].get('Id').split("/")[-1]
            set_progress(f"New Hosted zone '{hosted_zone_id}' is created")
            
    resource.aws_rh_id_for_hosted_zone = int(aws_rh_for_hosted_zone.split("/")[0])
    resource.hosted_zone_id = hosted_zone_id
    resource.ha_endpoint = endpoint_url
    return "SUCCESS", "route53 hosted zone created successfully", ""