"""Model Modularization increment: derive cross-module connections from a modularization's
own ports -- the one piece of real, computed behavior this increment implements (every other
new type is purely declarative/validated data, constructed directly by a caller).

```text
Module A output species
        |
        v
shared canonical species
        |
        v
Module B input
```

``derive_cross_module_connections`` never stores anything, never mutates its inputs, and never
infers a module boundary on its own -- it only reads the ``ModulePort`` rows a caller (or a
future automatic-discovery algorithm -- see this module's own docstring footer) already
declared, and reports every pair that shares a canonical species across two different modules
of the same modularization. No new canonical state, no duplicated species.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.agent2.types import ModelModularization, ModulePort, ModulePortDirection

#: A port in either of these directions may legitimately act as the *upstream* (sending) side
#: of a derived connection.
_UPSTREAM_DIRECTIONS = frozenset({ModulePortDirection.OUTPUT, ModulePortDirection.INPUT_OUTPUT})
#: A port in either of these directions may legitimately act as the *downstream* (receiving)
#: side. An ``INPUT_OUTPUT`` port paired with another ``INPUT_OUTPUT`` port on the same species
#: therefore yields two connections, one in each direction -- a real, disclosed structural
#: possibility, never collapsed into a single, arbitrarily-directed one.
_DOWNSTREAM_DIRECTIONS = frozenset({ModulePortDirection.INPUT, ModulePortDirection.INPUT_OUTPUT})


@dataclass(frozen=True, slots=True)
class ModuleConnection:
    """One derived cross-module connection: an upstream port of one module and a downstream
    port of a different module, both of the same modularization, sharing one canonical
    species. Always computed, never persisted on ``ModelSpecification`` -- re-derive from the
    same ``module_ports`` whenever needed."""

    modularization_id: str
    species_id: str
    upstream_module_id: str
    upstream_port_id: str
    downstream_module_id: str
    downstream_port_id: str


def derive_cross_module_connections(
    modularization: ModelModularization, ports: tuple[ModulePort, ...]
) -> tuple[ModuleConnection, ...]:
    """Every cross-module connection ``modularization``'s own ports imply.

    ``ports`` is every ``ModulePort`` row to consider -- typically
    ``ModelSpecification.module_ports`` filtered to this one modularization's own
    ``module_ids`` by the caller, though passing the full, unfiltered collection is also safe:
    a port whose own ``modularization_id`` does not match ``modularization.modularization_id``
    is simply never considered (never raises -- this is a pure query, not a validator;
    ``ModelSpecification.__post_init__`` already rejects a dangling/inconsistent port at
    construction time).

    Deterministic and order-independent: returns every valid (upstream, downstream) pair,
    sorted by ``(species_id, upstream_module_id, downstream_module_id)`` for stable output --
    never silently picks "the" connection when several real candidates exist.
    """
    relevant = tuple(p for p in ports if p.modularization_id == modularization.modularization_id)
    connections: list[ModuleConnection] = []
    for upstream in relevant:
        if upstream.direction not in _UPSTREAM_DIRECTIONS:
            continue
        for downstream in relevant:
            if downstream.direction not in _DOWNSTREAM_DIRECTIONS:
                continue
            if downstream.species_id != upstream.species_id:
                continue
            if downstream.module_id == upstream.module_id:
                continue
            connections.append(
                ModuleConnection(
                    modularization_id=modularization.modularization_id,
                    species_id=upstream.species_id,
                    upstream_module_id=upstream.module_id,
                    upstream_port_id=upstream.port_id,
                    downstream_module_id=downstream.module_id,
                    downstream_port_id=downstream.port_id,
                )
            )
    return tuple(
        sorted(
            connections,
            key=lambda c: (c.species_id, c.upstream_module_id, c.downstream_module_id),
        )
    )


__all__ = ["ModuleConnection", "derive_cross_module_connections"]
