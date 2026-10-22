"""
This CloudBolt plug-in collects deployment parameters (Resource Handler, Region, 
Zones, VPC, CloudBolt Version, and Instance Type) on Step 1 of the HA Architecture blueprint.
"""
import ast
import json
import os
import re
import boto3

from common.methods import set_progress
from infrastructure.models import CustomField
from resourcehandlers.aws.models import AWSHandler
from utilities.logger import ThreadLogger

logger = ThreadLogger(__name__)

def get_or_create_custom_fields():
    CustomField.objects.get_or_create(
        name='base_name',
        defaults={
            "label": 'Base Name',
            "type": 'STR',
            'show_as_attribute': True,
            "description": 'Used by the HA Architecture parent blueprint'
        }
    )
    CustomField.objects.get_or_create(
        name='aws_rh_name_ha',
        defaults={
            "label": 'AWS Resource Handler',
            "type": 'STR',
            'show_as_attribute': True,
            "description": 'Used by the HA Architecture parent blueprint'
        }
    )
    CustomField.objects.get_or_create(
        name='aws_rh_id',
        defaults={
            "label": 'AWS Resource Handler id',
            "type": 'INT',
            'show_as_attribute': False,
            "description": 'Used by the HA Architecture parent blueprint'
        }
    )
    CustomField.objects.get_or_create(
        name='aws_region_ha',
        defaults={
            "label": 'AWS Region',
            "type": 'STR',
            'show_as_attribute': True,
            "description": 'Used by the HA Architecture parent blueprint'
        }
    )
    CustomField.objects.get_or_create(
        name='aws_zone_region_list_ha',
        defaults={
            "label": 'Instance Locations List',
            "type": 'TUP',
            'show_as_attribute': False,
            "description": 'Used by the HA Architecture parent blueprint'
        }
    )
    CustomField.objects.get_or_create(
        name='instance_locations',
        defaults={
            "label": 'Instance Locations',
            "type": 'STR',
            'show_as_attribute': True,
            "description": 'Used by the HA Architecture parent blueprint'
        }
    )
    CustomField.objects.get_or_create(
        name='vpc_selection',
        defaults={
            "label": 'VPC Selection',
            "type": 'TUP',
            'show_as_attribute': False,
            "description": 'Used by the HA Architecture parent blueprint'
        }
    )
    CustomField.objects.get_or_create(
        name='aws_ha_cb_version',
        defaults={
            "label": 'CloudBolt Application Version',
            "type": 'STR',
            'show_as_attribute': True,
            "description": 'Used by the HA Architecture parent blueprint'
        }
    )
    CustomField.objects.get_or_create(
        name='aws_ha_instance_type',
        defaults={
            "label": 'Instance Type',
            "type": 'STR',
            'show_as_attribute': True,
            "description": 'Used by the HA Architecture parent blueprint'
        }
    )


def get_boto3_ec2_client(**kwargs):
    rh = kwargs.get('resource_handler')
    region = kwargs.get('region')
    wrapper = rh.get_api_wrapper()
    return wrapper.get_boto3_client('ec2', rh.serviceaccount, rh.servicepasswd, region)


def store_base_url(form_data, current_bp):
    CustomField.objects.get_or_create(
        name='order_base_url',
        defaults={"label": 'Order base url', "type": 'STR'}
    )
    fa = form_data.get("form-action", None) if form_data else None
    if fa:
        current_bp.set_value_for_custom_field(
            cf_name='order_base_url',
            value=fa[0].split("catalog")[0]
        )


def get_available_zones(**kwargs):
    """ This function will return all the zones available in region passed in 
        kwargs as 'region' with the help of boto3 client created with resource handler
        provided in kwargs as 'resource_handler_id'
    """
    region = kwargs.get('region')
    rh_id = kwargs.get('resource_handler_id')
    rh = AWSHandler.objects.get(id=int(rh_id))
    client = get_boto3_ec2_client(resource_handler=rh, region=region)
    try:
        response = client.describe_availability_zones(
            Filters=[
                {
                    'Name': 'region-name',
                    'Values': [region,]
                }])
    except Exception:
        return []
    zone_list = [zone['ZoneName'] for zone in response.get('AvailabilityZones', [])]
    return zone_list


