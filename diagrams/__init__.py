import contextvars
import os
import threading
import unicodedata
import uuid
import warnings
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple, Union

from graphviz import Digraph

# Global duplicate policy default (string or callable). Defaults to "error" when None.
_global_duplicate_policy: Union[str, Callable] = "error"


class _AutoNodeId:
    """Sentinel used to detect when a node id was not supplied."""


_AUTO_NODE_ID = _AutoNodeId()


def set_default_duplicate_policy(policy: Union[str, Callable, None]) -> None:
    """Set the global duplicate policy used when no per-diagram or per-call policy is provided."""
    global _global_duplicate_policy

    if policy is None:
        _global_duplicate_policy = "error"
    else:
        _global_duplicate_policy = policy


def get_default_duplicate_policy() -> Union[str, Callable]:
    """Retrieve the current global default duplicate policy."""
    return _global_duplicate_policy


def _normalize_key(value: str) -> str:
    """Normalize label/id for dedup comparison (case, whitespace, unicode-normalized)."""
    normalized = unicodedata.normalize("NFKC", value)

    return "".join(normalized.split()).lower()


def _policy_display_name(policy: Union[str, Callable, None]) -> str:
    """Return a readable name for the effective policy."""
    if isinstance(policy, str):
        return policy
    if callable(policy):
        return getattr(policy, "__name__", "callable")
    default = get_default_duplicate_policy()
    if isinstance(default, str):
        return default
    return getattr(default, "__name__", "callable")


def _policy_allows_duplicates(policy: Union[str, Callable, None], policy_func: Callable) -> bool:
    """Return True if the active policy intentionally permits duplicates."""
    if isinstance(policy, str):
        return policy.lower() == "warn"
    if callable(policy):
        if policy is _warn_policy:
            return True
        if policy in {_error_policy, _copy_policy}:
            return False
        return False
    default = get_default_duplicate_policy()
    if isinstance(default, str):
        return default.lower() == "warn"
    return policy_func is _warn_policy


def _resolve_with_policy(
    diagram: "Diagram",
    policy: Union[str, Callable, None],
    label: str,
    nodeid: str,
    existing_labels: List[str],
    existing_ids: List[str],
) -> Tuple[str, str]:
    """Apply the policy until a stable, permitted label/id pair is produced."""
    policy_func = _resolve_policy(policy)
    allows_duplicates = _policy_allows_duplicates(policy, policy_func)
    is_custom_callable = callable(policy) and policy not in {_error_policy, _warn_policy, _copy_policy}
    initial_label_key = _normalize_key(label)
    initial_id_key = _normalize_key(nodeid)

    if initial_label_key not in existing_labels and initial_id_key not in existing_ids:
        return label, nodeid

    seen: Set[Tuple[str, str]] = set()
    current_label = label
    current_id = nodeid

    while True:
        new_label, new_id = policy_func(
            current_label,
            current_id,
            existing_labels.copy(),
            existing_ids.copy(),
        )

        if not isinstance(new_label, str) or not isinstance(new_id, str):
            raise ValueError("Duplicate policy must return (label, nodeid) strings")

        norm_label = _normalize_key(new_label)
        norm_id = _normalize_key(new_id)
        label_conflict = norm_label in existing_labels
        id_conflict = norm_id in existing_ids

        if not label_conflict and not id_conflict:
            return new_label, new_id

        if allows_duplicates:
            return new_label, new_id

        if is_custom_callable and new_label == current_label:
            return new_label, new_id

        if is_custom_callable and (new_label, new_id) == (current_label, current_id):
            return new_label, new_id

        state = (norm_label, norm_id)
        if state in seen:
            policy_name = _policy_display_name(policy)
            raise ValueError(
                f"Diagram '{diagram.name}': duplicate label '{new_label}' or id '{new_id}' unresolved under '{policy_name}' policy"
            )

        seen.add(state)
        current_label, current_id = new_label, new_id



def _error_policy(label: str, nodeid: str, existing_labels: List[str], existing_ids: List[str]) -> Tuple[str, str]:
    """Built-in duplicate policy: raise ValueError on duplicate label or id."""
    normalized_label = _normalize_key(label)
    normalized_id = _normalize_key(nodeid)
    conflicts: List[str] = []

    if normalized_label in existing_labels:
        conflicts.append(f"label '{label}'")
    if normalized_id in existing_ids:
        conflicts.append(f"id '{nodeid}'")

    if conflicts:
        diagram = getdiagram()
        dname = diagram.name if diagram else "<unknown>"
        raise ValueError(f"Diagram '{dname}': duplicate {', '.join(conflicts)} under 'error' policy")

    return label, nodeid


