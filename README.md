# Life Itself

**Life Itself** is the game and product. **Simulated Reality Engine (SRE)** is its technical engine name: a persistent, systemic open-world life simulation where people remember, forget, talk, react, build reputations, experience trauma, navigate justice, and make deals. The long-term ambition is a grounded, reactive open world with the freedom and systemic depth of a real-life crime sandbox, while keeping everyday life—not just crime—at the centre.

## Development status

The Python reference layer contains a broad set of engine-independent simulation systems. The portable C++20 implementation provides a smaller native core. Unreal Engine presentation and runtime integration are not implemented. The React/Vite application in this branch is an application foundation and does not yet connect to a live simulation runtime or Supabase-backed player accounts.

See [the production implementation status](docs/PRODUCTION-IMPLEMENTATION-STATUS.md) for the explicit boundary between existing systems and remaining work.

## Running the application

Requirements: Node.js 22+ and npm.

```sh
npm install
npm run dev
```

Create a production build:

```sh
npm run build
npm run preview
```

The web application is a React 18 + TypeScript + Vite browser application. Its simulation-facing contracts are defined in `src/types/domain-contracts.ts`. A runtime adapter must implement `SimulationRuntimePort` before the UI can display authoritative world state or issue simulation commands.

## Running the Python reference engine

```sh
python -m pip install pytest
python -m pytest -q
```

Python 3.10+ is required.

## Running the portable C++ core

```sh
cmake -S cpp -B build
cmake --build build
ctest --test-dir build --output-on-failure
```

C++20 and CMake 3.20+ are required.

## Product and technical naming

- **Product/game:** Life Itself
- **Engine / code name:** Simulated Reality Engine (SRE)
- **Python package and C++ namespace:** `simreality`
- **Repository:** `michaelkage/Life-Itself`

## Architecture

The Python reference and C++ core remain engine-independent. Unreal integration is intended to consume immutable snapshots and submit validated commands through an adapter; Unreal object references must not leak into simulation domain modules. The browser application uses the same versioned boundary concept and must not invent live state when its runtime is disconnected.


## Simulation API connection

The browser application can connect to a separately hosted simulation API by setting `VITE_SIMULATION_API_URL`. The validated HTTP/SSE adapter and endpoint contract are documented in [docs/SIMULATION-HTTP-API.md](docs/SIMULATION-HTTP-API.md). The API server and Unreal bridge are not included in this frontend foundation.
