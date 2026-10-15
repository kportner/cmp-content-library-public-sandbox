def get_options_list(field, **kwargs):
    """
    A working sample that returns a dynamically generated list of options.

    :param field: The field you are generating options for (of type CustomField or its subclass HookInput).

    See the "Generated Parameter Options" section of the docs for more info and the CloudBolt forge
    for more examples: https://github.com/CloudBoltSoftware/cloudbolt-forge/tree/master/actions/cloudbolt_plugins
    """

    # In the simple cases where the label shown to users is the same as the value to be saved,
    # return a simple list of values
    # return [1, 10, 42, 100]
    # UPDATE

    # Otherwise, define the database values and labels as a list of 2-tuples.
    options = [
        (1, 'BP One'),
        (2, 'BP Two'),
        (3, 'BP Three'),
    ]

    return {
        'options': options,
        'initial_value': 2,
        'sort': True,
        'override': False,
    }