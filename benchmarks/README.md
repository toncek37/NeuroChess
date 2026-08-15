# Benchmarks

`neurochess_search_benchmark` compares the unoptimized alpha-beta baseline with the current optimized search at a fixed depth over a small deterministic position suite.

It reports best move, score, nodes, elapsed time, null-move cutoffs and LMR reductions. At this project stage it is a **search-efficiency/regression benchmark**, not an Elo estimator. Playing-strength tests against external UCI engines are introduced in Prompts 10–12.

Build and run:

```bash
cmake -S . -B build -DNEUROCHESS_BUILD_BENCHMARKS=ON
cmake --build build
./build/neurochess_search_benchmark
```
