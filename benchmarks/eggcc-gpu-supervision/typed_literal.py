"""Exact compiler i64 literals; never round semantic values to f32."""
def value(arg):
    sort=arg.get('sort',{})
    if set(arg)!={'literal','sort'} or sort.get('kind')!='i64' or sort.get('name')!='i64':raise ValueError('unsupported literal sort')
    number=arg['literal']
    if type(number)is not int or not -(1<<63)<=number<(1<<63):raise ValueError('invalid i64 literal')
    return dict(sort='i64',value=number)