def _warn_policy(label: str, nodeid: str, existing_labels: List[str], existing_ids: List[str]) -> Tuple[str, str]:
    """Built-in duplicate policy: emit warning but keep the name, but assign a unique ID."""
    normalized_label = _normalize_key(label)
    normalized_id = _normalize_key(nodeid)
    conflicts: List[str] = []

    if normalized_label in existing_labels:
        conflicts.append(f"label '{label}'")
    if normalized_id in existing_ids:
        conflicts.append(f"id '{nodeid}'")

    if conflicts:
        diagram = getdiagram()
        dname = diagram.name if diagram else "<unknown>"
        warnings.warn(
            f"Diagram '{dname}': duplicate {', '.join(conflicts)} under 'warn' policy",
            stacklevel=2,
        )

    new_id = nodeid
    if normalized_id in existing_ids:
        base_id = nodeid or "node"
        suffix = 1
        candidate = f"{base_id}_warn{suffix}"
        while _normalize_key(candidate) in existing_ids:
            suffix += 1
            candidate = f"{base_id}_warn{suffix}"
        new_id = candidate

    return label, new_id


def _copy_policy(label: str, nodeid: str, existing_labels: List[str], existing_ids: List[str]) -> Tuple[str, str]:
    """Built-in duplicate policy: generate unique label and/or id by appending a numeric suffix."""
    new_label = label
    base_label = label
    idx = 1

    while _normalize_key(new_label) in existing_labels:
        new_label = f"{base_label}_{idx}"
        idx += 1

    new_id = nodeid
    base_id = nodeid
    id_idx = 1

    while _normalize_key(new_id) in existing_ids:
        new_id = f"{base_id}_{id_idx}"
        id_idx += 1

    return new_label, new_id


def _resolve_policy(policy: Union[str, Callable, None]) -> Callable[[str, str, List[str], List[str]], Tuple[str, str]]:
    """Map a policy specification to a callable implementation."""
    effective = policy
    if effective is None:
        effective = get_default_duplicate_policy()
    if isinstance(effective, str):
        if effective == "error":
            return _error_policy
        elif effective == "warn":
            return _warn_policy
        elif effective == "copy":
            return _copy_policy
        else:
            raise ValueError(f"Unknown duplicate policy '{effective}'")
    elif callable(effective):
        return effective  # type: ignore
    else:
        raise ValueError(f"Invalid duplicate policy '{effective}'")

# Global contexts for a diagrams and a cluster.
#
# These global contexts are for letting the clusters and nodes know
# where context they are belong to. So the all clusters and nodes does
# not need to specify the current diagrams or cluster via parameters.
__diagram = contextvars.ContextVar("diagrams")
__cluster = contextvars.ContextVar("cluster")
_diagram_ctx = __diagram


def getdiagram() -> "Diagram":
    try:
        return __diagram.get()
    except LookupError:
        return None


def setdiagram(diagram: "Diagram"):
    __diagram.set(diagram)


def getcluster() -> "Cluster":
    try:
        return __cluster.get()
    except LookupError:
        return None


def setcluster(cluster: "Cluster"):
    __cluster.set(cluster)


