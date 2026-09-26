"""Structural JSON loading for native graphs, independent of reference pipelines.

This module deliberately does not import pass_definition: its Schema selectors,
material ownership and immutable transaction rules belong to the UE extension.
Only graph syntax and authored file origins are resolved here. Pass-specific
properties and physical ports are validated by the registered Falcor passes.
"""
import copy
import heapq
import json
import math
from os import PathLike
from pathlib import Path
import re


_IDENTIFIER = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
_LEGACY_PROPERTIES = {'schemaPath', 'sceneDefinition', 'pipelinePath', 'pipelineNode',
                      'pipelineRole', 'graphDefinitionPath', 'meshPolicyPath'}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _identifier(value, label):
    _require(isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None,
             f'{label} must be an ASCII identifier')
    return value


def _json_copy(value, label, ancestors=None):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        _require(math.isfinite(value), f'{label} must contain finite numbers')
        return value
    _require(isinstance(value, (dict, list)), f'{label} must contain only JSON values')
    ancestors = set() if ancestors is None else ancestors
    _require(id(value) not in ancestors, f'{label} contains a circular value')
    ancestors.add(id(value))
    try:
        if isinstance(value, list):
            return [_json_copy(item, f'{label}[{i}]', ancestors) for i, item in enumerate(value)]
        _require(all(isinstance(key, str) for key in value), f'{label} requires string keys')
        return {key: _json_copy(item, f'{label}.{key}', ancestors) for key, item in value.items()}
    finally:
        ancestors.remove(id(value))


def _keys(value, required, optional, label):
    _require(isinstance(value, dict), f'{label} must be an object')
    missing = set(required) - value.keys()
    unknown = value.keys() - set(required) - set(optional)
    _require(not missing, f'{label} missing required keys: {", ".join(sorted(missing))}')
    _require(not unknown, f'{label} unknown keys: {", ".join(sorted(unknown))}')
    if 'version' in value:
        _require(type(value['version']) is int and value['version'] == 1, f'{label} version must be 1')
    if 'metadata' in value:
        _require(isinstance(value['metadata'], dict), f'{label} metadata must be an object')


def _read_json(path):
    return _json_copy(json.loads(path.read_text(encoding='utf-8')), str(path))


def _merge(base, override):
    result = copy.deepcopy(base)
    for key, value in override.items():
        result[key] = (_merge(result[key], value) if isinstance(result.get(key), dict)
                       and isinstance(value, dict) else copy.deepcopy(value))
    return result


def _legacy_macros(value, label):
    if isinstance(value, str):
        _require(not value.startswith(('$packed', '$field:')), f'{label} uses legacy Schema macros')
    elif isinstance(value, dict):
        for key, child in value.items():
            _legacy_macros(child, f'{label}.{key}')
    elif isinstance(value, list):
        for i, child in enumerate(value):
            _legacy_macros(child, f'{label}[{i}]')


def _file_entries(entries, label):
    _require(isinstance(entries, list), f'{label} file_inputs must be an array')
    seen = set()
    for entry in entries:
        _require(isinstance(entry, str) and entry, f'{label} file_inputs require nonempty property paths')
        for part in entry.split('.'):
            _identifier(part, f'{label} file_inputs path {entry}')
        _require(entry not in seen, f'{label} duplicate file_inputs entry {entry}')
        seen.add(entry)
    return entries


def _resolve_files(properties, entries, origin, override=None, override_origin=None):
    entries = list(entries)
    if isinstance(properties.get('shader'), dict) and 'file' in properties['shader']:
        if 'shader.file' not in entries:
            entries.append('shader.file')
    for field in entries:
        parts = field.split('.')
        owner, authored_override = properties, override
        for part in parts[:-1]:
            _require(isinstance(owner, dict) and part in owner, f'file_inputs cannot resolve property {field}')
            owner = owner[part]
            authored_override = authored_override.get(part) if isinstance(authored_override, dict) else None
        leaf = parts[-1]
        _require(isinstance(owner, dict) and leaf in owner, f'file_inputs cannot resolve property {field}')
        value = owner[leaf]
        _require(isinstance(value, str) and value.strip(), f'file_inputs property {field} must be a nonempty string path')
        authored_here = isinstance(authored_override, dict) and leaf in authored_override
        directory = override_origin if authored_here else origin
        owner[leaf] = str((directory / value).resolve())


