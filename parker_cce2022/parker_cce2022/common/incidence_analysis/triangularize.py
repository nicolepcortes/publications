#  ___________________________________________________________________________
#
#  Pyomo: Python Optimization Modeling Objects
#  Copyright 2017 National Technology and Engineering Solutions of Sandia, LLC
#  Under the terms of Contract DE-NA0003525 with National Technology and 
#  Engineering Solutions of Sandia, LLC, the U.S. Government retains certain 
#  rights in this software.
#  This software is distributed under the 3-clause BSD License.
#  ___________________________________________________________________________

from pyomo.contrib.incidence_analysis.matching import maximum_matching
from pyomo.common.dependencies import networkx as nx


def block_triangularize(matrix, matching=None):
    """
    Computes the necessary information to permute a matrix to block-lower
    triangular form, i.e. a partition of rows and columns into an ordered
    set of diagonal blocks in such a permutation.

    Arguments
    ---------
    matrix: A SciPy sparse matrix
    matching: A perfect matching of rows and columns, in the form of a dict
              mapping row indices to column indices

    Returns
    -------
    Two dicts. The first maps each row index to the index of its block in a
    block-lower triangular permutation of the matrix. The second maps each
    column index to the index of its block in a block-lower triangular
    permutation of the matrix.
    """
    nxb = nx.algorithms.bipartite
    nxc = nx.algorithms.components
    nxd = nx.algorithms.dag
    from_biadjacency_matrix = nxb.matrix.from_biadjacency_matrix

    M, N = matrix.shape
    if M != N:
        raise ValueError("block_triangularize does not currently "
           "support non-square matrices. Got matrix with shape %s."
           % (matrix.shape,)
           )
    bg = from_biadjacency_matrix(matrix)

    if matching is None:
        matching = maximum_matching(matrix)

    len_matching = len(matching)
    if len_matching != M:
        raise ValueError("block_triangularize only supports matrices "
                "that have a perfect matching of rows and columns. "
                "Cardinality of maximal matching is %s" % len_matching
                )

    # Construct directed graph of rows
    dg = nx.DiGraph()
    dg.add_nodes_from(range(M))
    for n in dg.nodes:
        col_idx = matching[n]
        col_node = col_idx + M
        # For all rows that share this column
        for neighbor in bg[col_node]:
            if neighbor != n:
                # Add an edge towards this column's matched row
                dg.add_edge(neighbor, n)

    # Partition the rows into strongly connected components (diagonal blocks)
    scc_list = list(nxc.strongly_connected_components(dg))
    node_scc_map = {n: idx for idx, scc in enumerate(scc_list) for n in scc}

    # Now we need to put the SCCs in the right order. We do this by performing
    # a topological sort on the DAG of SCCs.
    dag = nx.DiGraph()
    for i, c in enumerate(scc_list):
        dag.add_node(i)
    for n in dg.nodes:
        source_scc = node_scc_map[n]
        for neighbor in dg[n]:
            # directed graph of constraints
            target_scc = node_scc_map[neighbor]
            if target_scc != source_scc:
                dag.add_edge(target_scc, source_scc)
                # Reverse direction of edge. This corresponds to creating
                # a block lower triangular matrix.

    # Indices into the SCC list, permuted into a topological order
    scc_order = list(nxd.topological_sort(dag))

    # c is the index into the list of SCCs
    # i is where it belongs in the order
    scc_block_map = {c: i for i, c in enumerate(scc_order)}
    row_block_map = {n: scc_block_map[c] for n, c in node_scc_map.items()}
    # ^ This maps row indices to the blocks they belong to.

    # I now want a DAG of diagonal blocks
    dag_ll = [
            [scc_block_map[j] for j in dag[i]]
            for i in scc_order
            ]

    # Invert the matching to map row indices to column indices
    col_row_map = {c: r for r, c in matching.items()}
    assert len(col_row_map) == M

    col_block_map = {c: row_block_map[col_row_map[c]] for c in range(N)}

    return row_block_map, col_block_map, dag_ll