class Diagram:
    __directions = ("TB", "BT", "LR", "RL")
    __curvestyles = ("ortho", "curved")
    __outformats = ("png", "jpg", "svg", "pdf", "dot")

    # fmt: off
    _default_graph_attrs = {
        "pad": "2.0",
        "splines": "ortho",
        "nodesep": "0.60",
        "ranksep": "0.75",
        "fontname": "Sans-Serif",
        "fontsize": "15",
        "fontcolor": "#2D3436",
    }
    _default_node_attrs = {
        "shape": "box",
        "style": "rounded",
        "fixedsize": "true",
        "width": "1.4",
        "height": "1.4",
        "labelloc": "b",
        # imagepos attribute is not backward compatible
        # TODO: check graphviz version to see if "imagepos" is available >= 2.40
        # https://github.com/xflr6/graphviz/blob/master/graphviz/backend.py#L248
        # "imagepos": "tc",
        "imagescale": "true",
        "fontname": "Sans-Serif",
        "fontsize": "13",
        "fontcolor": "#2D3436",
    }
    _default_edge_attrs = {
        "color": "#7B8894",
    }

    # fmt: on

    # TODO: Label position option
    # TODO: Save directory option (filename + directory?)
    def __init__(
        self,
        name: str = "",
        filename: str = "",
        direction: str = "LR",
        curvestyle: str = "ortho",
        outformat: Union[str, list[str]] = "png",
        autolabel: bool = False,
        show: bool = True,
        strict: bool = False,
        graph_attr: Optional[dict] = None,
        node_attr: Optional[dict] = None,
        edge_attr: Optional[dict] = None,
        duplicate_policy: Union[str, Callable, None] = None,
    ):
        """Diagram represents a global diagrams context.

        :param name: Diagram name. It will be used for output filename if the
            filename isn't given.
        :param filename: The output filename, without the extension (.png).
            If not given, it will be generated from the name.
        :param direction: Data flow direction. Default is 'left to right'.
        :param curvestyle: Curve bending style. One of "ortho" or "curved".
        :param outformat: Output file format. Default is 'png'.
        :param show: Open generated image after save if true, just only save otherwise.
        :param graph_attr: Provide graph_attr dot config attributes.
        :param node_attr: Provide node_attr dot config attributes.
        :param edge_attr: Provide edge_attr dot config attributes.
        :param strict: Rendering should merge multi-edges.
        :param duplicate_policy: Deduplication policy for node labels/ids within this diagram.
        """
        if graph_attr is None:
            graph_attr = {}
        if node_attr is None:
            node_attr = {}
        if edge_attr is None:
            edge_attr = {}
        self.name = name
        if not name and not filename:
            filename = "diagrams_image"
        elif not filename:
            filename = "_".join(self.name.split()).lower()
        self.filename = filename
        self._strict = strict
        self.dot = Digraph(self.name, filename=self.filename, strict=self._strict)

        # Set attributes.
        for k, v in self._default_graph_attrs.items():
            self.dot.graph_attr[k] = v
        self.dot.graph_attr["label"] = self.name
        for k, v in self._default_node_attrs.items():
            self.dot.node_attr[k] = v
        for k, v in self._default_edge_attrs.items():
            self.dot.edge_attr[k] = v

        if not self._validate_direction(direction):
            raise ValueError(f'"{direction}" is not a valid direction')
        self.dot.graph_attr["rankdir"] = direction

        if not self._validate_curvestyle(curvestyle):
            raise ValueError(f'"{curvestyle}" is not a valid curvestyle')
        self.dot.graph_attr["splines"] = curvestyle

        if isinstance(outformat, list):
            for one_format in outformat:
                if not self._validate_outformat(one_format):
                    raise ValueError(
                        f'"{one_format}" is not a valid output format')
        else:
            if not self._validate_outformat(outformat):
                raise ValueError(f'"{outformat}" is not a valid output format')
        self.outformat = outformat

        # Merge passed in attributes
        self.dot.graph_attr.update(graph_attr)
        self.dot.node_attr.update(node_attr)
        self.dot.edge_attr.update(edge_attr)

        self.show = show
        self.autolabel = autolabel

        # deduplication related structures
        # Per-diagram duplicate policy
        self.duplicate_policy: Union[str, Callable, None] = duplicate_policy
        # Nodes created in this diagram
        self._nodes: List["Node"] = []
        # Edges created between nodes in this diagram
        self._edges: List[Tuple["Node", "Node", Dict[str, str]]] = []
        # record of deduplication events
        self._dedup_events: List[Dict] = []
        # undo/redo stacks for node operations
        self._undo_stack: List[Tuple[str, List["Node"]]] = []
        self._redo_stack: List[Tuple[str, List["Node"]]] = []
        # lock used for thread-safe batch creation of nodes
        self._lock = threading.Lock()

    def __str__(self) -> str:
        return str(self.dot)

    def __enter__(self):
        setdiagram(self)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.render()
        # Remove the graphviz file leaving only the image.
        os.remove(self.filename)
        setdiagram(None)

    def _repr_png_(self):
        return self.dot.pipe(format="png")

    def _validate_direction(self, direction: str) -> bool:
        return direction.upper() in self.__directions

    def _validate_curvestyle(self, curvestyle: str) -> bool:
        return curvestyle.lower() in self.__curvestyles

    def _validate_outformat(self, outformat: str) -> bool:
        return outformat.lower() in self.__outformats

    def node(self, nodeid: str, label: str, **attrs) -> None:
        """Create a new node."""
        self.dot.node(nodeid, label=label, **attrs)

    def connect(self, node: "Node", node2: "Node", edge: "Edge") -> None:
        """Connect the two Nodes."""
        attrs = edge.attrs.copy()
        self.dot.edge(node.nodeid, node2.nodeid, **attrs)
        self._edges.append((node, node2, attrs))

    def subgraph(self, dot: Digraph) -> None:
        """Create a subgraph for clustering"""
        self.dot.subgraph(dot)

    def render(self) -> None:
        if isinstance(self.outformat, list):
            for one_format in self.outformat:
                self.dot.render(format=one_format, view=self.show, quiet=True)
        else:
            self.dot.render(format=self.outformat, view=self.show, quiet=True)

    def undo(self) -> None:
        """Undo the most recent node addition."""
        if not self._undo_stack:
            return
        op_type, nodes = self._undo_stack.pop()
        if op_type == "add":
            # Remove these nodes from our internal list
            for n in nodes:
                if n in self._nodes:
                    self._nodes.remove(n)
            # push onto redo stack
            self._redo_stack.append((op_type, nodes))
            # rebuild graphviz dot to reflect removal
            self._rebuild()

    def redo(self) -> None:
        """Redo the most recently undone node addition."""
        if not self._redo_stack:
            return

        op_type, nodes = self._redo_stack.pop()

        if op_type == "add":
            token = _diagram_ctx.set(self)

            existing_labels = [
                _normalize_key(getattr(n, "_dedup_label", n.label)) for n in self._nodes
            ]
            existing_ids = [_normalize_key(n.nodeid) for n in self._nodes]

            restored: List["Node"] = []

            try:
                for node in nodes:
                    policy_spec = node._duplicate_policy_spec

                    try:
                        resolved_label, resolved_id = _resolve_with_policy(
                            self,
                            policy_spec,
                            node._raw_label,
                            node._original_id,
                            existing_labels,
                            existing_ids,
                        )
                    except ValueError:
                        self._dedup_events.append(
                            {
                                "action": "rejected",
                                "label": node._raw_label,
                                "nodeid": node._original_id,
                                "policy": _policy_display_name(policy_spec),
                            }
                        )
                        raise

                    node._id = resolved_id
                    dedup_label = resolved_label
                    node._dedup_label = dedup_label
                    node.label = dedup_label

                    if self.autolabel:
                        prefix = node.__class__.__name__
                        node.label = prefix + ("\n" + dedup_label if dedup_label else "")

                    node._diagram = self
                    self._nodes.append(node)

                    event: Dict = {
                        "action": "added",
                        "label": node.label,
                        "nodeid": node.nodeid,
                        "policy": _policy_display_name(policy_spec),
                    }

                    if dedup_label != node._raw_label or node.nodeid != node._original_id:
                        event["action"] = "renamed"
                        event["old_label"] = node._raw_label
                        event["old_nodeid"] = node._original_id

                    if hasattr(node, "_dedup_event_index") and node._dedup_event_index is not None:
                        if 0 <= node._dedup_event_index < len(self._dedup_events):
                            self._dedup_events[node._dedup_event_index] = event
                        else:
                            self._dedup_events.append(event)
                            node._dedup_event_index = len(self._dedup_events) - 1
                    else:
                        self._dedup_events.append(event)
                        node._dedup_event_index = len(self._dedup_events) - 1

                    restored.append(node)
                    existing_labels.append(_normalize_key(dedup_label))
                    existing_ids.append(_normalize_key(node.nodeid))

                self._undo_stack.append((op_type, nodes))
                self._rebuild()
            except Exception:
                for node in restored:
                    if node in self._nodes:
                        self._nodes.remove(node)

                self._rebuild()
                raise
            finally:
                _diagram_ctx.reset(token)

    def _rebuild(self) -> None:
        """Rebuild the underlying graphviz structures from current nodes."""

        # reset the top-level graph
        saved_graph_attr = dict(self.dot.graph_attr)
        saved_node_attr = dict(self.dot.node_attr)
        saved_edge_attr = dict(self.dot.edge_attr)
        self.dot = Digraph(self.name, filename=self.filename, strict=self._strict)
        self.dot.graph_attr.update(saved_graph_attr)
        self.dot.node_attr.update(saved_node_attr)
        self.dot.edge_attr.update(saved_edge_attr)

        # gather clusters present
        clusters = {n._cluster for n in self._nodes if n._cluster}

        # reset clusters
        for cluster in clusters:
            c_graph_attr = dict(cluster.dot.graph_attr)
            c_node_attr = dict(cluster.dot.node_attr)
            c_edge_attr = dict(cluster.dot.edge_attr)
            cluster.dot = Digraph(cluster.name)
            cluster.dot.graph_attr.update(c_graph_attr)
            cluster.dot.node_attr.update(c_node_attr)
            cluster.dot.edge_attr.update(c_edge_attr)

        # re-add nodes to graphviz structures
        for node in self._nodes:
            if node._cluster:
                node._cluster.node(node.nodeid, node.label, **node._attrs)
            else:
                self.node(node.nodeid, node.label, **node._attrs)

        # embed clusters into diagram dot respecting nesting
        for cluster in clusters:
            if cluster._parent:
                cluster._parent.subgraph(cluster.dot)
            else:
                self.subgraph(cluster.dot)

        # re-add edges whose endpoints still exist
        for src, dst, attrs in self._edges:
            if src in self._nodes and dst in self._nodes:
                self.dot.edge(src.nodeid, dst.nodeid, **attrs)

    def dedup_report(self) -> Union[List[Dict], Dict]:
        """Return a list/dict summarizing deduplication events."""
        return self._dedup_events

    def add_nodes(self, labels: List[str], duplicate_policy: Union[str, Callable, None] = None) -> List['Node']:
        """Atomically create multiple nodes from a list of labels. If any node violates
        the deduplication policy, the batch creation fails and no nodes are added.
        When invoked via this method, node addition is thread-safe and will respect
        the provided per-call duplicate_policy, falling back to the Diagram-level or
        global policy as needed."""
        if not isinstance(labels, list):
            raise ValueError("labels must be a list of strings")

        for lbl in labels:
            if not isinstance(lbl, str):
                raise ValueError("Node labels must be strings")

        nodes: List["Node"] = []

        with self._lock:
            if duplicate_policy is not None:
                effective_policy_spec: Union[str, Callable, None] = duplicate_policy
            elif self.duplicate_policy is not None:
                effective_policy_spec = self.duplicate_policy
            else:
                effective_policy_spec = get_default_duplicate_policy()

            token = _diagram_ctx.set(self)

            try:
                for lbl in labels:
                    node = Node(
                        lbl,
                        duplicate_policy=effective_policy_spec,
                        batch=True,
                    )
                    nodes.append(node)

                # Bundle the batch into undo stack as one operation.
                self._undo_stack.append(("add", nodes))

                # Any new addition invalidates the redo history.
                self._redo_stack.clear()
                return nodes
            except Exception:
                # In case of any error during actual creation, detach nodes that may have been created.
                for n in nodes:
                    if n in self._nodes:
                        self._nodes.remove(n)

                # Remove dedup events associated with nodes that were rolled back.
                removed = 0
                scan_index = len(self._dedup_events) - 1
                while removed < len(nodes) and scan_index >= 0:
                    event = self._dedup_events[scan_index]
                    if event.get("action") in {"added", "renamed"}:
                        self._dedup_events.pop(scan_index)
                        removed += 1
                    scan_index -= 1

                self._rebuild()
                raise
            finally:
                _diagram_ctx.reset(token)


