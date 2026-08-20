# Mojo / Modular Platform — source investigation

Investigation of the open-source Modular Platform repository, which hosts the
Mojo language and the MAX AI framework.

- Repo: `https://github.com/modular/modular` (Apache 2.0 with LLVM Exceptions)
- Clone inspected at `33cd4694` — *"[Release] Pin lockfiles to Mojo
  1.1.0.dev2026082005, MAX 26.6.0.dev2026082005"*, 2026-08-20
- Working tree: 341 MB, 10,549 tracked files
- Toolchain exercised: `pip install modular` → Mojo 1.0.0 (`ed45d567`), MAX 26.5.0

Everything below was checked against the source or run locally; nothing is from
memory. Where a claim could not be verified in this environment it says so.

---

## 1. What was actually just open-sourced

The headline event is precise and datable from the commit graph:

```
e41ef364 2026-08-18  Merge pull request #6904 from modular/mojo-oss
                     "Open source Mojo"
                     2,853 files changed, 561,408 insertions(+)
```

A binary search over first-parent history confirms the boundary: `40abdfb1`
(2026-08-17) has no `KGEN/` directory; `e41ef364` (2026-08-18) does. The
`modular/v25.7.0` tag (2025-11-20) has a top level of just
`bazel docs examples max mojo tools utils` — no compiler.

So the thing that is new is **the Mojo compiler itself**. The standard library
(2024-03) and the MAX kernel library (2025) were already open; this drop added
the closed half:

| Directory | What it is | Language |
|---|---|---|
| `KGEN/` | The Mojo compiler ("Kernel GENerator") | C++ / MLIR TableGen |
| `AsyncRT/` | Async runtime, work queues, `AsyncValue` | C++ |
| `Support/` | Shared C++ support library (incl. NIXL bits) | C++ |
| `Init/`, `Cache/`, `Config/` | Process init, compilation cache, config | C++ |

Note the compiler's *git history* goes back further than the drop (KGEN commits
exist from 2025-06 in the fetched window) — Modular exported monorepo history
along with the code rather than squashing it.

---

## 2. What language is Mojo implemented in?

**C++20, built on LLVM/MLIR.** Not Mojo, and not Python.

Compiler proper (`KGEN/lib` + `KGEN/include` + `KGEN/tools`):

| | Lines |
|---|---|
| `.cpp` | 201,716 |
| `.h` | 37,130 |
| `.td` (MLIR TableGen dialect/op definitions) | 22,532 |
| **Total C++ front + IR + backend** | **~261,000** |

Supporting C++ outside KGEN: `Support/` ~49k, `AsyncRT/` ~15k, `Cache/` ~3k.

`-std=c++20` is set in `bazel/internal/cc-toolchain/args/BUILD.bazel:157`.

The remaining `.mojo` under `KGEN/` is almost entirely tests: 88,684 lines
across 974 files in `KGEN/test/`, versus 18,851 lines of non-test Mojo. Plus
42,908 lines of `.mlir` FileCheck tests. The compiler is *not* self-hosted.

Python appears in the compiler only as tooling: `KGEN/tools/mblack` (82 files)
is a fork of Black that formats Mojo, which is what `mojo format` runs.

### Largest compiler source files

```
6,105  KGEN/lib/Compiler/ObjectCompiler/LLVM/Bitcode/21/BitcodeWriter21.cpp
5,837  KGEN/lib/KGENDialect/KGENAttrs.cpp
5,742  KGEN/lib/MojoParser/ExprNodes.cpp
5,514  KGEN/lib/LowerLIT/CheckLifetimes.cpp        <- the borrow checker
5,425  KGEN/lib/MojoParser/DeclResolution.cpp
4,408  KGEN/lib/MojoParser/ParserStmts.cpp
4,265  KGEN/lib/MojoParser/ClosureEmitter.cpp
3,190  KGEN/lib/Elaborator/Elaborator.cpp          <- monomorphization
```

`KGEN/lib/MojoParser/` alone is 59,130 lines across 39 `.cpp` files — the
single largest subsystem, which tracks with Mojo's Python-superset-ish surface
syntax plus full generics/traits inference.

---

## 3. What libraries does it use?

### The compiler's dependency is essentially "LLVM, and nothing else"

`bazel/public-patches/llvm_source.bzl` pins a raw LLVM commit:

```
LLVM_COMMIT = ec26997e2e4606d97918a4a082c4f93ca38a6f46
```

with five carried patches (an LLDB export fix, a MachineFunction API change, an
LLDB DAP console fix, an ELF extractor heap-corruption fix, and two Bazel config
reverts). LLVM is fetched as source and built from scratch — MLIR, LLVM codegen,
LLD and LLDB all come from that one pin.

