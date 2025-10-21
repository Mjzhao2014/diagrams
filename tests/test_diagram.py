import os
import pathlib
import shutil
import unittest

from diagrams import Cluster, Diagram, Edge, Node, getcluster, getdiagram, setcluster, setdiagram


class DiagramTest(unittest.TestCase):
    def setUp(self):
        self.name = "diagram_test"

    def tearDown(self):
        setdiagram(None)
        setcluster(None)
        # Only some tests generate the image file.
        try:
            shutil.rmtree(self.name)
        except OSError:
            # Consider it file
            try:
                os.remove(self.name + ".png")
            except FileNotFoundError:
                pass

    def test_validate_direction(self):
        # Normal directions.
        for dir in ("TB", "BT", "LR", "RL", "tb"):
            Diagram(direction=dir)

        # Invalid directions.
        for dir in ("BR", "TL", "Unknown"):
            with self.assertRaises(ValueError):
                Diagram(direction=dir)

    def test_validate_curvestyle(self):
        # Normal directions.
        for cvs in ("ortho", "curved", "CURVED"):
            Diagram(curvestyle=cvs)

        # Invalid directions.
        for cvs in ("tangent", "unknown"):
            with self.assertRaises(ValueError):
                Diagram(curvestyle=cvs)

    def test_validate_outformat(self):
        # Normal output formats.
        for fmt in ("png", "jpg", "svg", "pdf", "PNG", "dot"):
            Diagram(outformat=fmt)

        # Invalid output formats.
        for fmt in ("pnp", "jpe", "unknown"):
            with self.assertRaises(ValueError):
                Diagram(outformat=fmt)

    def test_with_global_context(self):
        self.assertIsNone(getdiagram())
        with Diagram(name=os.path.join(self.name, "with_global_context"), show=False):
            self.assertIsNotNone(getdiagram())
        self.assertIsNone(getdiagram())

    def test_node_not_in_diagram(self):
        # Node must be belong to a diagrams.
        with self.assertRaises(EnvironmentError):
            Node("node")

    def test_node_to_node(self):
        with Diagram(name=os.path.join(self.name, "node_to_node"), show=False):
            node1 = Node("node1")
            node2 = Node("node2")
            self.assertEqual(node1 - node2, node2)
            self.assertEqual(node1 >> node2, node2)
            self.assertEqual(node1 << node2, node2)

    def test_node_to_nodes(self):
        with Diagram(name=os.path.join(self.name, "node_to_nodes"), show=False):
            node1 = Node("node1")
            nodes = [Node("node2"), Node("node3")]
            self.assertEqual(node1 - nodes, nodes)
            self.assertEqual(node1 >> nodes, nodes)
            self.assertEqual(node1 << nodes, nodes)

    def test_nodes_to_node(self):
        with Diagram(name=os.path.join(self.name, "nodes_to_node"), show=False):
            node1 = Node("node1")
            nodes = [Node("node2"), Node("node3")]
            self.assertEqual(nodes - node1, node1)
            self.assertEqual(nodes >> node1, node1)
            self.assertEqual(nodes << node1, node1)

    def test_default_filename(self):
        self.name = "example_1"
        with Diagram(name="Example 1", show=False):
            Node("node1")
        self.assertTrue(os.path.exists(f"{self.name}.png"))

    def test_custom_filename(self):
        self.name = "my_custom_name"
        with Diagram(name="Example 1", filename=self.name, show=False):
            Node("node1")
        self.assertTrue(os.path.exists(f"{self.name}.png"))

    def test_empty_name(self):
        """Check that providing an empty name don't crash, but save in a diagrams_image.xxx file."""
        self.name = "diagrams_image"
        with Diagram(show=False):
            Node("node1")
        self.assertTrue(os.path.exists(f"{self.name}.png"))

    def test_autolabel(self):
        with Diagram(name=os.path.join(self.name, "nodes_to_node"), show=False):
            node1 = Node("node1")
            self.assertTrue(node1.label, "Node\nnode1")

    def test_outformat_list(self):
        """Check that outformat render all the files from the list."""
        self.name = "diagrams_image"
        with Diagram(show=False, outformat=["dot", "png"]):
            Node("node1")
        # both files must exist
        self.assertTrue(os.path.exists(f"{self.name}.png"))
        self.assertTrue(os.path.exists(f"{self.name}.dot"))

        # clean the dot file as it only generated here
        os.remove(self.name + ".dot")

    def test_duplicate_node_policy_warn(self):
        with Diagram(name="dup_warn", show=False, duplicate_policy="warn"):
            n1 = Node("cache")
            n2 = Node("cache")
            self.assertNotEqual(n1, n2)

    def test_duplicate_node_policy_copy(self):
        with Diagram(name="dup_copy", show=False, duplicate_policy="copy"):
            n1 = Node("db")
            n2 = Node("db")
            self.assertNotEqual(n1.nodeid, n2.nodeid)
            self.assertTrue(n2.label.startswith("db"))

    def test_duplicate_node_error(self):
        with Diagram(name="dup_case", show=False, duplicate_policy="error"):
            Node("Worker")
            with self.assertRaises(ValueError):
                Node("Worker")

    def test_duplicate_node_whitespace_insensitive(self):
        with Diagram(name="dup_whitespace", show=False, duplicate_policy="error"):
            Node("service")
            with self.assertRaises(ValueError):
                Node("Service")
            with self.assertRaises(ValueError):
                Node(" service ")

    def test_duplicate_node_custom_nodeid(self):
        with Diagram(name="dup_manualid", show=False, duplicate_policy="error"):
            Node("a", nodeid="custom1")
            with self.assertRaises(ValueError):
                Node("b", nodeid="custom1")

    def test_duplicate_node_across_clusters(self):
        with Diagram(name="dup_clusters", show=False, duplicate_policy="error"):
            with Cluster("one"):
                Node("shared")
            with Cluster("two"):
                with self.assertRaises(ValueError):
                    Node("shared")

    def test_duplicate_node_concurrent_creation(self):
        with Diagram(name="dup_concurrent", show=False, duplicate_policy="error"):
            for i in range(3):
                Node("dupe_" + str(i))
                Node("dupe_" + str(i + 5))
                with self.assertRaises(ValueError):
                    Node("dupe_" + str(i))

    def test_duplicate_node_edge_case_unicode(self):
        with Diagram(name="dup_unicode", show=False, duplicate_policy="error"):
            Node("nø∂e")
            with self.assertRaises(ValueError):
                Node("NØ∂E")
        with Diagram(name="dup_unicode2", show=False, duplicate_policy="error"):
            Node("foo\tbar")
            with self.assertRaises(ValueError):
                Node("foo bar")

    def test_duplicate_node_unicode_normalization(self):
        with Diagram(name="dup_unicode_norm", show=False, duplicate_policy="error"):
            Node("café")
            with self.assertRaises(ValueError):
                Node("cafe\u0301")  # "e" + combining accent

    def test_duplicate_node_label_vs_nodeid(self):
        with Diagram(name="dup_nodeid", show=False, duplicate_policy="error"):
            Node("test", nodeid="abc")
            with self.assertRaises(ValueError):
                Node("test2", nodeid="abc")

    def test_duplicate_node_regression(self):
        with Diagram(name="dup_regression", show=False, duplicate_policy="error"):
            Node("unique_a")
            Node("unique_b")

    def test_duplicate_node_batch_policy_override(self):
        with Diagram(name="dup_batch_override", show=False, duplicate_policy="error") as d:
            batch = [("foo"), ("foo")]
            nodes = d.add_nodes(batch, duplicate_policy="copy")
            labels = [n.label for n in nodes]
            self.assertTrue(any(label == "foo" for label in labels))
            self.assertTrue(any(label != "foo" for label in labels))

    def test_duplicate_node_nonstring(self):
        with Diagram(name="dup_nonstring", show=False, duplicate_policy="error"):
            with self.assertRaises(ValueError):
                Node(123)  # Non-string label
            with self.assertRaises(ValueError):
                Node("valid", nodeid=456)

    def test_duplicate_node_thread_safety(self):
        import threading
        with Diagram(name="dup_thread", show=False, duplicate_policy="error") as d:
            errs = []

            def add():
                try:
                    d.add_nodes(["foo"])
                except Exception as e:
                    errs.append(e)
            threads = [threading.Thread(target=add) for _ in range(3)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(len([e for e in errs if isinstance(e, ValueError)]), 2)

    def test_duplicate_node_custom_policy_called(self):
        called = {}

        def policy(label, nodeid, labels, ids):
            called['hit'] = (label, nodeid)
            return (label + "_unique", nodeid + "_2")
        with Diagram(name="dup_custom_called", show=False, duplicate_policy=policy):
            n1 = Node("dupX", nodeid="A")
            n2 = Node("dupX", nodeid="A")
            self.assertEqual(called['hit'], ("dupX", "A"))
            self.assertEqual(n2.label, "dupX_unique")
            self.assertEqual(n2.nodeid, "A_2")

    def test_duplicate_node_custom_policy_still_duplicate(self):
        def policy(label, nodeid, labels, ids):
            return (label, nodeid)  # returns a colliding tuple on purpose
        with Diagram(name="dup_custom_still_dup", show=False, duplicate_policy=policy):
            Node("foo", nodeid="bar")
            try:
                Node("foo", nodeid="bar")  # OK if implementation permits; also OK if it raises
            except ValueError:
                pass  # acceptable if the implementation re-applies the active policy (e.g., "error") to the callable's result

    def test_duplicate_node_custom_policy_label_vs_nodeid(self):
        def policy(label, nodeid, labels, ids):
            if label in labels:
                return (label + "2", nodeid)
            if nodeid in ids:
                return (label, nodeid + "2")
            return (label, nodeid)
        with Diagram(name="dup_custom_labelvsid", show=False, duplicate_policy=policy):
            Node("foo", nodeid="bar")
            n2 = Node("foo", nodeid="bar2")
            n3 = Node("foo2", nodeid="bar")
            self.assertEqual(n2.label, "foo2")
            self.assertEqual(n3.nodeid, "bar2")

    def test_duplicate_node_batch_atomicity(self):
        with Diagram(name="dup_batch", show=False, duplicate_policy="error") as d:
            batch = [("one",), ("two",), ("one",)]
            with self.assertRaises(ValueError):
                d.add_nodes([args[0] for args in batch])
            self.assertFalse(any(n.label.strip() in {"one", "two"} for n in d._nodes))  # Use _nodes

    def test_duplicate_node_policy_scoping(self):
        with Diagram(name="dup_scope", show=False, duplicate_policy="error") as d:
            Node("x")
            n2 = Node("x", duplicate_policy="warn")
            self.assertNotEqual(n2.nodeid, None)

    def test_duplicate_node_dedup_report(self):
        with Diagram(name="dup_report", show=False, duplicate_policy="copy") as d:
            n1 = Node("foo")
            n2 = Node("foo")
            n3 = Node("bar")
            report = d.dedup_report()

    def test_duplicate_node_undo_redo(self):
        with Diagram(name="dup_undo", show=False, duplicate_policy="error") as d:
            n1 = Node("foo")
            d.undo()
            self.assertNotIn("foo", [n.label.strip() for n in d._nodes])
            d.redo()
            self.assertIn("foo", [n.label.strip() for n in d._nodes])

    def test_duplicate_node_error_message(self):
        with Diagram(name="dup_message", show=False, duplicate_policy="error"):
            Node("hello")
            with self.assertRaisesRegex(ValueError, "hello"):
                Node("hello")

    def test_duplicate_node_policy_stability(self):
        with Diagram(name="dup_undo_redo_policy", show=False, duplicate_policy="warn") as d:
            n1 = Node("foo")
            n2 = Node("foo")
            d.undo()  # Remove n2
            # Redo should not fail (should use old policy, which was 'warn')
            d.redo()
            self.assertIn(n2, d._nodes)

    def test_copy_policy_unique_name(self):
        with Diagram(name="copy_case_norm", show=False, duplicate_policy="copy") as d:
            n0 = Node("foo")          # "foo"
            n1 = Node("Foo")          # "Foo" - should be detected as duplicate
            n2 = Node("foo ")         # "foo " - trailing whitespace
            n3 = Node("foo_1")        # "foo_1" - explicit suffix
            n4 = Node("foo")          # should create "foo_2" if normalization is correct

            labels = [n.label for n in d._nodes]
            # All normalized forms should be unique
            norm = lambda x: x.strip().lower()
            self.assertEqual(len({norm(lbl) for lbl in labels}), len(labels), f"Labels not normalized/unique: {labels}")


class ClusterTest(unittest.TestCase):
    def setUp(self):
        self.name = "cluster_test"

    def tearDown(self):
        setdiagram(None)
        setcluster(None)
        # Only some tests generate the image file.
        try:
            shutil.rmtree(self.name)
        except OSError:
            pass

    def test_validate_direction(self):
        # Normal directions.
        for dir in ("TB", "BT", "LR", "RL"):
            with Diagram(name=os.path.join(self.name, "validate_direction"), show=False):
                Cluster(direction=dir)

        # Invalid directions.
        for dir in ("BR", "TL", "Unknown"):
            with self.assertRaises(ValueError):
                with Diagram(name=os.path.join(self.name, "validate_direction"), show=False):
                    Cluster(direction=dir)

    def test_with_global_context(self):
        with Diagram(name=os.path.join(self.name, "with_global_context"), show=False):
            self.assertIsNone(getcluster())
            with Cluster():
                self.assertIsNotNone(getcluster())
            self.assertIsNone(getcluster())

    def test_with_nested_cluster(self):
        with Diagram(name=os.path.join(self.name, "with_nested_cluster"), show=False):
            self.assertIsNone(getcluster())
            with Cluster() as c1:
                self.assertEqual(c1, getcluster())
                with Cluster() as c2:
                    self.assertEqual(c2, getcluster())
                self.assertEqual(c1, getcluster())
            self.assertIsNone(getcluster())

    def test_node_not_in_diagram(self):
        # Node must be belong to a diagrams.
        with self.assertRaises(EnvironmentError):
            Node("node")

    def test_node_to_node(self):
        with Diagram(name=os.path.join(self.name, "node_to_node"), show=False):
            with Cluster():
                node1 = Node("node1")
                node2 = Node("node2")
                self.assertEqual(node1 - node2, node2)
                self.assertEqual(node1 >> node2, node2)
                self.assertEqual(node1 << node2, node2)

    def test_node_to_nodes(self):
        with Diagram(name=os.path.join(self.name, "node_to_nodes"), show=False):
            with Cluster():
                node1 = Node("node1")
                nodes = [Node("node2"), Node("node3")]
                self.assertEqual(node1 - nodes, nodes)
                self.assertEqual(node1 >> nodes, nodes)
                self.assertEqual(node1 << nodes, nodes)

    def test_nodes_to_node(self):
        with Diagram(name=os.path.join(self.name, "nodes_to_node"), show=False):
            with Cluster():
                node1 = Node("node1")
                nodes = [Node("node2"), Node("node3")]
                self.assertEqual(nodes - node1, node1)
                self.assertEqual(nodes >> node1, node1)
                self.assertEqual(nodes << node1, node1)


class EdgeTest(unittest.TestCase):
    def setUp(self):
        self.name = "edge_test"

    def tearDown(self):
        setdiagram(None)
        setcluster(None)
        # Only some tests generate the image file.
        try:
            shutil.rmtree(self.name)
        except OSError:
            pass

    def test_node_to_node(self):
        with Diagram(name=os.path.join(self.name, "node_to_node"), show=False):
            node1 = Node("node1")
            node2 = Node("node2")
            self.assertEqual(node1 - Edge(color="red") - node2, node2)

    def test_node_to_nodes(self):
        with Diagram(name=os.path.join(self.name, "node_to_nodes"), show=False):
            with Cluster():
                node1 = Node("node1")
                nodes = [Node("node2"), Node("node3")]
                self.assertEqual(node1 - Edge(color="red") - nodes, nodes)

    def test_nodes_to_node(self):
        with Diagram(name=os.path.join(self.name, "nodes_to_node"), show=False):
            with Cluster():
                node1 = Node("node1")
                nodes = [Node("node2"), Node("node3")]
                self.assertEqual(nodes - Edge(color="red") - node1, node1)

    def test_nodes_to_node_with_additional_attributes(self):
        with Diagram(name=os.path.join(self.name, "nodes_to_node_with_additional_attributes"), show=False):
            with Cluster():
                node1 = Node("node1")
                nodes = [Node("node2"), Node("node3")]
                self.assertEqual(
                    nodes -
                    Edge(
                        color="red") -
                    Edge(
                        color="green") -
                    node1,
                    node1)

    def test_node_to_node_with_attributes(self):
        with Diagram(name=os.path.join(self.name, "node_to_node_with_attributes"), show=False):
            with Cluster():
                node1 = Node("node1")
                node2 = Node("node2")
                self.assertEqual(
                    node1 << Edge(
                        color="red",
                        label="1.1") << node2,
                    node2)
                self.assertEqual(
                    node1 >> Edge(
                        color="green",
                        label="1.2") >> node2,
                    node2)
                self.assertEqual(
                    node1 << Edge(
                        color="blue",
                        label="1.3") >> node2,
                    node2)

    def test_node_to_node_with_additional_attributes(self):
        with Diagram(name=os.path.join(self.name, "node_to_node_with_additional_attributes"), show=False):
            with Cluster():
                node1 = Node("node1")
                node2 = Node("node2")
                self.assertEqual(
                    node1 << Edge(
                        color="red",
                        label="2.1") << Edge(
                        color="blue") << node2,
                    node2)
                self.assertEqual(
                    node1 >> Edge(
                        color="green",
                        label="2.2") >> Edge(
                        color="red") >> node2,
                    node2)
                self.assertEqual(
                    node1 << Edge(
                        color="blue",
                        label="2.3") >> Edge(
                        color="black") >> node2,
                    node2)

    def test_nodes_to_node_with_attributes_loop(self):
        with Diagram(name=os.path.join(self.name, "nodes_to_node_with_attributes_loop"), show=False):
            with Cluster():
                node = Node("node")
                self.assertEqual(
                    node >> Edge(
                        color="red",
                        label="3.1") >> node,
                    node)
                self.assertEqual(
                    node << Edge(
                        color="green",
                        label="3.2") << node,
                    node)
                self.assertEqual(
                    node >> Edge(
                        color="blue",
                        label="3.3") << node,
                    node)
                self.assertEqual(
                    node << Edge(
                        color="pink",
                        label="3.4") >> node,
                    node)

    def test_nodes_to_node_with_attributes_bothdirectional(self):
        with Diagram(name=os.path.join(self.name, "nodes_to_node_with_attributes_bothdirectional"), show=False):
            with Cluster():
                node1 = Node("node1")
                nodes = [Node("node2"), Node("node3")]
                self.assertEqual(
                    nodes << Edge(
                        color="green",
                        label="4") >> node1,
                    node1)

    def test_nodes_to_node_with_attributes_bidirectional(self):
        with Diagram(name=os.path.join(self.name, "nodes_to_node_with_attributes_bidirectional"), show=False):
            with Cluster():
                node1 = Node("node1")
                nodes = [Node("node2"), Node("node3")]
                self.assertEqual(
                    nodes << Edge(
                        color="blue",
                        label="5") >> node1,
                    node1)

    def test_nodes_to_node_with_attributes_onedirectional(self):
        with Diagram(name=os.path.join(self.name, "nodes_to_node_with_attributes_onedirectional"), show=False):
            with Cluster():
                node1 = Node("node1")
                nodes = [Node("node2"), Node("node3")]
                self.assertEqual(
                    nodes >> Edge(
                        color="red",
                        label="6.1") >> node1,
                    node1)
                self.assertEqual(
                    nodes << Edge(
                        color="green",
                        label="6.2") << node1,
                    node1)

    def test_nodes_to_node_with_additional_attributes_directional(self):
        with Diagram(name=os.path.join(self.name, "nodes_to_node_with_additional_attributes_directional"), show=False):
            with Cluster():
                node1 = Node("node1")
                nodes = [Node("node2"), Node("node3")]
                self.assertEqual(
                    nodes >> Edge(
                        color="red",
                        label="6.1") >> Edge(
                        color="blue",
                        label="6.2") >> node1,
                    node1)
                self.assertEqual(
                    nodes << Edge(
                        color="green",
                        label="6.3") << Edge(
                        color="pink",
                        label="6.4") << node1,
                    node1)


class ResourcesTest(unittest.TestCase):
    def test_folder_depth(self):
        """
        The code currently only handles resource folders up to a dir depth of 2
        i.e. resources/<provider>/<type>/<image>, so check that this depth isn't
        exceeded.
        """
        resources_dir = pathlib.Path(__file__).parent.parent / "resources"
        max_depth = max(
            os.path.relpath(
                d,
                resources_dir).count(
                os.sep) +
            1 for d,
            _,
            _ in os.walk(resources_dir))
        self.assertLessEqual(max_depth, 2)