class Cluster:
    __directions = ("TB", "BT", "LR", "RL")
    __bgcolors = ("#E5F5FD", "#EBF3E7", "#ECE8F6", "#FDF7E3")

    # fmt: off
    _default_graph_attrs = {
        "shape": "box",
        "style": "rounded",
        "labeljust": "l",
        "pencolor": "#AEB6BE",
        "fontname": "Sans-Serif",
        "fontsize": "12",
    }

    # fmt: on

    # FIXME:
    #  Cluster direction does not work now. Graphviz couldn't render
    #  correctly for a subgraph that has a different rank direction.
    def __init__(
        self,
        label: str = "cluster",
        direction: str = "LR",
        graph_attr: Optional[dict] = None,
    ):
        """Cluster represents a cluster context.

        :param label: Cluster label.
        :param direction: Data flow direction. Default is 'left to right'.
        :param graph_attr: Provide graph_attr dot config attributes.
        """
        if graph_attr is None:
            graph_attr = {}
        self.label = label
        self.name = "cluster_" + self.label

        self.dot = Digraph(self.name)

        # Set attributes.
        for k, v in self._default_graph_attrs.items():
            self.dot.graph_attr[k] = v
        self.dot.graph_attr["label"] = self.label

        if not self._validate_direction(direction):
            raise ValueError(f'"{direction}" is not a valid direction')
        self.dot.graph_attr["rankdir"] = direction

        # Node must be belong to a diagrams.
        self._diagram = getdiagram()
        if self._diagram is None:
            raise EnvironmentError("Global diagrams context not set up")
        self._parent = getcluster()

        # Set cluster depth for distinguishing the background color
        self.depth = self._parent.depth + 1 if self._parent else 0
        coloridx = self.depth % len(self.__bgcolors)
        self.dot.graph_attr["bgcolor"] = self.__bgcolors[coloridx]

        # Merge passed in attributes
        self.dot.graph_attr.update(graph_attr)

    def __enter__(self):
        setcluster(self)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self._parent:
            self._parent.subgraph(self.dot)
        else:
            self._diagram.subgraph(self.dot)
        setcluster(self._parent)

    def _validate_direction(self, direction: str) -> bool:
        return direction.upper() in self.__directions

    def node(self, nodeid: str, label: str, **attrs) -> None:
        """Create a new node in the cluster."""
        self.dot.node(nodeid, label=label, **attrs)

    def subgraph(self, dot: Digraph) -> None:
        self.dot.subgraph(dot)


