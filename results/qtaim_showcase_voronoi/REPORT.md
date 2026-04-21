# First-pass QTAIM vs Voronoi / powerfit showcase results

Key numerical findings:
- Projected BCP fractions are usable connector observables on the current showcase: max off-axis distance is below 0.004 A for every system.
- Ordinary Voronoi strongly overconnects at the raw graph level.
- Using `intersection_inside` as a visibility mask exactly recovers the QTAIM BCP graph for CO2, methane, ethane, and both benzenes.
- The same visibility mask is not sufficient for the cage case: adamantane still shows visible H...H extras.
- However, the Voronoi face clearance diagnostic `intersection_edge_min_dist` cleanly separates the adamantane extras from true QTAIM edges in the current showcase. A threshold around 0.5 A yields perfect graph recovery for all current systems.
- One-shot powerfit matches the projected BCP fractions essentially exactly, and all requested QTAIM pairs are realized, but it does not by itself remove candidate-absent extra faces in the raw graph.

Interpretation for the manuscript:
- Do not sell powerfit here as a graph-topology miracle.
- Sell the comparison as: raw Voronoi overconnects; representability-aware masking explains much of the graph disagreement; powerfit is needed to correct separator geometry.
- The clearance diagnostic is promising, but on this tiny curated pack it should be presented as a hypothesis / diagnostic, not as a universal law.
