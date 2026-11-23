"""Bake sort positions for visible rows and their recorded input ports."""
from semantic_catalog import SemanticCatalog


class Schemas:
    def __init__(self,cat,program):
        tables=program['recipe']['tables']
        self.rows=[tuple(s['kind']=='eq' for s in t['schema']) for t in tables]
        self.inputs={}
        for template,roles in cat.inputs.items():
            kind,idx=template
            if kind=='generated':
                schemas=[self.rows[table] for table,_ in cat.atoms[idx]]
            elif kind=='repair':
                schemas=[(self.rows[idx][-1],)]*len(roles)
            else:
                continue
            for role,schema in zip(roles,schemas,strict=True):
                self.inputs[cat.roots[template],role]=schema

    @staticmethod
    def scalar_content(values,schema):
        return tuple(None if opaque else h for h,opaque in zip(values,schema,strict=True))


class TypedContentCatalog(SemanticCatalog):
    def __init__(self,program):
        super().__init__(program)
        self.content_schema=Schemas(self,program)
