"""Post-generation witness audit, independent of the Torch model and its encoder."""
from collections import Counter, defaultdict
import numpy as np


def stage_totals(expected, legal_counts, exact_counts, activated, wrong_rows):
    missing = len(expected.difference(legal_counts))
    duplicates = sum(n - 1 for n in legal_counts.values())
    illegal = activated - sum(legal_counts.values())
    binding_complete = not (illegal or missing or duplicates)
    return {
        'obligations': len(expected), 'nonempty': bool(expected), 'active_outputs': activated,
        'binding_complete': binding_complete, 'complete': binding_complete and wrong_rows == 0,
        'missing': missing, 'semantic_missing': len(expected.difference(exact_counts)),
        'duplicates': duplicates, 'illegal': illegal, 'wrong_rows': wrong_rows,
    }


def audit_graph(expected1, expected2, first, second, request_count, parent_payload=None):
    """expected1 maps source (left,right) to full row; expected2 maps (left,right,request_slot) to row.

    Different physical producers of the same source binding share identity for
    duplication counts. Semantic exactness checks the actual consumed row and
    its selected ancestry. Both stage records carry integer active, pointers,
    and full ordered `rows`, with shapes [S], [S,2], [S,C].
    """
    if parent_payload is None:
        parent_payload = {key:tuple(row) for key,row in expected1.items()}

    def unpack(frame):
        live = np.asarray(frame['active'])
        pointers, rows = np.asarray(frame['pointers']), np.asarray(frame['rows'])
        if (live.ndim != 1 or pointers.shape != (len(live),2) or rows.ndim != 2
                or len(rows) != len(live) or live.dtype.kind not in 'biu'
                or pointers.dtype.kind not in 'iu' or rows.dtype.kind not in 'iu'
                or not np.isin(live, (0,1)).all()):
            raise ValueError('expected a discrete activation, two pointers and one row per slot')
        for slot in np.flatnonzero(live):
            yield int(slot), tuple(map(int, pointers[slot])), tuple(map(int, rows[slot]))

    bound, exact = Counter(), Counter()
    parent_slots = {}
    wrong_rows = active = 0
    for slot, binding, row in unpack(first):
        active += 1
        if binding in expected1:
            bound[binding] += 1
            correct = row == tuple(expected1[binding])
            parent_slots[slot] = (binding, correct)
            if correct:
                exact[binding] += 1
            else:
                wrong_rows += 1
    report1 = stage_totals(set(expected1), bound, exact, active, wrong_rows)
    required = defaultdict(set)
    ready_obligations = set()
    for witness in expected2:
        left, right, request_slot = witness
        binding = (left, right)
        if binding not in expected1 or not 0<=request_slot<request_count:
            raise ValueError('source consumer witness refers to an undefined producer/request')
        required[request_slot].add(binding)
        if binding in exact:
            ready_obligations.add(witness)

    bound, exact = Counter(), Counter()
    wrong_rows = active = 0
    diagnostics = dict(invalid_request_slot=0, request_has_no_source_match=0,
                       absent_parent_reference=0, illegal_producer_binding=0,
                       wrong_live_parent=0, wrong_live_parent_same_payload=0,
                       wrong_live_parent_with_correct_parent_available=0,
                       corrupt_consumed_parent=0, wrong_result_row=0)
    ready_requests = {r for _,_,r in ready_obligations}
    for _, (parent_slot, request_slot), row in unpack(second):
        active += 1
        if not 0 <= request_slot < request_count:
            diagnostics['invalid_request_slot'] += 1
            continue
        if not required[request_slot]:
            diagnostics['request_has_no_source_match'] += 1
            continue
        if not 0 <= parent_slot < len(first['active']) or not first['active'][parent_slot]:
            diagnostics['absent_parent_reference'] += 1
            continue
        if parent_slot not in parent_slots:
            diagnostics['illegal_producer_binding'] += 1
            continue
        binding, parent_exact = parent_slots[parent_slot]
        witness = (*binding, request_slot)
        if witness not in expected2:
            diagnostics['wrong_live_parent'] += 1
            diagnostics['wrong_live_parent_with_correct_parent_available'] += int(request_slot in ready_requests)
            diagnostics['wrong_live_parent_same_payload'] += int(any(
                parent_payload[binding] == parent_payload[wanted] for wanted in required[request_slot]))
            continue
        bound[witness] += 1
        row_exact = row == tuple(expected2[witness])
        diagnostics['corrupt_consumed_parent'] += int(not parent_exact)
        diagnostics['wrong_result_row'] += int(not row_exact)
        if parent_exact and row_exact:
            exact[witness] += 1
        else:
            wrong_rows += 1
    report2 = stage_totals(set(expected2), bound, exact, active, wrong_rows)
    report2.update(diagnostics)
    report2['unavailable_parent_obligations'] = len(expected2) - len(ready_obligations)
    report2['parent_ready'] = len(expected2) == len(ready_obligations)
    return report1, report2


def totals(records):
    result = {key:sum(int(g[key]) for g in records) for key in records[0]}
    result.update(graphs=len(records), nonempty_graphs=result.pop('nonempty'),
                  complete_graphs=result.pop('complete'), binding_complete_graphs=result.pop('binding_complete'),
                  nonempty_complete_graphs=sum(int(g['complete'] and g['nonempty']) for g in records))
    if 'parent_ready' in result:
        result['parent_ready_nonempty_graphs'] = sum(int(g['parent_ready'] and g['nonempty']) for g in records)
        result['parent_ready_nonempty_complete_graphs'] = sum(int(g['parent_ready'] and g['nonempty'] and g['complete']) for g in records)
        del result['parent_ready']
    result['per_graph'] = records
    return result
