# Data Structures: Trees and Graphs

## Binary Trees

A binary tree is a hierarchical data structure where each node has at most two children.

### Properties
- Height: longest path from root to a leaf
- Balanced: height difference between subtrees is at most 1
- Complete: all levels filled except possibly the last

### Binary Search Tree (BST)
- Left child < parent < right child
- Search: O(log n) average, O(n) worst case
- Insert: O(log n) average
- Delete: O(log n) average

### Traversals
- In-order (left, root, right): produces sorted output for BST
- Pre-order (root, left, right): useful for tree copying
- Post-order (left, right, root): useful for deletion
- Level-order (BFS): uses a queue

## Graphs

A graph G = (V, E) consists of vertices V and edges E connecting them.

### Types
- Directed vs undirected
- Weighted vs unweighted
- Cyclic vs acyclic (DAG = Directed Acyclic Graph)

### Representations
- Adjacency matrix: O(V²) space, O(1) edge lookup
- Adjacency list: O(V + E) space, O(degree) edge lookup

### Key Algorithms
- BFS (Breadth-First Search): shortest path in unweighted graphs, O(V + E)
- DFS (Depth-First Search): topological sort, cycle detection, O(V + E)
- Dijkstra's algorithm: shortest path in weighted graphs, O((V + E) log V)
- Bellman-Ford: handles negative weights, O(V * E)
- Kruskal's / Prim's: minimum spanning tree
