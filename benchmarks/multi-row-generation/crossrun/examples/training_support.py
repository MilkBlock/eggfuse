"""Offline experiment assets and set alignment. Imported only by train.py."""
import hashlib
import importlib.util
from pathlib import Path

import numpy as np


ASSETS = Path(__file__).resolve().parents[2]
DATA_COLUMNS = ('a', 'b', 'requests', 'target1', 'target2')


def load_asset(path):
    if not path.is_file():
        raise FileNotFoundError(f'Missing experiment asset: {path}')
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_training_set(assets, npz_path):
    if npz_path is None:
        source = load_asset(assets / 'crossrun/data/crossrun_data.py')
        return source.dataset('train')
    with np.load(npz_path, allow_pickle=False) as archive:
        return {name: archive[name] for name in DATA_COLUMNS}


def training_digest(training):
    digest = hashlib.sha256()
    for name in DATA_COLUMNS:
        digest.update(training[name].tobytes())
    return digest.hexdigest()


def assign_outputs(predictions, targets, solve):
    """Assign unordered target records to slots by their activation and two parent IDs."""
    active = targets[..., 0]
    slots = targets.shape[1]
    costs = np.zeros((len(targets), slots, slots))
    for column, score in enumerate(predictions):
        logits = np.asarray(score)
        maximum = logits.max(axis=-1, keepdims=True)
        log_partition = maximum + np.log(np.exp(logits - maximum).sum(axis=-1, keepdims=True))
        costs_for_class = log_partition - logits
        labels = targets[:, None, :, column, None]
        selected = np.take_along_axis(costs_for_class[:, :, None, :], labels, axis=-1)[..., 0]
        costs += selected if column == 0 else selected * active[:, None, :]
    return solve(costs)


def align_training_targets(make_scores, finish_scores, requests, pair_targets, result_targets, solve):
    batch = np.arange(len(pair_targets))[:, None]
    pair_assignment = assign_outputs(make_scores, pair_targets, solve)
    pairs = pair_targets[batch, pair_assignment]

    # Source labels identify a result's parents by (A id, B id). Resolve these
    # identities to physical Pair and Request slots for pointer supervision.
    # The model has already produced its own token before this function runs.
    results = result_targets.copy()
    source_ids = results[:, :, None, 1:3]
    pair_match = (source_ids == pairs[:, None, :, 1:3]).all(axis=-1) & (pairs[:, None, :, 0] != 0)
    request_match = (source_ids == requests[:, None, :, :2]).all(axis=-1)
    live = results[..., 0] != 0
    if not np.all(pair_match.sum(axis=-1)[live] == 1) or not np.all(request_match.sum(axis=-1)[live] == 1):
        raise ValueError('An active Result label requires one source Pair and one Request')
    results[..., 1] = pair_match.argmax(axis=-1)
    results[..., 2] = request_match.argmax(axis=-1)
    result_assignment = assign_outputs(finish_scores, results, solve)
    return pairs, results[batch, result_assignment]
