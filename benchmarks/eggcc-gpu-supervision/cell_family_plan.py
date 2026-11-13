"""Project an explicit original control subtree for a bounded Cell-family audit."""
from device_snapshot_import import identity


def project_control(node,stages):
    if isinstance(node,list):
        children=[p for c in node if (p:=project_control(c,stages)) is not None]
        return children or None
    if not isinstance(node,dict):raise ValueError('invalid source control')
    if set(node)=={'run'}:return dict(node) if node['run'] in stages else None
    if set(node)=={'sequence'}:
        body=project_control(node['sequence'],stages)
        return dict(sequence=body) if body else None
    if set(node)=={'saturate'}:
        body=project_control(node['saturate'],stages)
        return dict(saturate=body) if body else None
    if set(node)=={'repeat','body'}:
        body=project_control(node['body'],stages)
        return dict(repeat=node['repeat'],body=body) if body else None
    raise ValueError('unsupported source control')


def family(recipe,config):
    rules=config['rules'];stages=config['stages']
    if not rules or len(set(rules))!=len(rules) or len(set(stages))!=len(stages):raise ValueError('duplicate/empty family')
    if any(recipe['rules'][r]['metadata']['source_set'] not in stages for r in rules):raise ValueError('rule stage mismatch')
    node=recipe['control']
    for part in config['control_path']:node=node[part]
    control=project_control(node,set(stages))
    if control is None:raise ValueError('empty projected schedule')
    return rules,stages,control


def withhold(snapshot,recipe,config):
    """Choose withheld facts from existing typed snapshot fields, never outputs."""
    removed=set(config.get('remove_tables',[]));selectors=[]
    tables={t['name']:t for t in recipe['tables']}
    for selector in config.get('remove_rows',[]):
        source=selector['from_table'];target=selector['table'];column=selector['column']
        schema=tables[target]['schema'][column]
        for field in selector['from_columns']:
            if tables[source]['schema'][field]!=schema:raise ValueError('withhold sort mismatch')
        keys={identity(row['values'][field]) for row in snapshot['rows'] if row['table']==source and not row['subsumed'] for field in selector['from_columns']}
        selectors.append((target,column,keys))
    rows=[row for row in snapshot['rows'] if row['table'] not in removed and not any(row['table']==table and identity(row['values'][col]) in keys for table,col,keys in selectors)]
    return dict(snapshot,rows=rows),len(snapshot['rows'])-len(rows)
