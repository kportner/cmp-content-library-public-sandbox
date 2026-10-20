import re
import uuid
from common.methods import (
    get_options_for_action_input_field,
    get_or_create_update_order_item,
    validate_disk_constraints,
)
from infrastructure.models import CustomField
from infrastructure.helper_functions import raise_error_if_not_permitted
from utilities.logger import ThreadLogger

logger = ThreadLogger(__name__)


def generate_options_for_ebs_volume_type(
    server=None, servers=None, profile=None, **kwargs
):
    """
    Generate the options for the ``ebs_volume_type`` action-input field.

    Returns ``{"hidden": True}`` when there is no single server context (e.g.
    bulk actions), otherwise the options configured on the ``ebs_volume_type``
    custom field.
    """
    if not server:
        return {"hidden": True}

    custom_field = CustomField.objects.get(name="ebs_volume_type")
    choices = get_options_for_action_input_field(custom_field)

    return choices


def validate_inputs(
    server, new_disk_size, ebs_volume_type, iops, encrypted, encryption_key_arn
):
    """
    Validate the inputs for adding an EBS volume and return a list of error
    messages (empty if all inputs are valid).

    Checks that disk size and volume type are supplied, enforces the IOPS and
    minimum-size rules for the various EBS volume types (io1/gp2/st1/sc1), and,
    when encryption is requested, validates that the KMS key ARN matches the
    server's region and is well-formed (including a valid key UUID). Also flags a
    key ARN supplied without encryption enabled.

    Args:
        server (Server): The server the disk is being added to.
        new_disk_size (int): Requested disk size in GiB.
        ebs_volume_type (str): The EBS volume type (e.g. io1, gp2, st1, sc1).
        iops (int): Provisioned IOPS (only valid for io1 volumes).
        encrypted (bool): Whether volume encryption is enabled.
        encryption_key_arn (str): The KMS key ARN to use when encrypted.

    Returns:
        List[str]: Validation error messages; empty when inputs are valid.
    """
    validation_errors = []
    if not new_disk_size:
        validation_errors.append("Disk Size is a required field")
    if not ebs_volume_type:
        validation_errors.append("EBS Volume Type is a required field")
    if ebs_volume_type == "io1":
        if not iops:
            validation_errors.append(
                "You must specify a number of IOPS for 'io1' volumes."
            )
        elif iops < 100:
            validation_errors.append("The volume IOPS is too low. The minimum is 100.")
    else:
        if iops:
            validation_errors.append(
                f"The parameter IOPS is not supported for '{ebs_volume_type}' volumes"
            )

    if ebs_volume_type == "gp2":
        if new_disk_size < 4:
            validation_errors.append(
                "The minimum disk size for 'gp2' volumes is 4 GiB."
            )

    if ebs_volume_type in ["st1", "sc1"]:
        if new_disk_size < 500:
            validation_errors.append(
                f"The minimum disk size for '{ebs_volume_type}' volumes is 500 GiB."
            )

    if encrypted and encryption_key_arn:
        arn_region = encryption_key_arn.split(":")[3]
        if arn_region != server.ec2serverinfo.ec2_region:
            validation_errors.append(
                "The AWS Encryption KMS Key ARN region does not match the server region."
            )
        # validate the KMS Key ARN is in the following format
        #     single region key: arn:aws:kms:regionname:123456789012:key/someuuid
        #      multi-region key: arn:aws:kms:regionname:123456789012:key/mrk-someuuidwithoutdashes
        pattern = re.compile(
            "arn:aws:kms:{region}:[0-9]+:key/(mrk-)?(.+)".format(region=arn_region)
        )
        match_obj = pattern.match(encryption_key_arn)
        if not match_obj:
            validation_errors.append(
                "The AWS Encryption KMS Key ARN format is not valid."
            )
        else:
            try:
                # UUID with or without the dashes will validate
                uuid.UUID(match_obj[2], version=4)
            except ValueError:
                validation_errors.append(
                    "The AWS Volume Encryption KMS Key ARN format is valid but the UUID did not validate."
                )
    elif not encrypted and encryption_key_arn:
        validation_errors.append(
            "The AWS Volume Encryption KMS Key ARN was supplied but encryption was not enabled."
        )

    return validation_errors


def run(
    server=None, owner=None, servers=None, profile=None, position=None, *args, **kwargs
):
    """
    Add an EBS volume to a server by staging the change on the user's current
    order.

    Validates the requested disk inputs and disk constraints, then adds (or
    updates) an order item on the profile's current order describing the new
    disk. This plug-in operates on a single server only and does not support
    bulk actions.

    Args:
        server (Server): The server to add the disk to (required).
        owner: The order owner (unused here; accepted from the action context).
        servers (list, optional): Present for bulk contexts; rejected if it
            contains more than one server.
        profile (UserProfile): The acting user's profile (required for
            permission checks and to locate the current order).
        position (int, optional): Disk position; defaults to the server's
            current disk count.

    Returns:
        tuple: ``(status, output_message, error_message)`` where status is
        "SUCCESS" or "FAILURE".

    Raises:
        PermissionError: If no profile is provided.
    """
    if not profile:
        raise PermissionError(
            "Could not find user profile, which is required to add disk"
        )

    if servers and len(servers) > 1:
        return (
            "FAILURE",
            "",
            "Currently this action does not support for bulk action",
        )

    if server is None:
        return (
            "FAILURE",
            "",
            "This plugin only runs against a Server, no Server object given",
        )

    raise_error_if_not_permitted(profile, "server.add_disks", [server])

    new_disk_size = kwargs.get("new_disk_size") and int(kwargs["new_disk_size"])
    ebs_volume_type = kwargs.get("ebs_volume_type")
    iops = kwargs.get("iops") and int(kwargs["iops"])
    aws_volume_encryption = kwargs.get("aws_volume_encryption")
    aws_volume_encryption_key_arn = kwargs.get("aws_volume_encryption_key_arn")

    validation_errors = validate_inputs(
        server,
        new_disk_size,
        ebs_volume_type,
        iops,
        aws_volume_encryption,
        aws_volume_encryption_key_arn,
    )

    if not position:
        position = server.disks.count()

    validation_errors = validate_disk_constraints(
        server, position, new_disk_size, validation_errors=validation_errors
    )
    if validation_errors:
        msg = " ".join(validation_errors)
        logger.error(f"Validation Error on inputs: {msg}")
        return (
            "FAILURE",
            msg,
            (f"Selections not valid: {msg}"),
        )

    # Check if an order is already present in current_order. If present,
    # indicate an error message to either clear or submit the current order.
    order = profile.get_current_order()
    errors = order.check_server_modification(server)
    if errors:
        for error in errors:
            logger.error(error)
            return "FAILURE", error, "Failed"

    new_values = {
        "new_disk_size": new_disk_size,
        "ebs_volume_type": ebs_volume_type,
        "iops": iops,
        "aws_volume_encryption": aws_volume_encryption,
        "aws_volume_encryption_key_arn": aws_volume_encryption_key_arn,
    }
    order = get_or_create_update_order_item(server, order, new_values)
    if not order.group:
        order.group = server.group
        order.save()
    return "SUCCESS", "Your order modification has been added to your current order", ""


# These are here to ensure that when this plug-in code is modified from the
# CB UI, the action inputs and all their attributes are preserved. These are
# defined in cb_minimal.py.
# {{ new_disk_size }}
# {{ ebs_volume_type }}
# {{ iops }}
# {{ aws_volume_encryption }}