Everything else in `bazel/common.MODULE.bazel` is ordinary C++ infrastructure:

`abseil-cpp`, `fmt` 11.2, `protobuf` 33.5, `grpc` 1.76, `opentelemetry-cpp`,
`curl`, `tcmalloc`, `xxhash`, `nlohmann_json`, `tomlplusplus`, `zlib-ng`,
`zstd`, `google_benchmark`, plus Bazel rulesets (`rules_cc`, `rules_python`,
`rules_mojo`, `rules_pycross`, `apple_support`).

Build system is **Bazel** (`bazelw` wrapper, `--config=build-mojo` to build the
compiler from source rather than downloading the prebuilt toolchain wheel).

### The Python/AI side's dependencies

`bazel/pip/requirements/pyproject.toml` is the pinned set. The load-bearing
runtime ones for MAX are:

- `numpy`, `transformers` (>=5.12,<5.13), `huggingface-hub`, `safetensors`,
  `tokenicer`/`tokenizers`, `gguf`, `sentencepiece`, `tiktoken` — model and
  tokenizer loading
- `fastapi`, `starlette`, `uvicorn`/`uvloop`, `sse-starlette`, `pyzmq`,
  `msgspec`, `pydantic` — the serving layer
- `llguidance` + a vendored copy of `xgrammar` — constrained/structured decoding
- `opentelemetry-*`, `prometheus-client` — telemetry
- `openai` — client-side compatibility and tests

**PyTorch is not a runtime dependency of MAX inference.** Across all 1,577
Python files in `max/python`, `import torch` appears exactly once, in
`pipelines/weights/quantize_checkpoint.py`. `torch`, `triton`, `vllm`,
`sglang`, `flashinfer`, `tilelang` are confined to dependency groups used for
benchmark baselines and comparison tests. That is a real architectural claim,
not marketing: the inference path is Python → MLIR → Mojo kernels, with no
framework underneath.

---

## 4. How the compiler actually works

`KGEN/docs/MojoCompilerWalkthrough.md` (1,408 lines) documents this, and the
structure matches the source tree.

**Mojo has no AST.** The parser emits MLIR operations directly. There are seven
Mojo-specific MLIR dialects — six defined by the 42 `.td` files under
`KGEN/include/`, plus `debuginfo` in `Support/`:

| Dialect | Role | Parametric? |
|---|---|---|
| `lit` | Source-level IR — what the parser emits | yes |
| `kgen` | Canonical Mojo IR, generators + params | yes → no |
| `pop` | Parametric SIMD / memory ops | yes → no |
| `hlcf` | Structured (high-level) control flow | no |
| `co` | Coroutines | no |
| `interp` | Compile-time interpreter ops and data | no |
| `debuginfo` | Debug information (lives in `Support/`) | no |

Upstream MLIR dialects (`index`, `llvm`, `nvvm`, `rocdl`) can appear at any
stage.

Pipeline:

1. **Parse / typecheck** — lazy three-phase parser (name resolution → signature
   resolution → body resolution), which is how Mojo avoids forward declarations.
   Emits `lit`.
2. **Semantic checking** — `LowerSemanticCF` → `CheckLifetimes` (the borrow
   checker) → `LowerLIT`. Output is `kgen`.
3. **Pre-elaboration opt** — SROA, mem2reg, parametric inlining, dead-param
   removal, to shrink the IR *before* monomorphizing.
4. **Elaboration** — `ElaborateGenerators` monomorphizes every generic and
   evaluates all compile-time code. Runs in parallel. This is the heart of the
   design.
5. **Post-elaboration opt** — calling conventions, SROA, mem2reg, SCCP,
   inlining, loop unrolling.
6. **Lower to LLVM** — `LowerKGENToLLVM` → `LowerPOPToLLVM` → LLVM IR → machine
   code, or NVPTX / AMDGCN / Metal for GPU targets.

The **compile-time interpreter** (`KGEN/lib/Interpreter/`) is what makes Mojo's
`comptime` work: it compiles functions to a `FunctionIRBytecode`, maintains an
emulated virtual address space for loads/stores, supports full control flow, and
deliberately requires no JIT so it works in environments that forbid one.

### Verified against real output

Compiling a trivial generic SIMD function with the installed toolchain and
dumping LLVM IR shows the monomorphized symbol carrying its full KGEN parameter
list, with `#kgen.instref` and `#interp.memref` attributes embedded in the
mangled name — exactly the elaboration/interpreter model the docs describe:

