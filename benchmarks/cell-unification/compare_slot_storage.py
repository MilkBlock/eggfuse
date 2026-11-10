#!/usr/bin/env python3
"""Compare unique published result storage plus all compiled inheritance layouts.

Run after run_slot_inheritance.py. The reference is the same selected program
executed with frame88-reference.patch applied in an isolated source checkout.
These are capacity bytes plus estimated Rc headers, not peak RSS/allocator bytes.
"""
import argparse
import json
from pathlib import Path
from check_links import load, sha
from check_alias_routes import same_execution


def storage(directory):
    report = load(directory / 'report.json')['stage_spine']
    census = report['published_history_storage']
    published = sum(v for k, v in census.items() if k.endswith('_bytes'))
    owners = census['owners'] + census['layouts']
    header = census['rc_header_bytes'] // owners if owners else 0
    assert not owners or header * owners == census['rc_header_bytes']
    # Replace the referenced-layout subset with all compiled layouts, never
    # charging their payload or Rc headers twice.
    combined = (published - census['layout_bytes'] - census['layouts'] * header
                + report['compiled_history_layout_bytes'])
    return dict(frame_bytes=report['history_result_frame_bytes'],
                published=census, published_bytes=published,
                compiled_layouts=report['compiled_history_layouts'],
                compiled_layout_bytes=report['compiled_history_layout_bytes'],
                combined_bytes=combined, report_sha256=sha(directory/'report.json'))


def compare(root, reference):
    execution = same_execution([reference, root/'run-candidate'],
                               [root/'program.json', root/'program.json'])
    samples = {name: storage(path) for name, path in (
        ('frame88_reference', reference), ('materialized', root/'run-materialized'),
        ('candidate', root/'run-candidate'))}
    before, after = (samples[k]['combined_bytes'] for k in ('frame88_reference','candidate'))
    control = samples['materialized']['combined_bytes']
    return dict(scope='standalone Cell CPU, final published history owners and all compiled slot layouts; no timing',
                execution=execution, samples=samples,
                bytes_saved=before-after, fractional_reduction=1-after/before,
                inheritance_over_materialized_bytes=after-control,
                inheritance_over_materialized_fraction=after/control-1,
                limitations='Excludes allocator rounding, peak/transient or unpublished cursor storage, program JSON and unrelated graph data. Rc headers are estimated. Whole-process compression is not established.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('root', 'reference', 'output'):
        parser.add_argument('--'+key, required=True, type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(compare(args.root, args.reference), indent=2)+'\n')