def generate_options_for_aws_resource_handler(field, control_value=None, **kwargs):
    current_bp = kwargs.get('blueprint')
    options = [("", "-- Select Single Resource Handler --")]
    if control_value:
        options = []
        CustomField.objects.get_or_create(
            name='global_ha_base_name',
            defaults={"label": 'Global base name for all resources', "type": 'STR'}
        )
        current_bp.set_value_for_custom_field(cf_name='global_ha_base_name', value=control_value)   #Set the Global rhID variable as a customfield
        for rh in AWSHandler.objects.all():
            options.append((rh.id, rh.name))
    return options
    # return sorted(options, key=lambda tup: tup[1].lower())


def generate_options_for_aws_ha_region(control_value=None, **kwargs):
    current_bp = kwargs.get('blueprint')
    options = [("", "-- Select Single Region --")]
    if control_value:
        store_base_url(kwargs.get("form_data", {}), current_bp)
        CustomField.objects.get_or_create(
            name='global_ha_architecture_rh_id',
            defaults={"label": 'Global base name for all resources', "type": 'INT'}
        )
        current_bp.set_value_for_custom_field(cf_name='global_ha_architecture_rh_id', value=control_value)   #Set the Global rhID variable as a customfield
        rh_id = control_value
        rh = AWSHandler.objects.get(id=rh_id)
        wrapper = rh.get_api_wrapper()
        for item in wrapper.get_all_regions():
            options.append(("{}@{}".format(control_value, item['name']), item['display']))
    return options


def generate_options_for_aws_ha_zone_region_pair(control_value=None, **kwargs):
    """ This will generate options as 'zone1 (Region1)@Rh_ID','zone2 (Region1)@Rh_ID','zone3 (Region2)@Rh_ID,...so on
        for all zones in all valid/allowed regions
    """
    current_bp = kwargs.get('blueprint')
    options = [("", "--Select Availability Zones--")]
    if control_value:
        store_base_url(kwargs.get("form_data", {}), current_bp)  #just to make sure we store order url
        rh_id = control_value.split("@")[0]
        region = control_value.split("@")[-1]
        CustomField.objects.get_or_create(
            name='global_ha_architecture_rh_id',
            defaults={"label": 'Global HA Architecture AWS RH ID', "type": 'INT'}
        )
        current_bp.set_value_for_custom_field(cf_name='global_ha_architecture_rh_id', value=rh_id)   #Set the Global rhID variable as a customfield
        options = []

        rh = AWSHandler.objects.get(id=rh_id)
        label = region.replace('-', ' ')
        list_of_zones = get_available_zones(resource_handler_id=rh_id, region=region)
        if len(list_of_zones) == 0:
            options.append(("", "-- Select another region, this region is not supported --"))
        else:
            for zone in list_of_zones:
                options.append(("{0} ({1})@{2}".format(zone, region, rh_id), "{0} ({1})".format(zone, label)))

    return options


def generate_options_for_aws_ha_existing_vpc(control_values=None, **kwargs):
    """ This returns all the available VPCs from the regions selected by user in slelect Instance location choice
    """
    current_bp = kwargs.get('blueprint')
    options = [("Not Selected Any", "Create new VPC")]
    if control_values:
        if "" in control_values:
            return [("", "-- Select Existing or Create New VPC --")]
        CustomField.objects.get_or_create(
            name='global_ha_architecture_locations',
            defaults={"label": 'Global HA Architecture AWS selected zones', "type": 'STR'}
        )
        zone_selection_list = []
        instance_locations_list = control_values
        rh_id = int(control_values[0].split("@")[-1])
        region = control_values[0].split(")")[0].split("(")[-1]
        rh = AWSHandler.objects.get(id=rh_id)
        for ele in instance_locations_list:
            zone_selection_list.append(ele.split("@")[0])
        current_bp.set_value_for_custom_field(cf_name='global_ha_architecture_locations', value=",".join(zone_selection_list))   #Set the Global locations variable as a customfield
        client = get_boto3_ec2_client(resource_handler=rh, region=region)
        response = client.describe_vpcs()
        resp = response.get('Vpcs', [])
        for vpc in resp:
            label = "{0} @ {1}".format(vpc["VpcId"], region)
            options.append((label, label))
    return options


