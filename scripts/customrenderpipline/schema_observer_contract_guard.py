"""Per-observer verified dependency hashes, not an mtime or process-global cache."""
import hashlib
from pathlib import Path
from schema_observer_codegen import load_contract


class ContractGuard:
    def __init__(self, artifacts):
        contract = load_contract(artifacts)
        generated = contract['artifacts']
        paths = [generated.manifest, generated.metadata, generated.codec]
        if generated.definition is not None:
            paths += [generated.definition, generated.codec.parent/'GBuffer.3d.slang']
        paths += [Path(info['path']) for info in contract['sources'].values()]
        resolved = [path.resolve() for path in paths]
        # emit_observer embeds a resolved Codec include. Keep checking that
        # actual target too, not only a caller-supplied junction/symlink alias.
        self._aliases = tuple((path, target) for path, target in zip(paths, resolved) if path.absolute() != target)
        self._paths = tuple(dict.fromkeys(paths + resolved))
        self._hashes = self._read_hashes()
        # The first parse identifies dependencies. Revalidate after capturing
        # them so a concurrent edit between parse and capture cannot be blessed.
        confirmed = load_contract(generated)
        if confirmed != contract:
            raise ValueError('Schema changed during observer binding; regenerate and rebind')
        self.validate()
        self.contract = confirmed

    def _read_hashes(self):
        try:
            return tuple(hashlib.sha256(path.read_bytes()).digest() for path in self._paths)
        except OSError as error:
            raise ValueError('Schema dependency unavailable; regenerate and rebind: '+str(error)) from error

    def validate(self):
        # Re-read EVERY file on EVERY request: same-size/mtime edits and source,
        # manifest, metadata, codec, raster or definition changes still reject.
        # Only deterministic parsing/semantic validation/code generation is
        # reused; no request skips content checks or relies on stat timestamps.
        # Canonical generated paths need no repeated path resolution. Explicit
        # aliases must still resolve to the target frozen when shaders bound.
        if any(path.resolve() != target for path, target in self._aliases):
            raise ValueError('Schema dependency path changed; regenerate and rebind observer')
        if self._read_hashes() != self._hashes:
            raise ValueError('Schema dependency changed/modified; regenerate and rebind observer')
