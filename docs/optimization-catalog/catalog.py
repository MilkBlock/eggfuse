#!/usr/bin/env python3
"""Render the optimization index or read its counters; never run a benchmark."""
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def load(path):
    return json.loads(Path(path).read_text())


def metric_id(metric):
    return f"{metric['source']}:{metric['pointer']} [{metric['reduce']}]"


def render(catalog, category):
    rows = [f"# {category['id']} · {category['title']}", "",
            "[返回总目录](README.md)。本页从 [catalog.json](catalog.json) 生成。", "",
            "指标路径以 `report:` 或 `program:` 开头；`*` 表示逐规则/逐 Run 展开。",
            "同一指标可能被多个优化使用，不能跨条目累加成总收益。", ""]
    for opt in catalog['optimizations']:
        if opt['category'] != category['id']:
            continue
        rows += [f"## {opt['id']} · {opt['title']}", "",
                 f"启用条件：{opt['activation']}。", "",
                 f"编译期依据：{opt['compile_fact']}。", "",
                 f"替代的旧工作：{opt['replaces']}。", "",
                 f"运行时仍须满足：{opt['live_obligations']}", "",
                 "代码：" + " · ".join(f"[{Path(p).name}](../../{p})" for p in opt['sources']), "",
                 "| 指标用途 | 精确数据路径 |", "|---|---|"]
        for kind, label in [('benefit', '收益观察（需基线差值）'), ('cost', '成本 / 剩余工作'), ('coverage', '覆盖 / 规模 / 回退')]:
            rows.append(f"| {label} | " + "<br>".join(f"`{metric_id(m)}`" for m in opt['metrics'][kind]) + " |")
        rows += ["", f"解释与缺口：{opt['gaps']}", "", f"状态：{opt['status']}。", ""]
        if opt['evidence']:
            rows += ["证据：" + " · ".join(f"[{p}](../../{p})" for p in opt['evidence']), ""]
    return '\n'.join(rows)


class Missing(Exception):
    pass


def walk(value, parts):
    if not parts:
        return [value]
    head, *tail = parts
    if isinstance(value, dict) and value.get('enabled') is False and head != 'enabled':
        raise Missing('disabled')
    if head == '*':
        if not isinstance(value, (list, dict)):
            raise Missing('missing_counter')
        items = value.values() if isinstance(value, dict) else value
        return [result for item in items for result in walk(item, tail)]
    key = head.replace('~1', '/').replace('~0', '~')
    if isinstance(value, dict) and key in value:
        return walk(value[key], tail)
    if isinstance(value, list) and key.isdigit() and int(key) < len(value):
        return walk(value[int(key)], tail)
    if isinstance(value, dict) and value.get('enabled') is False:
        raise Missing('disabled')
    raise Missing('missing_counter')


def read_metric(metric, sources):
    source = sources.get(metric['source'])
    if source is None:
        return {'status': 'missing_source'}
    try:
        values = walk(source, metric['pointer'].split('/')[1:])
    except Missing as error:
        return {'status': str(error)}
    reduction = metric['reduce']
    if reduction == 'value':
        if len(values) != 1 or values[0] is None:
            return {'status': 'missing_counter'}
        value = values[0]
    elif reduction == 'count':
        if not all(isinstance(v, (dict, list)) for v in values):
            return {'status': 'wrong_type'}
        value = sum(map(len, values))
    else:
        if not all(isinstance(v, (float, int)) and not isinstance(v, bool) for v in values):
            return {'status': 'wrong_type'}
        value = sum(values)
    return {'status': 'observed', 'value': value}


def check(catalog):
    assert catalog['schema'] == 'eggfuse-optimization-catalog/v1'
    categories = {c['id'] for c in catalog['categories']}
    ids = [o['id'] for o in catalog['optimizations']]
    assert len(ids) == len(set(ids)), 'duplicate optimization ID'
    for opt in catalog['optimizations']:
        assert opt['category'] in categories
        for file in opt['sources'] + opt['evidence']:
            assert (ROOT / file).is_file(), f"missing source/evidence: {file}"
        for metrics in opt['metrics'].values():
            for metric in metrics:
                assert metric['source'] in ('report', 'program')
                assert metric['pointer'].startswith('/')
                assert metric['reduce'] in ('value', 'count', 'sum')
    for category in catalog['categories']:
        path = HERE / category['file']
        assert path.read_text() == render(catalog, category), f"stale generated page: {path}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['render', 'check', 'extract'])
    parser.add_argument('--report', type=Path)
    parser.add_argument('--program', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    catalog = load(HERE / 'catalog.json')
    if args.command == 'render':
        for category in catalog['categories']:
            (HERE / category['file']).write_text(render(catalog, category))
        return
    check(catalog)
    if args.command == 'check':
        print(f"checked {len(catalog['categories'])} categories, {len(catalog['optimizations'])} optimizations")
        return
    if not args.report:
        parser.error('extract requires --report; it does not execute a workload')
    paths = {'report': args.report, 'program': args.program}
    sources = {key: load(path) for key, path in paths.items() if path is not None}
    if 'program' in sources and sources['report'].get('program_sha256') != sources['program'].get('sha256'):
        parser.error('report/program digest mismatch')
    metrics = {metric_id(m): m for m in catalog['common_metrics']}
    for opt in catalog['optimizations']:
        metrics.update({metric_id(m): m for group in opt['metrics'].values() for m in group})
    result = {
        'schema': 'eggfuse-optimization-metrics/v1',
        'scope': catalog['scope'],
        'interpretation': 'one execution; no speedup claim; missing/disabled is not zero',
        'sources': {key: {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                    for key, path in paths.items() if path is not None},
        'metrics': {key: read_metric(metric, sources) for key, metric in sorted(metrics.items())},
        'optimizations': {o['id']: {kind: [metric_id(m) for m in group]
                                  for kind, group in o['metrics'].items()} for o in catalog['optimizations']},
    }
    text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end='')


if __name__ == '__main__':
    main()