def generate_options_for_aws_ha_cb_version(control_value=None, control_values=None, **kwargs):
    """ Dynamically fetches available CloudBolt versions from AWS AMIs. """
    options = [("", "-- Select CloudBolt Application Version --")]
    
    current_bp = kwargs.get('blueprint')
    cf_dict = current_bp.get_cf_values_as_dict() if current_bp else {}
    rh_id = cf_dict.get('global_ha_architecture_rh_id')
    
    req = kwargs.get('request')
    region = None

    # 1. Parse region from control values
    val = control_value or (control_values[0] if control_values and len(control_values) > 0 else None)
    if isinstance(val, (list, tuple)) and len(val) > 0:
        val = val[0]

    if val:
        if "(" in val and ")" in val:
            region = val.split(")")[0].split("(")[-1]
        elif "@" in val:
            region = val.split("@")[-1]

    # 2. Inspect live HTTP request GET parameters
    if not region and req:
        for key, raw_val in req.GET.items():
            if 'aws_ha_zone_region_pair' in key or 'aws_ha_region' in key:
                if raw_val and raw_val != "Not Selected Any":
                    if "(" in raw_val and ")" in raw_val:
                        region = raw_val.split(")")[0].split("(")[-1]
                    elif "@" in raw_val:
                        region = raw_val.split("@")[-1]
                    else:
                        region = raw_val
                    if region:
                        break

    if not region:
        region = cf_dict.get('aws_region_ha')

    # Query AWS EC2 AMIs
    if rh_id and region:
        try:
            rh = AWSHandler.objects.get(id=rh_id)
            client = get_boto3_ec2_client(resource_handler=rh, region=region)
            response = client.describe_images(
                Filters=[
                    {'Name': 'state', 'Values': ['available']},
                    {'Name': 'name', 'Values': ['*CloudBolt*']}
                ]
            )
            
            images = response.get('Images', [])
            images = sorted(images, key=lambda x: x.get('CreationDate', ''), reverse=True)

            version_set = set()
            pattern = r"v?20\d{2}\.\d+(?:\.\d+)?"
            
            for img in images:
                name = img.get('Name', '')
                match = re.search(pattern, name)
                if match:
                    ver_raw = match.group()
                    clean_ver = ver_raw if ver_raw.startswith('v') else f"v{ver_raw}"
                    if clean_ver not in version_set:
                        version_set.add(clean_ver)
                        options.append((clean_ver, f"CloudBolt {clean_ver} ({region})"))
        except Exception:
            pass

    if len(options) == 1:
        if region:
            options = [("", f"-- No CloudBolt AMIs found in region '{region}' --")]
        else:
            options = [("", "-- Select AWS Region / Zones first --")]

    return options


