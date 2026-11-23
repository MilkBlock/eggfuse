"""Limit port encoding to the union of the bounded Actor's possible typed reads."""
from dataclasses import replace


class AddressablePorts:
    def __init__(self, catalog):
        self.tables = {rid:tuple(table for table,_ in atoms) for rid,atoms in catalog.atoms.items()}
        self.seminaive = catalog.seminaive
        self.full = 0
        self.encoded = 0

    def project(self, snapshot):
        latest = {}
        for port in snapshot.ports:
            latest[port.table] = max(latest.get(port.table,-1),port.version)
        cutoffs = {}
        for rid, watermark in snapshot.rules.items():
            tables = self.tables[rid]
            if not self.seminaive[rid]:
                for table in tables:
                    cutoffs[table] = 0
                continue
            for pivot, table in enumerate(tables):
                if latest.get(table,-1) < watermark:
                    continue
                cutoffs[table] = min(cutoffs.get(table,watermark),watermark)
                # One live delta pivot can consult other roles in the sealed
                # snapshot, including old ports. Leave their full typed domains.
                for role, other in enumerate(tables):
                    if role != pivot:
                        cutoffs[other] = 0
        ports = [p for p in snapshot.ports if p.table in cutoffs and p.version>=cutoffs[p.table]]
        self.full += len(snapshot.ports)
        self.encoded += len(ports)
        return replace(snapshot,ports=ports)
