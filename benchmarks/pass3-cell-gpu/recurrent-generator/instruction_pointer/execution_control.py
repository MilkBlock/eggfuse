"""Logical controls over the open CCP v0.1 occurrence. No native schedule override."""

from time import perf_counter

import torch

from discrete_editor import features

CONTINUE, SUBMIT, SEAL = range(3)


def legal(balance, draft, mode):
    # Only syntactic legality / hard budgets. Seal closes a drained draft.
    return (balance > 0, draft > 0, not draft and mode != "B")


def representation(memory, pages, balance, draft, submitted, last_reply):
    x = features(memory.context(), memory.event, [], 0)[0]
    x[-6:] = torch.tensor(
        [
            pages / 6,
            balance / 6,
            draft / 96,
            submitted / 96,
            sum(s == 0 for s in last_reply) / max(1, len(last_reply)),
            float(bool(last_reply)),
        ]
    )
    return x


def window(memory, balance, mode, choose, generate, submit, deadline, capture=False):
    """A finite draft. A native response acknowledges selected requests only."""
    draft, rows, last = [], [], []
    pages = sent = 0
    while True:
        if perf_counter() >= deadline:
            raise TimeoutError
        mask = legal(balance, len(draft), mode)
        if not balance and not draft:
            return rows, balance, "budget_truncation"
        x = representation(memory, pages, balance, len(draft), sent, last)
        action = choose(x, mask)
        if action not in (CONTINUE, SUBMIT, SEAL) or not mask[action]:
            raise ValueError("control outside the current syntax or resource budget")
        row = {"action": action, "pages": pages, "draft": len(draft), "sent": sent}
        if capture:
            row.update(x=x.tolist(), mask=mask)
        rows.append(row)
        if action == SEAL:
            return rows, balance, "neural_seal"
        if capture:
            started = perf_counter()
        if action == CONTINUE:
            cells = generate()
            if capture:
                row["generation_seconds"] = perf_counter() - started
            draft.extend(cells)
            if capture:
                from discovery_sampling import encode

                row["tokens"] = [encode(c) for c in cells]
            row["generated"] = len(cells)
            pages += 1
            balance -= 1
        else:
            response = submit(draft)
            if capture:
                row["submit_seconds"] = perf_counter() - started
            if len(response) != len(draft):
                raise ValueError("incomplete admission response")
            last = [int(r[1]) for r in response]
            row["ids"] = [int(r[0]) for r in response]
            row["status"] = last
            sent += len(draft)
            draft = []


def pick(net, x, mask):
    scores = net(x.to(next(net.parameters()).device)).detach()
    return int(
        scores.masked_fill(
            ~torch.tensor(mask, device=scores.device), float("-inf")
        ).argmax()
    )