```llvm
%28 = fadd contract <4 x float> %27, splat (float 1.000000e+01)
call void @"std::io::io::print[...],Ts.values`=[[typevalue<#kgen.instref<
  \1B\22std::builtin::simd::SIMD,dtype=f32,length=4\22>>, simd<4, f32>]]"(...)
```

---

## 5. How the AI capabilities are implemented

Three layers, and the interesting part is where the boundary between them sits.

### Layer 1 — Kernels, written in Mojo (529,439 lines, 513 files in `max/kernels/src`)

This is where the actual AI math lives. Not C++, not CUDA C, not Triton — Mojo.

```
7.3M  src/nn/          attention (MHA/MLA), softmax, rope, moe, topk,
                       normalization, conv, sampling, kv_cache, ...
5.4M  src/linalg/      matmul (sm80/sm90/sm100, AMD CDNA/RDNA, Apple),
                       fp8/fp4/fp6/mxfp quantization, grouped matmul, lora
1.6M  src/layout/      TileTensor, swizzle, TMA async copy, tensor_core
1.4M  src/graph_compiler/  op registration + builtin kernels
688K  src/state_space/ Mamba-style SSM kernels
396K  src/comm/        collectives (allreduce, allgather)
400K  src/shmem/       expert-parallel comms
```

Vendor libraries are reachable but not required: `_cublas`, `_cublaslt`,
`_cudnn`, `_cufft`, `_rocblas`, `_miopen` are pure-Mojo FFI bindings
(`rocblas.mojo` alone is 46,220 lines) loaded via `std.ffi._find_dylib`.

**How Mojo reaches the metal**: user-level Mojo can embed MLIR directly.
Across the repo there are 639 `__mlir_op`, 755 `__mlir_attr`, and 842
`__mlir_type` uses, reaching these dialects from Mojo *source*:

```
270  pop.     87  index.   83  lit.    42  kgen.
 30  nvvm.    27  llvm.    24  builtin. 14 co.   6 rocdl.
```

So `wgmma` on Hopper is spelled as `#nvvm.wgmma_type<e4m3>` inside a Mojo
function, and `tcgen05` on Blackwell drops to `inlined_assembly` (18 sites).
There is no separate kernel DSL — the escape hatch is the compiler's own IR.

GPU host support lives in `max/mojo/max/gpu` (26,365 lines) with backends for
CUDA (`_nvidia_cuda.mojo`), HIP (`_amdgpu_hip.mojo`) and **Metal**
(`_metal.mojo`) — Apple GPUs are a first-class target.

### Layer 2 — The graph compiler (closed source)

Python builds an MLIR graph in Modular's `mo`/`rmo` dialects, then hands it to
`libmax.so`. Verified live:

```python
with Graph("add_mul", input_types=(ty, ty)) as g:
    a, b = g.inputs
    g.output(ops.relu(a * b + 1.0))
```

```mlir
mo.graph @add_mul(%arg0: !mo.tensor<[2, 3], f32>, ...) {
  %1 = rmo.mul(%arg0, %arg1) : ...
  %2 = mo.constant {value = #M.dense_array<1.000000e+00> : tensor<f32>} : ...
  %3 = rmo.add(%1, %2) : ...
  %4 = rmo.mo.relu(%3) : ...
  mo.output %4 : !mo.tensor<[2, 3], f32>
}
```
→ executes and returns `[[0,0,0],[1,3,5]]` on CPU.

`max/graph/graph.py` imports `Attribute`, `Block`, `OpBuilder`, `Operation`
from `max._core` and dialects `mo`, `kgen`, `m`, `builtin` — nanobind bindings
into a compiled extension.

### Layer 3 — Python model + serving code (391,085 lines in `max/python`)

```
228,627  pipelines/   94 model architectures + kv-cache, sampling, speculative
                      decoding, LoRA, diffusion, request handling
 36,265  nn/          layers built on the graph API
 21,860  serve/       OpenAI-compatible server (FastAPI + SSE + zmq workers)
 20,476  graph/       the graph-staging API, 70 op modules
```

Architectures include DeepSeek V2/V3/V3.2, Llama 3/4, Qwen 2/2.5-VL/3/3-VL-MoE,
Gemma 3/4, GPT-OSS, Mistral/Pixtral, InternVL, Whisper, Flux, Mamba, BERT/T5,
and a lot of speculative-decoding variants (Eagle, MTP, DFlash).

### The glue: `@extensibility.register`

A Mojo function becomes a graph op by decoration. Built-ins use
`@register_internal("mo.add")`; user kernels use `@extensibility.register`, and
`Graph(..., custom_extensions=[path])` precompiles the directory to a `.mojoc`
package and links it into the graph.