def generate_options_for_aws_ha_instance_type(control_value=None, control_values=None, **kwargs):
    """ Returns only instance types compatible with the selected AWS Region and
        CloudBolt Version - Marketplace AMIs are restricted to enterprise Nitro
        types, Private Custom AMIs also unlock burstable t3 types.
    """
    req = kwargs.get('request')
    control_value_dict = kwargs.get('control_value_dict') or {}

    nitro_enterprise_types = [
        "m5.large", "m5.xlarge", "m5.2xlarge", "m5.4xlarge", "m5.12xlarge", "m5.24xlarge",
        "m5a.large", "m5a.xlarge", "m5a.2xlarge", "m5a.4xlarge", "m5a.8xlarge", "m5a.12xlarge", "m5a.16xlarge", "m5a.24xlarge",
        "m6i.large", "m6i.xlarge", "m6i.2xlarge", "m6i.4xlarge",
        "c5.large", "c5.xlarge", "c5.2xlarge", "c5.4xlarge",
        "c5a.large", "c5a.xlarge", "c5a.2xlarge", "c5a.4xlarge"
    ]
    burstable_types = ["t3.medium", "t3.large", "t3.xlarge", "t3.2xlarge"]

    options = [("", "-- Select Instance Type --")]

    current_bp = kwargs.get('blueprint')
    cf_dict = current_bp.get_cf_values_as_dict() if current_bp else {}

    rh_id = None
    region = None
    selected_version = None

    def try_extract_version(s):
        m = re.search(r"20\d{2}\.\d+(?:\.\d+)?", str(s))
        return m.group() if m else None

    # 1. Read directly from control_value_dict - this is how CloudBolt passes values
    # for a field with multiple declared dependencies (region + version here).
    region_val = control_value_dict.get('aws_ha_region')
    if region_val:
        region_val = str(region_val).strip()
        if "@" in region_val:
            parts = region_val.split("@")
            left, right = parts[0].strip(), parts[-1].strip()
            if left.isdigit():
                rh_id = left
                region = right
            elif right.isdigit():
                rh_id = right
                region = left

    version_val = control_value_dict.get('aws_ha_cb_version')
    if version_val:
        version_val = str(version_val).strip()
        if version_val:
            selected_version = version_val

    # 1b. Fall back to control_value/control_values for single-dependency-style calls
    # (kept for resilience in case CloudBolt ever invokes this differently).
    if not selected_version or not region:
        candidates = []
        if control_value is not None:
            candidates.append(control_value)
        if control_values:
            candidates.extend(control_values)

        for val in candidates:
            if isinstance(val, (list, tuple)) and len(val) > 0:
                val = val[0]
            if not val:
                continue
            val_str = str(val).strip()

            if not selected_version:
                ver = try_extract_version(val_str)
                if ver:
                    selected_version = val_str

            if "@" in val_str and not rh_id and not region:
                parts = val_str.split("@")
                left, right = parts[0].strip(), parts[-1].strip()
                if "(" in right and ")" in right:
                    right = right.split(")")[-2].split("(")[-1]
                if left.isdigit():
                    rh_id = left
                    region = right if not right.isdigit() else region
                elif right.isdigit():
                    rh_id = right
                    region = left if not left.isdigit() else region

    # 2. Inspect live HTTP request GET parameters
    if (not rh_id or not region or not selected_version) and req and hasattr(req, 'GET'):
        for key, raw_val in req.GET.items():
            if not raw_val or raw_val == "Not Selected Any":
                continue

            if 'aws_resource_handler' in key and not rh_id:
                rh_id = raw_val

            elif 'aws_ha_region' in key:
                if "@" in raw_val:
                    parts = raw_val.split("@")
                    if not rh_id:
                        rh_id = parts[0]
                    if not region:
                        region = parts[-1]
                elif not region:
                    region = raw_val

            elif 'aws_ha_zone_region_pair' in key and not region:
                if "(" in raw_val and ")" in raw_val:
                    region = raw_val.split(")")[0].split("(")[-1]
                elif "@" in raw_val:
                    region = raw_val.split("@")[0].strip()

            elif 'aws_ha_cb_version' in key and not selected_version:
                selected_version = raw_val

    # 3. Fallbacks from blueprint context
    if not rh_id:
        rh_id = cf_dict.get('global_ha_architecture_rh_id') or cf_dict.get('aws_rh_id')
    if not rh_id:
        first_rh = AWSHandler.objects.first()
        if first_rh:
            rh_id = first_rh.id

    if not region:
        region = cf_dict.get('aws_region_ha') or "us-east-1"
    if not selected_version:
        selected_version = cf_dict.get('aws_ha_cb_version')

    # 4. Determine allowed instance types via AMI metadata.
    # NOTE: versions are not a fixed, known set (new CloudBolt versions ship over time),
    # so classification cannot be hardcoded by version number. Every version must be
    # resolved against the actual AMI's Marketplace metadata.
    ver_num = try_extract_version(selected_version) if selected_version else None

    is_marketplace = None  # None = could not be determined
    allowed_families = list(nitro_enterprise_types)

    if rh_id and region and ver_num:
        try:
            rh = AWSHandler.objects.get(id=int(rh_id))
            client = get_boto3_ec2_client(resource_handler=rh, region=region)

            ami_resp = client.describe_images(
                Filters=[
                    {'Name': 'state', 'Values': ['available']},
                    {'Name': 'name', 'Values': [f'*{ver_num}*']}
                ]
            )
            images = ami_resp.get('Images', [])
            if images:
                img = sorted(images, key=lambda x: x.get('CreationDate', ''), reverse=True)[0]

                owner_alias = str(img.get('ImageOwnerAlias', '')).lower()
                image_loc = str(img.get('ImageLocation', '')).lower()
                owner_id = str(img.get('OwnerId', ''))
                product_codes = img.get('ProductCodes', [])

                is_marketplace = (
                    bool(product_codes) or
                    owner_alias == 'aws-marketplace' or
                    'marketplace' in image_loc or
                    owner_id == '679593333241'
                )
        except Exception:
            logger.exception(
                "generate_options_for_aws_ha_instance_type failed resolving rh_id=%r "
                "region=%r selected_version=%r; falling back to nitro-only types",
                rh_id, region, selected_version
            )
            is_marketplace = None

    if is_marketplace is False:
        allowed_families = burstable_types + allowed_families
    elif is_marketplace is None:
        set_progress(
            f"instance_type: could not classify marketplace status for rh_id={rh_id!r} "
            f"region={region!r} selected_version={selected_version!r} ver_num={ver_num!r} "
            f"- defaulting to nitro-only (safe) options"
        )

    for item in allowed_families:
        options.append((item, f"{item} ({region})"))

    if len(options) == 1:
        for item in nitro_enterprise_types:
            options.append((item, f"{item} ({region})"))

    set_progress(f"instance_type options: rh_id={rh_id} region={region} selected_version={selected_version!r} ver_num={ver_num!r} is_marketplace={is_marketplace} allowed_families={allowed_families}")

    return options


