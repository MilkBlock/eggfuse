"""Ephemeral GPU features from the current explicit Cell set.

No predicted latent or source-history token is read. This is an input adapter,
not yet a trained replacement for the recurrent completion model.
"""
from device_slot_owners import shape, live
from neural_device_candidates import seed_inputs


def current_inputs(state, frames, xp):
    n, width = shape(state)
    # Full compiled width: generated Cells may be wider than query seed rows.
    fields, _ = seed_inputs(state, frames, xp, field_width=width)
    rid = state['keys'][:, 0]
    valid_id = (rid >= 0) & (rid < len(frames['roles']))
    eligible = state['present'] & state['visible'] & state['settled']
    readable = valid_id & live(state, xp.arange(n), xp)
    mask = eligible & readable
    # Dirty historical latents are irrelevant here, but invalid explicit state
    # and unsettled visible Cells still block a completeness claim.
    complete = ~xp.any(state['present'] & state['visible'] &
                       (~state['settled'] | ~readable))
    return dict(fields=xp.where(mask[:, None], fields, 0), mask=mask,
                complete=complete)


def current_candidates(state, frames, plan, encoder, external_complete, eq_settled, xp):
    """Use ephemeral current-state embeddings in the existing query route.

    Preserves exact source resolution and ownership/lifetime checks. This first
    adapter still uses the bounded Cartesian route, not scalable context routing.
    """
    from neural_device_candidates import candidates
    if 'owner_token_blocks' in state:
        raise ValueError('block token layouts need an explicit current-state projection')
    inputs = current_inputs(state, frames, xp)
    embeddings = encoder(inputs['fields'])
    if embeddings.shape != (len(state['present']), 128):
        raise ValueError('current-state encoder must return one 128-float row per Cell')
    temporary = dict(state, tokens=embeddings)
    batch = candidates(temporary, frames, plan,
                       external_complete & inputs['complete'], eq_settled, xp)
    return dict(batch, complete=batch['complete'] & inputs['complete'])