class Node:
    """Node represents a node for a specific backend service."""

    _provider = None
    _type = None

    _icon_dir = None
    _icon = None

    _height = 1.9

    def __init__(
        self,
        label: str = "",
        *,
        nodeid: Union[str, "_AutoNodeId"] = _AUTO_NODE_ID,
        duplicate_policy: Union[str, Callable, None] = None,
        batch: bool = False,
        **attrs: Dict,
    ):
        """Node represents a system component.

        :param label: Node label.
        :param duplicate_policy: Optional duplicate policy override for this node creation.
            Can be "error", "warn", or "copy" to use built-in policies, a callable conforming
            to `(label, nodeid, existing_labels, existing_ids) -> (label, nodeid)`, or None to
            defer to the Diagram- or global-level policy.
        :param batch: Internal flag used to suppress undo stack management when invoked as part of a batch.
        """
        if not isinstance(label, str):
            raise ValueError("Node label must be a string")

        # Generates an ID for identifying a node, unless specified
        if nodeid is _AUTO_NODE_ID:
            proposed_id = self._rand_id()
        else:
            if not isinstance(nodeid, str):
                raise ValueError("Node id must be a string")
            proposed_id = nodeid

        self._raw_label = label
        proposed_label = label
        orig_id = proposed_id

        # Node must belong to a diagram.
        self._diagram = getdiagram()
        if self._diagram is None:
            raise EnvironmentError("Global diagrams context not set up")

        # Determine effective duplicate policy: per-call > per-diagram > global.
        effective_policy_spec: Union[str, Callable, None]

        if duplicate_policy is not None:
            effective_policy_spec = duplicate_policy
        elif self._diagram.duplicate_policy is not None:
            effective_policy_spec = self._diagram.duplicate_policy
        else:
            effective_policy_spec = get_default_duplicate_policy()

        # Retain what policy was used on this node for potential redo operations.
        self._duplicate_policy_spec = effective_policy_spec
        self._original_id = orig_id
        self._dedup_event_index: Optional[int] = None

        # Existing labels/ids in this diagram.
        existing_labels = [
            _normalize_key(getattr(n, "_dedup_label", n.label)) for n in self._diagram._nodes
        ]
        existing_ids = [_normalize_key(n.nodeid) for n in self._diagram._nodes]

        # Apply policy.
        try:
            proposed_label, proposed_id = _resolve_with_policy(
                self._diagram,
                effective_policy_spec,
                proposed_label,
                proposed_id,
                existing_labels,
                existing_ids,
            )
        except ValueError:
            # Record the rejected event.
            self._diagram._dedup_events.append(
                {
                    "action": "rejected",
                    "label": label,
                    "nodeid": proposed_id,
                    "policy": _policy_display_name(effective_policy_spec),
                }
            )
            raise

        # Adjust label and id if required.
        self._id = proposed_id
        self._dedup_label = proposed_label
        self.label = proposed_label

        # Compute autolabel after deduplication.
        if self._diagram.autolabel:
            prefix = self.__class__.__name__
            if self.label:
                self.label = prefix + "\n" + self.label
            else:
                self.label = prefix

        # fmt: off
        # If a node has an icon, increase the height slightly to avoid
        # that label being spanned between icon image and white space.
        # Increase the height by the number of new lines included in the label.
        padding = 0.4 * (self.label.count('\n'))
        self._attrs = {
            "shape": "none",
            "height": str(self._height + padding),
            "image": self._load_icon(),
        } if self._icon else {}

        # fmt: on
        self._attrs.update(attrs)

        self._cluster = getcluster()

        # If a node is in the cluster context, add it to cluster.
        if self._cluster:
            self._cluster.node(self._id, self.label, **self._attrs)
        else:
            self._diagram.node(self._id, self.label, **self._attrs)

        # Append to node list and optionally to undo stack.
        self._diagram._nodes.append(self)

        if not batch:
            self._diagram._undo_stack.append(("add", [self]))
            self._diagram._redo_stack.clear()

        # Log deduplication event.
        event: Dict = {
            "action": "added",
            "label": self.label,
            "nodeid": self._id,
            "policy": _policy_display_name(self._duplicate_policy_spec),
        }
        # If the deduplication policy modified label or id values (excluding autolabel), mark as renamed.
        if proposed_label != label or proposed_id != orig_id:
            event["action"] = "renamed"
            event["old_label"] = label
            event["old_nodeid"] = orig_id
        self._diagram._dedup_events.append(event)
        self._dedup_event_index = len(self._diagram._dedup_events) - 1

    def __repr__(self):
        _name = self.__class__.__name__
        return f"<{self._provider}.{self._type}.{_name}>"

    def __sub__(self, other: Union["Node", List["Node"], "Edge"]):
        """Implement Self - Node, Self - [Nodes] and Self - Edge."""
        if isinstance(other, list):
            for node in other:
                self.connect(node, Edge(self))
            return other
        elif isinstance(other, Node):
            return self.connect(other, Edge(self))
        else:
            other.node = self
            return other

    def __rsub__(self, other: Union[List["Node"], List["Edge"]]):
        """Called for [Nodes] and [Edges] - Self because list don't have __sub__ operators."""
        for o in other:
            if isinstance(o, Edge):
                o.connect(self)
            else:
                o.connect(self, Edge(self))
        return self

    def __rshift__(self, other: Union["Node", List["Node"], "Edge"]):
        """Implements Self >> Node, Self >> [Nodes] and Self Edge."""
        if isinstance(other, list):
            for node in other:
                self.connect(node, Edge(self, forward=True))
            return other
        elif isinstance(other, Node):
            return self.connect(other, Edge(self, forward=True))
        else:
            other.forward = True
            other.node = self
            return other

    def __lshift__(self, other: Union["Node", List["Node"], "Edge"]):
        """Implements Self << Node, Self << [Nodes] and Self << Edge."""
        if isinstance(other, list):
            for node in other:
                self.connect(node, Edge(self, reverse=True))
            return other
        elif isinstance(other, Node):
            return self.connect(other, Edge(self, reverse=True))
        else:
            other.reverse = True
            return other.connect(self)

    def __rrshift__(self, other: Union[List["Node"], List["Edge"]]):
        """Called for [Nodes] and [Edges] >> Self because list don't have __rshift__ operators."""
        for o in other:
            if isinstance(o, Edge):
                o.forward = True
                o.connect(self)
            else:
                o.connect(self, Edge(self, forward=True))
        return self

    def __rlshift__(self, other: Union[List["Node"], List["Edge"]]):
        """Called for [Nodes] << Self because list of Nodes don't have __lshift__ operators."""
        for o in other:
            if isinstance(o, Edge):
                o.reverse = True
                o.connect(self)
            else:
                o.connect(self, Edge(self, reverse=True))
        return self

    @property
    def nodeid(self):
        return self._id

    # TODO: option for adding flow description to the connection edge
    def connect(self, node: "Node", edge: "Edge"):
        """Connect to other node.

        :param node: Other node instance.
        :param edge: Type of the edge.
        :return: Connected node.
        """
        if not isinstance(node, Node):
            ValueError(f"{node} is not a valid Node")
        if not isinstance(edge, Edge):
            ValueError(f"{edge} is not a valid Edge")
        # An edge must be added on the global diagrams, not a cluster.
        self._diagram.connect(self, node, edge)
        return node

    @staticmethod
    def _rand_id():
        return uuid.uuid4().hex

    def _load_icon(self):
        basedir = Path(os.path.abspath(os.path.dirname(__file__)))
        return os.path.join(basedir.parent, self._icon_dir, self._icon)