def prodcut_license_file_validation(blueprint_context):
    is_prodcut_license_file_valid = True
    bpsi_key_list = [key for key in blueprint_context.keys() if "product_license" in key]
    if bpsi_key_list:
        bpsi_context = blueprint_context.get(bpsi_key_list[0])
        pl_file_object = bpsi_context.get("product_license_file")
        name, extension = os.path.splitext(pl_file_object.file.name)
        if extension not in [".bin"]:
            is_prodcut_license_file_valid = False
    return is_prodcut_license_file_valid


def run(job, *args, **kwargs):
    resource = kwargs.pop('resources').first()
    user = resource.owner
    #is_prodcut_license_file_valid = prodcut_license_file_validation(blueprint_context = kwargs.get("blueprint_context"))
    if not (prodcut_license_file_validation(blueprint_context=kwargs.get("blueprint_context", {}))):
        return "FAILURE", "Kindly select valid product license file with '.bin' extension..", "Invalid Product License File"
    if not (user.is_cbadmin or user.is_super_admin):
        return "FAILURE", "Kindly login with superuser or cbadmin user privilage..", "Unauthorized User"
    
    get_or_create_custom_fields()
    
    base_name = '{{base_name}}'
    resource_handler_id = '{{aws_resource_handler}}'
    aws_ha_region = "{{aws_ha_region}}".split('@')[-1]
    aws_zone_region = {{aws_ha_zone_region_pair}}
    existing_vpcs = "{{aws_ha_existing_vpc}}"
    cb_version = "{{aws_ha_cb_version}}"
    instance_type = "{{aws_ha_instance_type}}"

    if len(aws_zone_region) == 1:
        return "FAILURE", "Kindly select at least TWO ZONES to deploy HA Architecture..", "Insufficient Zones"

    instance_locations = ", ".join([i.split('@')[0] for i in aws_zone_region])
    aws_zone_region_tuple = ("Selected AWS Zones-region pairs for HA deployment", instance_locations)
    existing_vpcs_tuple = ("Selected list of Existing VPC in given regions", existing_vpcs)
    
    rh = AWSHandler.objects.get(id=int(resource_handler_id))
    wrapper = rh.get_api_wrapper()
    display_region = [region["display"] for region in wrapper.get_all_regions() if region["name"] == aws_ha_region][0]
    zone_list = [zone.split(" (")[0].replace(" ", "") for zone in instance_locations.split(",")]

    resource.instance_locations = f'{", ".join(zone_list[:-1])} and {zone_list[-1]} in "{display_region}"'
    resource.base_name = base_name
    resource.aws_rh_name_ha = rh.name
    resource.aws_rh_id = rh.id
    resource.aws_zone_region_list_ha = aws_zone_region_tuple
    resource.vpc_selection = existing_vpcs_tuple
    resource.aws_region_ha = aws_ha_region
    
    # Store parameters directly onto the parent resource custom fields
    resource.set_value_for_custom_field('aws_ha_cb_version', cb_version)
    resource.set_value_for_custom_field('aws_ha_instance_type', instance_type)
    resource.save()

    return "SUCCESS", "Deployment locations and parameters captured successfully", ""