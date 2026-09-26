"""Assemble ordinary native Falcor render graphs from owned pass descriptions.

``make_graph`` never generates a Schema, snapshots a Scene, or seals a graph.
Legacy generation transactions are intentionally not exported here.
"""


def make_graph(name, definition, *, base_directory=None):
    """Return a native ``falcor.RenderGraph`` from a JSON path or dictionary.

    The declaration requires ``version: 1`` and a nonempty ``nodes`` array;
    ``edges``, ``outputs`` and descriptive ``metadata`` are optional. Nodes
    contain ``name`` and ``type`` (or ``description`` naming reusable pass JSON),
    plus optional ``properties``, ``file_inputs`` and descriptive ``metadata``.
    Reusable properties merge recursively with node overrides.

    ``shader.file`` and explicit dotted ``file_inputs`` resolve at the file
    authoring each value. In-memory definitions use ``base_directory`` or the
    current directory. Assets remain live; the loader neither reads nor freezes
    them. Falcor owns pass registration, reflection, resource compatibility and
    scheduling. The returned graph remains editable through its native API.
    """
    if __package__:
        from .native_pipeline import load_graph_definition
    else:
        from native_pipeline import load_graph_definition

    if not isinstance(name, str) or not name.strip():
        raise ValueError('graph name must be a nonempty string')
    declaration = load_graph_definition(definition, base_directory=base_directory)
    from falcor import RenderGraph, createPass

    graph = RenderGraph(name)
    for node in declaration['nodes']:
        graph.addPass(createPass(node['type'], node['properties']), node['name'])
    for source, target in declaration['edges']:
        graph.addEdge(source, target)
    for output in declaration['outputs']:
        graph.markOutput(output)
    if any(node['type'] in {'CustomRenderPiplineHistoryReadPass', 'CustomRenderPiplineHistoryWritePass'}
           for node in declaration['nodes']):
        from falcor import customRenderPiplineBindHistory
        customRenderPiplineBindHistory(graph)
    return graph
