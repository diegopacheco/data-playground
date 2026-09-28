import csv
import json
import os
import unittest
import urllib.error
import urllib.request
from collections import defaultdict, deque
from pathlib import Path

DATA = Path(os.environ.get("DATA_DIR", "/data"))
UI = os.environ.get("UI_URL", "http://localhost:8080")
MAX_HOPS = 6


def rows(name):
    with open(DATA / name) as f:
        return [{k: int(v) if v.lstrip("-").isdigit() else v for k, v in r.items()} for r in csv.DictReader(f)]


def get(path):
    with urllib.request.urlopen(UI + path, timeout=60) as r:
        return json.loads(r.read())


def bfs(adjacency, source, limit):
    dist, queue = {source: 0}, deque([source])
    while queue:
        node = queue.popleft()
        if dist[node] == limit:
            continue
        for nxt in adjacency[node]:
            if nxt not in dist:
                dist[nxt] = dist[node] + 1
                queue.append(nxt)
    dist.pop(source)
    return dist


class GraphQueries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.customers = rows("customers.csv")
        cls.products = {p["product_id"]: p for p in rows("products.csv")}
        cls.follows = {(f["follower_id"], f["followed_id"]) for f in rows("follows.csv")}
        cls.orders = rows("orders.csv")
        cls.adjacency = defaultdict(set)
        for a, b in cls.follows:
            cls.adjacency[a].add(b)
        cls.bought = defaultdict(lambda: [0, 0])
        for o in cls.orders:
            cls.bought[(o["customer_id"], o["product_id"])][0] += 1
            cls.bought[(o["customer_id"], o["product_id"])][1] += o["quantity"]
        cls.buyers = defaultdict(set)
        for c, p in cls.bought:
            cls.buyers[p].add(c)
        cls.ids = [c["customer_id"] for c in cls.customers]

    def test_sql_tables_hold_every_csv_row(self):
        tables = get("/api/stats")["tables"]
        self.assertEqual(tables, {"customers": len(self.customers), "products": len(self.products),
                                  "follows": len(self.follows), "orders": len(self.orders)})

    def test_graph_has_a_vertex_per_customer_and_product_and_one_bought_edge_per_distinct_pair(self):
        stats = get("/api/stats")
        self.assertEqual(stats["nodes"], {"Customer": len(self.customers), "Product": len(self.products)})
        self.assertEqual(stats["edges"], {"FOLLOWS": len(self.follows), "BOUGHT": len(self.bought)})
        self.assertLess(len(self.bought), len(self.orders), "repeat purchases must collapse into one BOUGHT edge")

    def test_graph_endpoint_edges_and_properties_match_the_csv_files(self):
        g = get("/api/graph")
        follows = {(int(e["from"][1:]), int(e["to"][1:])) for e in g["edges"] if e["type"] == "FOLLOWS"}
        self.assertEqual(follows, self.follows)
        bought = {(int(e["from"][1:]), int(e["to"][1:])): [e["orders"], e["quantity"]] for e in g["edges"] if e["type"] == "BOUGHT"}
        self.assertEqual(bought, dict(self.bought))
        self.assertEqual(len(g["nodes"]), len(self.customers) + len(self.products))

    def test_k_hop_reach_and_hop_count_match_a_breadth_first_search_for_every_customer(self):
        for cid in self.ids:
            for k in (1, 2, 3):
                expected = bfs(self.adjacency, cid, k)
                got = {r["id"]: r["hops"] for r in get(f"/api/khop?customer={cid}&k={k}")["reached"]}
                self.assertEqual(got, expected, f"customer {cid} k={k}")

    def test_shortest_path_is_as_short_as_bfs_and_walks_only_real_follows_edges(self):
        checked_unreachable = 0
        for source in self.ids[:10]:
            dist = bfs(self.adjacency, source, MAX_HOPS)
            for target in self.ids:
                if target == source:
                    continue
                r = get(f"/api/path?from={source}&to={target}")
                if target not in dist:
                    self.assertIsNone(r["path"], f"{source}->{target} has no path within {MAX_HOPS} hops")
                    checked_unreachable += 1
                    continue
                path = r["path"]
                self.assertEqual(r["hops"], dist[target], f"{source}->{target} is not the shortest")
                self.assertEqual(len(path), dist[target] + 1)
                self.assertEqual((path[0], path[-1]), (source, target))
                for a, b in zip(path, path[1:]):
                    self.assertIn((a, b), self.follows, f"{source}->{target} uses a missing edge {a}->{b}")
        self.assertGreater(checked_unreachable, 0, "the data should include unreachable pairs so the null case is exercised")

    def test_customers_who_bought_x_also_bought_matches_co_purchase_counts_for_every_product(self):
        for pid in self.products:
            counts = defaultdict(int)
            for c in self.buyers[pid]:
                for other in self.products:
                    if other != pid and c in self.buyers[other]:
                        counts[other] += 1
            expected = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
            r = get(f"/api/recommend?product={pid}")
            self.assertEqual(r["buyers"], sorted(self.buyers[pid]))
            self.assertEqual([(x["id"], x["buyers"]) for x in r["also_bought"]], expected, f"product {pid}")

    def test_network_spend_joins_cypher_reach_with_sql_orders(self):
        for cid in self.ids:
            reach = set(bfs(self.adjacency, cid, 2))
            spend = defaultdict(lambda: [set(), 0, 0])
            for o in self.orders:
                if o["customer_id"] in reach:
                    s = spend[self.products[o["product_id"]]["category"]]
                    s[0].add(o["customer_id"])
                    s[1] += 1
                    s[2] += o["quantity"] * o["price_cents"]
            expected = sorted(([c, len(s[0]), s[1], s[2]] for c, s in spend.items()), key=lambda r: (-r[3], r[0]))
            mine = {p for c, p in self.bought if c == cid}
            picks = defaultdict(set)
            for c, p in self.bought:
                if c in reach and p not in mine:
                    picks[p].add(c)
            expected_picks = sorted(((p, len(cs)) for p, cs in picks.items()), key=lambda kv: (-kv[1], kv[0]))[:5]
            r = get(f"/api/network?customer={cid}&k=2")
            self.assertEqual([[s["category"], s["customers"], s["order_lines"], s["revenue_cents"]] for s in r["spend"]], expected, f"customer {cid}")
            self.assertEqual([(p["id"], p["buyers"]) for p in r["picks"]], expected_picks, f"customer {cid}")

    def test_invalid_parameters_are_rejected_before_reaching_cypher(self):
        for path in ("/api/khop?customer=1&k=9", "/api/path?from=1&to=x", "/api/recommend?product=1%27%20OR%201"):
            with self.assertRaises(urllib.error.HTTPError) as e:
                get(path)
            self.assertEqual(e.exception.code, 400)
            e.exception.close()

    def test_ui_page_has_every_tab(self):
        with urllib.request.urlopen(UI + "/", timeout=30) as r:
            html = r.read().decode()
        for tab in ("Graph", "K-hop", "Shortest path", "Also bought", "Cypher + SQL"):
            self.assertIn(f">{tab}<", html)


if __name__ == "__main__":
    unittest.main()
