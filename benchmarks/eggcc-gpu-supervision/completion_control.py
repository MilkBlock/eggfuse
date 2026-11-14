"""A completion label belongs to one explicit source control contract.

Structural equality is conservative: this does not prove arbitrary schedules
interchangeable. Legacy artifacts only established single-ruleset saturation.
"""
from device_schedule import compile_schedule


def stages_for(recipe):
    return list(dict.fromkeys(r['metadata']['source_set'] for r in recipe['rules']))


def default_control(stages):
    if len(stages)!=1:raise ValueError('missing multistage completion control')
    return dict(saturate=dict(run=stages[0]))


def capture_control(meta):
    recipe=meta.get('original_recipe')
    if recipe is None:recipe=dict(rules=meta['recipe']['rules'][:len(meta['source_rules'])])
    stages=stages_for(recipe);control=meta.get('source_control')
    if control is None:control=default_control(stages)
    compile_schedule(control,stages)
    return control


def require_head_control(report,control,stages):
    expected=report.get('completion_control')
    if expected is None:expected=default_control(stages)
    compile_schedule(expected,stages)
    if expected!=control:raise ValueError('head completion control mismatch')
