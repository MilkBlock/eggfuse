"""Independent CPU interpretation of the selected family's source schedule."""
def execute(reference,control,budget=128,observe=None):
    records=[]
    def visit(node):
        if isinstance(node,list):
            changed=False
            for child in node:changed=visit(child) or changed
            return changed
        if not isinstance(node,dict):raise ValueError('invalid schedule')
        if set(node)=={'sequence'}:return visit(node['sequence'])
        if set(node)=={'run'}:
            if len(records)>=budget:raise ValueError('reference schedule Run budget exhausted')
            rules=[r for r in reference.recipe['rules'] if r['metadata']['source_set']==node['run']]
            if not rules:raise ValueError('uncovered ruleset')
            before=reference.unions;ctors=reference.constructions;changes,apps=reference.apply(rules)
            row=dict(stage=node['run'],applications=apps,per_rule_applications=reference.last_match_counts,new_equivalences=reference.unions-before)
            if reference.constructions!=ctors:row['new_constructors']=reference.constructions-ctors
            records.append(row)
            if observe:observe(reference,row)
            return bool(changes)
        if set(node)=={'saturate'}:
            changed=False
            while True:
                before=len(records);step=visit(node['saturate']);changed=changed or step
                if not step:return changed
                if len(records)==before:raise ValueError('non-progressing saturation')
        if set(node)=={'repeat','body'}:
            count=node['repeat']
            if type(count)is not int or count<0:raise ValueError('invalid repeat')
            changed=False
            for _ in range(count):changed=visit(node['body']) or changed
            return changed
        raise ValueError('unsupported schedule')
    visit(control);return records
