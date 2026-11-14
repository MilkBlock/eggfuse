"""Exact compiler i64 literals; never round semantic values to f32."""
def value(arg):
    sort=arg.get('sort',{})
    if set(arg)!={'literal','sort'} or not isinstance(sort,dict) or sort.get('kind')!='i64' or sort.get('name')!='i64':raise ValueError('unsupported literal sort')
    number=arg['literal']
    if type(number)is not int or not -(1<<63)<=number<(1<<63):raise ValueError('invalid i64 literal')
    return dict(sort='i64',value=number)


def resolved(arg,slots,reference):
    """Read an already executed operand without allocating oracle identities."""
    if set(arg)=={'slot'}:return reference.root(slots[arg['slot']])
    from device_snapshot_import import identity
    literal=value(arg);key=identity(literal)
    if key not in reference.scalar_ids:raise ValueError('literal absent from completed reference')
    return reference.scalar_ids[key]


def compiled_id(arg,recipe):
    """Resolve a constant in the caller's reserved exact identity namespace."""
    from device_snapshot_import import identity
    literal=value(arg);key=identity(literal)
    result=recipe.get('literal_ids',{}).get(key)
    if type(result) is not int or not 0<=result<(1<<31):raise ValueError('unbound literal identity')
    return result
