# Allocation trial extension

Single allocator chooses a nonnegative vector summing to `budget` to minimize
squared distance to `target`. The scripted primary action `[5,5]` is preserved;
`AllocationSolver` computes the separate analytic single-actor optimum via
water-filling projection onto the simplex (general budgets/targets/dims>=2).
It is a single-actor optimum, not a multiplayer equilibrium. Numerical searches
are qualified; this solver carries an analytic model-specific justification
(KKT water-filling for squared distance with simplex constraints).