**Verified end-to-end locally** — a Mojo kernel with `comptime if target ==
"cpu"` / `"gpu"` specialization, compiled by KGEN and executed through MAX:

```
Graph result:    [1.5227834 1.0788828 0.57447207 ...]
Expected result: [1.5227834 1.0788828 0.57447207 ...]
```

---

## 6. What is still *not* open

This matters, and the README's "Mojo compiler: /KGEN" understates it.

**Downloaded as prebuilt binaries** (`bazel/modular_wheel_repository.bzl`
fetches `max_core` and `mojo_compiler` wheels and moves `.so` files into place):

- `max/_core.*.so` — the Python↔MLIR nanobind layer. `max/python/max/_core/`
  contains 27 `.pyi` stubs and **no implementation**; `max/python/max/_core/internal/`
  is referenced by BUILD files but does not exist in the repo.
- `libmax.so` — the MAX graph compiler and inference runtime
- `libMGPRT`, `libNVPTX.so`, `libnixl.so`, `libAsyncRTMojoBindings`,
  `libKGENCompilerRTShared`

**Closed Mojo kernel packages** shipped as precompiled `.mojoc`
(`bazel/mojo_aliases.bzl` → `INTERNAL_PACKAGES`):

```
//Kernels/lib/attn_res      //Kernels/lib/matmul_rs   //Kernels/lib/msa
//Kernels/src/mega_ffn      //max/internal/driver/src/_hal
//max/internal/driver/src/machine
```

The pattern is visible in the open shims — `builtin_kernels/attn_res.mojo` says
outright: *"The kernel lives in `//Kernels/lib/attn_res` (`attn_res.mix`); only
the `@extensibility.register` wrapper lives here."* Some of the newest
attention kernels are registered openly and implemented privately.

**Licensing is two-tier**: the repo is Apache 2.0 w/ LLVM Exceptions, but the
shipped wheel declares `LicenseRef-MAX-Platform-Software-License`, and the
README states MAX usage and distribution fall under the Modular Community
License. Contributions are accepted to the stdlib, kernels, and model
architectures — *not* to the compiler.

---

## 7. So what do we actually have here?

A real compiler, honestly complete for what it claims to be. `KGEN/` contains
the lexer, the three-phase parser, the type checker, the borrow checker, the
monomorphizer, the compile-time interpreter, seven MLIR dialects, the LLVM
lowering, the LSP server, the LLDB plugin, the REPL, the package format, and a
974-file test suite. Combined with the already-open 119,091-line standard
library, you could read it end to end and understand exactly how Mojo works.
The docs shipped with it (`KGEN/docs/`, including an `arcana/` directory on
witness elaboration, conformance, thunks, and closures) are written for
compiler engineers, not for marketing.

What you cannot do is build the AI stack from source. The compiler is open;
the *graph compiler* — the thing that decides how a model's ops get fused,
scheduled, and dispatched to those kernels — is a binary blob. MAX's kernels
are open and its model definitions are open, so you can see every individual
piece of arithmetic, but the optimizer that stitches them into a fast inference
engine is not here. A fully self-hosted, from-source MAX is not on the table
with this drop.

Two honest caveats on this investigation:

- **I did not build the compiler.** `--config=build-mojo` requires compiling
  LLVM+MLIR from source under Bazel; that is hours of work and disk this
  container does not have. The runtime behavior above was verified with the
  official prebuilt toolchain instead.
- **Version skew**: the repo HEAD targets Mojo 1.1.0.dev / MAX 26.6.0.dev while
  `pip install modular` gave Mojo 1.0.0 / MAX 26.5.0. Repo examples using the
  nightly-renamed `@__parameter` decorator fail on the release compiler; I
  patched it to `@parameter` to run the custom-op example.

### Language notes worth flagging

Mojo 1.0.0 shipped 2026-08-11, nine days before this snapshot, and it moved a
lot:

- `fn` is deprecated — `def` is the one function keyword
- `alias` → `comptime`; `@parameter if/for` → `comptime if/for`
- `Pointer` and `UnsafePointer` unified; unsafety marked per-operation, and
  pointers are non-null by design (`Optional[Pointer[...]]` uses the null niche)
- *Interior origins*: the lifetime checker now tracks references into container
  interiors, so holding an element reference across a mutation is rejected
- `InlineArray`→`Array`, `StringSlice`→`StringSpan`, `size`→`length`,
  `read`→`imm`, `Int` is now `Scalar[DType.int]`
- Bounds checking on by default on CPU; negative indexing removed entirely
- Nightly adds `where` clauses on `thin` function types

That last cluster is the tell: this is a language doing pre-1.0 cleanup work
*at* 1.0, with compiler fix-its for nearly every break.