def _load_node(node, index, origin):
    label = f'node {index}'
    _require(isinstance(node, dict), f'{label} must be an object')
    optional = ('properties', 'file_inputs', 'inherit_pipeline', 'metadata')
    if 'description' in node:
        _keys(node, ('name', 'description'), optional, label)
        path = node['description']
        _require(isinstance(path, str) and path.strip(), f'{label} description must be a file path')
        description_path = (origin / path).resolve()
        description = _read_json(description_path)
        _keys(description, ('type',), (*optional, 'version'), f'{label} pass description')
        base = description.get('properties', {})
        override = node.get('properties', {})
        _require(isinstance(base, dict) and isinstance(override, dict), f'{label} properties must be objects')
        properties = _merge(base, override)
        base_files = _file_entries(description.get('file_inputs', []), label)
        node_files = _file_entries(node.get('file_inputs', []), label)
        files = base_files + [entry for entry in node_files if entry not in base_files]
        inherit = node.get('inherit_pipeline', description.get('inherit_pipeline', False))
        # An override cannot hide a reusable description's legacy dependency.
        _require(description.get('inherit_pipeline', False) is False,
                 f'{label} inherit_pipeline must be false; legacy inheritance is not supported')
        kind = description['type']
        file_origin = description_path.parent
    else:
        _keys(node, ('name', 'type'), optional, label)
        properties = node.get('properties', {})
        _require(isinstance(properties, dict), f'{label} properties must be an object')
        files = _file_entries(node.get('file_inputs', []), label)
        inherit = node.get('inherit_pipeline', False)
        kind = node['type']
        file_origin, override = origin, None
    name = _identifier(node['name'], f'{label} name')
    _identifier(kind, f'node {name} type')
    _require(inherit is False, f'node {name} inherit_pipeline must be false; legacy inheritance is not supported')
    forbidden = properties.keys() & _LEGACY_PROPERTIES
    _require(not forbidden, f'node {name} uses legacy transaction properties: {", ".join(sorted(forbidden))}')
    _legacy_macros(properties, f'node {name} properties')
    for resource in properties.get('resources', []) if isinstance(properties.get('resources'), list) else []:
        _require(not isinstance(resource, dict) or not ({'schema', 'schema_expanded'} & resource.keys()),
                 f'node {name} resources use legacy Schema expansion')
    _resolve_files(properties, files, file_origin, override, origin)
    return {'name': name, 'type': kind, 'properties': properties}


def load_graph_definition(definition, *, base_directory=None):
    """Load/validate JSON and return an owned physical declaration, without Falcor.

    Endpoints are ASCII ``Node.port`` identifiers; bare pairs denote execution
    dependencies. Physical port existence/type is intentionally left to Falcor.
    Both graph and pass ``metadata`` objects are descriptive, never pass props.
    Graph version is required; reusable descriptions may omit version for the
    existing type/properties format, but any explicit version must be 1.
    """
    if isinstance(definition, (str, PathLike)):
        path = Path(definition).resolve()
        declaration, origin = _read_json(path), path.parent
    else:
        declaration = _json_copy(definition, 'Native graph')
        origin = Path.cwd() if base_directory is None else Path(base_directory).resolve()
    _keys(declaration, ('version', 'nodes'), ('edges', 'outputs', 'metadata'), 'Native graph')
    raw_nodes = declaration['nodes']
    _require(isinstance(raw_nodes, list) and raw_nodes, 'Native graph nodes must be a nonempty array')
    nodes, indices = [], {}
    for i, raw in enumerate(raw_nodes):
        node = _load_node(raw, i, origin)
        _require(node['name'] not in indices, f'duplicate node name {node["name"]}')
        indices[node['name']] = i
        nodes.append(node)

    def endpoint(value, label):
        _require(isinstance(value, str), f'{label} must be a string endpoint')
        name, separator, port = value.partition('.')
        _identifier(name, f'{label} node')
        _require(name in indices, f'{label} references unknown node {name}')
        if separator:
            _legacy_macros(port, label)
            _identifier(port, f'{label} port')
        return name, bool(separator)

    edges, outputs = declaration.get('edges', []), declaration.get('outputs', [])
    _require(isinstance(edges, list), 'Native graph edges must be an array')
    _require(isinstance(outputs, list), 'Native graph outputs must be an array')
    seen_edges, targets = set(), set()
    successors = {name: set() for name in indices}
    indegree = {name: 0 for name in indices}
    for i, edge in enumerate(edges):
        _require(isinstance(edge, list) and len(edge) == 2, f'edge {i} must contain exactly two endpoints')
        source, source_port = endpoint(edge[0], f'edge {i} source')
        target, target_port = endpoint(edge[1], f'edge {i} destination')
        _require(source != target, f'edge {i} is a self edge on node {source}')
        _require(source_port == target_port, f'edge {i} cannot mix execution and resource endpoints')
        _require(tuple(edge) not in seen_edges, f'duplicate edge {edge[0]} -> {edge[1]}')
        if target_port:
            _require(edge[1] not in targets, f'duplicate destination {edge[1]}')
            targets.add(edge[1])
        seen_edges.add(tuple(edge))
        if target not in successors[source]:
            successors[source].add(target)
            indegree[target] += 1
    seen_outputs = set()
    for i, output in enumerate(outputs):
        _, port = endpoint(output, f'output {i}')
        _require(port, f'output {i} must identify a port')
        _require(output not in seen_outputs, f'duplicate output {output}')
        seen_outputs.add(output)
    ready = [indices[name] for name, count in indegree.items() if count == 0]
    heapq.heapify(ready)
    visited = 0
    while ready:
        name = nodes[heapq.heappop(ready)]['name']
        visited += 1
        for target in successors[name]:
            indegree[target] -= 1
            if indegree[target] == 0:
                heapq.heappush(ready, indices[target])
    _require(visited == len(nodes), 'Native graph contains a cycle involving ' +
             ', '.join(name for name, count in indegree.items() if count))
    return {'version': 1, 'nodes': nodes, 'edges': edges, 'outputs': outputs}
