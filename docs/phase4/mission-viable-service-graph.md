# Phase 4 Mission-Viable Service Graph

## Scope and safety boundary

Phase 4 implements the synthetic, nonclinical Mission-Viable Service Graph (MVSG) mechanism
approved in the Phase 0 v1.1 design. It selects the smallest declared service graph that preserves
mandatory mission capabilities under current authority, freshness, locality, resource, deadline,
ordering, exclusion, and redundancy constraints.

The optimizer does not invent mission priorities, diagnose patients, control medical equipment,
or by itself establish hypothesis H5. Phase 8 subsequently compared mission utility per declared
energy/compute unit against the frozen B6 static-priority baseline using repeated paired experiments.

## Constraint model

For service selection variable `z_i` and placement variable `y_i,s`:

- exactly one placement is selected when a service is selected;
- AND dependency: `z_i <= z_j`;
- OR group: `z_i <= sum(z_j for j in alternatives)`;
- mutual exclusion: `z_i + z_j <= 1`;
- redundancy: selected members and, where declared, distinct occupied sites meet the threshold;
- mandatory capability coverage meets its declared unit requirement;
- per-site resource demand and aggregate authority budgets are never exceeded;
- selected services remain inside the authority envelope's action, resource, site, impact,
  approval, security, confidence, freshness, and exact MVSG-hash constraints;
- selected startup dependencies precede their consumers; and
- declared capability and end-to-end latency deadlines are hard constraints.

The deterministic CP-SAT solver runs with one search worker and a recorded seed. Its
lexicographic objective is:

1. satisfy all hard mandatory constraints;
2. minimize selected service count;
3. minimize integer-scaled resource cost, authority exposure, and declared starvation penalty;
4. maximize optional mission utility.

## Independent validation

OR-Tools is not trusted to authorize its own result. `PlanValidator` does not import optimizer
internals or OR-Tools. It recomputes every hard constraint, the startup relation, graph/context
hashes, and the complete objective. Its validation certificate binds the graph, context,
placements, startup order, objective values, validator version, and explicit checks.

The certificate is deterministic evidence for later inclusion by hash in Phase 3 decision
certificates. It is not a new cryptographic proof or proof of application correctness.

## Timeout and infeasibility behavior

A solver result can run only after independent validation. On a timeout:

1. use a validated incumbent if one exists;
2. otherwise rebind and independently revalidate the previous graph under the new context;
3. otherwise return `SAFE_SHUTDOWN`.

Infeasibility, stale mandatory data, missing authority, insufficient confidence, invalid
redundancy, budget exhaustion, or a rejected incumbent cannot be converted into availability by
relaxing a hard constraint.

## Acceptance evidence

The Phase 4 gate requires full tests and branch-aware coverage at or above 90%; strict linting and
typing; CP-SAT agreement with a brute-force subset/placement oracle; byte-identical frozen vector
regeneration; timeout and negative safety tests; raw benchmark samples; provenance; SBOM;
dependency audit; source manifest; evidence manifest; and matching local/CI archives tied to one
clean source commit.

Automated success remains `CONDITIONAL_PASS`; it cannot complete Phase 4 or authorize Phase 5.
Independent review recorded Phase 4 `PASS` at source commit
`6fb314effdc5e45145593bbdd582e19f60914d5f`.

## Known limitations

- CP-SAT establishes bounded-instance optimization, not universal optimality.
- The brute-force oracle is restricted to small graphs.
- Resource and energy quantities are declared integer models, not measured joules.
- The hospital graph is an engineering fixture, not a clinical model.
- Validator compromise, incorrect declared mission priorities, and false sensor evidence remain
  outside this mechanism's guarantee.
- Phase 4 evidence alone does not establish the identity/time/policy, causal recovery,
  orchestration, or experimental claims that were implemented and reviewed in later phases.