class Edge:
    """Edge represents an edge between two nodes."""

    _default_edge_attrs = {
        "fontcolor": "#2D3436",
        "fontname": "Sans-Serif",
        "fontsize": "13",
    }

    def __init__(
        self,
        node: "Node" = None,
        forward: bool = False,
        reverse: bool = False,
        label: str = "",
        color: str = "",
        style: str = "",
        **attrs: Dict,
    ):
        """Edge represents an edge between two nodes.

        :param node: Parent node.
        :param forward: Points forward.
        :param reverse: Points backward.
        :param label: Edge label.
        :param color: Edge color.
        :param style: Edge style.
        :param attrs: Other edge attributes
        """
        if node is not None:
            assert isinstance(node, Node)

        self.node = node
        self.forward = forward
        self.reverse = reverse

        self._attrs = {}

        # Set attributes.
        for k, v in self._default_edge_attrs.items():
            self._attrs[k] = v

        if label:
            # Graphviz complaining about using label for edges, so replace it with xlabel.
            # Update: xlabel option causes the misaligned label position:
            # https://github.com/mingrammer/diagrams/issues/83
            self._attrs["label"] = label
        if color:
            self._attrs["color"] = color
        if style:
            self._attrs["style"] = style
        self._attrs.update(attrs)

    def __sub__(self, other: Union["Node", "Edge", List["Node"]]):
        """Implement Self - Node or Edge and Self - [Nodes]"""
        return self.connect(other)

    def __rsub__(self, other: Union[List["Node"],
                 List["Edge"]]) -> List["Edge"]:
        """Called for [Nodes] or [Edges] - Self because list don't have __sub__ operators."""
        return self.append(other)

    def __rshift__(self, other: Union["Node", "Edge", List["Node"]]):
        """Implements Self >> Node or Edge and Self >> [Nodes]."""
        self.forward = True
        return self.connect(other)

    def __lshift__(self, other: Union["Node", "Edge", List["Node"]]):
        """Implements Self << Node or Edge and Self << [Nodes]."""
        self.reverse = True
        return self.connect(other)

    def __rrshift__(self,
                    other: Union[List["Node"],
                                 List["Edge"]]) -> List["Edge"]:
        """Called for [Nodes] or [Edges] >> Self because list of Edges don't have __rshift__ operators."""
        return self.append(other, forward=True)

    def __rlshift__(self,
                    other: Union[List["Node"],
                                 List["Edge"]]) -> List["Edge"]:
        """Called for [Nodes] or [Edges] << Self because list of Edges don't have __lshift__ operators."""
        return self.append(other, reverse=True)

    def append(self,
               other: Union[List["Node"],
                            List["Edge"]],
               forward=None,
               reverse=None) -> List["Edge"]:
        result = []
        for o in other:
            if isinstance(o, Edge):
                o.forward = forward if forward else o.forward
                o.reverse = reverse if reverse else o.reverse
                self._attrs = o.attrs.copy()
                result.append(o)
            else:
                result.append(
                    Edge(
                        o,
                        forward=forward,
                        reverse=reverse,
                        **self._attrs))
        return result

    def connect(self, other: Union["Node", "Edge", List["Node"]]):
        if isinstance(other, list):
            for node in other:
                self.node.connect(node, self)
            return other
        elif isinstance(other, Edge):
            self._attrs = other._attrs.copy()
            return self
        else:
            if self.node is not None:
                return self.node.connect(other, self)
            else:
                self.node = other
                return self

    @property
    def attrs(self) -> Dict:
        if self.forward and self.reverse:
            direction = "both"
        elif self.forward:
            direction = "forward"
        elif self.reverse:
            direction = "back"
        else:
            direction = "none"
        return {**self._attrs, "dir": direction}


Group = Cluster
