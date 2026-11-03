"""
CWMS FastAPI Backend.
Provides REST API for simulation control, monitoring, and results.
"""
from contextlib import asynccontextmanager
from typing import List, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator
import uvicorn
import asyncio
import hmac
import logging
import os
from pathlib import Path

from cwms_simulator import (
    CWMSimulator,
    SimulationConfig,
    SimulationResult,
    NodeState,
    PolicyFactory,
    WorkloadForecaster,
)
from cwms_simulator.nodes import create_default_nodes
from cwms_simulator.storage import ResultsStore

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "cwms_data" / "cwms.db"
MAX_TOTAL_REQUESTS = 100_000
MAX_REQUEST_BYTES = 32_768
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
logger = logging.getLogger("cwms_api")


# Global state for API
class SimulatorState:
    def __init__(self):
        self.simulator: Optional[CWMSimulator] = None
        self.result: Optional[SimulationResult] = None
        self.running = False
        self.current_interval = 0
        self.total_intervals = 0
        self.policy = "-"
        self.label = "custom"
        self.run_id: Optional[int] = None
        self.error: Optional[str] = None
        self.health_overrides: dict[str, bool] = {}

simulator_state = SimulatorState()
results_store = ResultsStore(os.environ.get("CWMS_DB_PATH", str(DEFAULT_DB_PATH)))


def _api_token() -> str:
    """Return the configured bearer token, or an empty string when disabled."""
    return os.environ.get("CWMS_API_TOKEN", "").strip()


async def require_api_token(authorization: Optional[str] = Header(default=None)) -> None:
    """Require a bearer token for state-changing endpoints when configured."""
    expected = _api_token()
    if not expected:
        return
    scheme, _, presented = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(presented.strip(), expected):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )


class BodyTooLarge(Exception):
    """Raised internally when a request body exceeds the configured limit."""


class RequestBodyLimitMiddleware:
    """Reject oversized request bodies, including chunked uploads."""

    def __init__(self, app, max_bytes: int = MAX_REQUEST_BYTES):
        self.app = app
        self.max_bytes = max_bytes

    @staticmethod
    async def _reject(send) -> None:
        body = b'{"detail":"Request body too large"}'
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        })
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        raw_length = headers.get(b"content-length")
        if raw_length is not None:
            try:
                if int(raw_length) > self.max_bytes:
                    await self._reject(send)
                    return
            except ValueError:
                await self._reject(send)
                return

        received = 0
        response_started = False

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise BodyTooLarge
            return message

        async def tracking_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except BodyTooLarge:
            if not response_started:
                await self._reject(send)


def _cors_origins() -> List[str]:
    """Read an explicit comma-separated CORS allowlist from the environment."""
    raw = os.environ.get("CWMS_CORS_ORIGINS", "")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def _validate_bind_host(host: str) -> None:
    """Refuse accidental unauthenticated exposure beyond loopback."""
    if host in LOOPBACK_HOSTS:
        return
    allow = os.environ.get("CWMS_ALLOW_UNAUTHENTICATED_REMOTE", "").lower()
    if _api_token() or allow in {"1", "true", "yes"}:
        return
    raise RuntimeError(
        "Refusing to bind to a non-loopback address without CWMS_API_TOKEN. "
        "Set a token or CWMS_ALLOW_UNAUTHENTICATED_REMOTE=1 for an isolated demo."
    )


def _prepare_simulator(config: SimulationConfig, label: str) -> CWMSimulator:
    """
    Build and initialize a simulator before exposing it through the API.

    Initializing synchronously closes the window where a status request could
    arrive while the simulator components are still unset. Manual health
    overrides are applied, then the configured failed node is forced unhealthy
    so a scenario's failure cannot be undone by an older override.
    """
    simulator = CWMSimulator(config)
    simulator.initialize()

    for name, healthy in simulator_state.health_overrides.items():
        node = next((n for n in simulator.nodes if n.name == name), None)
        if node is not None:
            node.set_health(NodeState.HEALTHY if healthy else NodeState.UNHEALTHY)
    if config.fail_node:
        for node in simulator.nodes:
            if node.name == config.fail_node:
                node.set_health(NodeState.UNHEALTHY)

    simulator_state.simulator = simulator
    simulator_state.total_intervals = config.intervals
    simulator_state.current_interval = 0
    simulator_state.policy = config.policy
    simulator_state.label = label
    simulator_state.run_id = None
    simulator_state.error = None
    simulator_state.result = None
    return simulator


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    yield
    # Shutdown


app = FastAPI(
    title="CWMS API",
    description="Cloud Workload Management System - REST API for simulation and monitoring",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(RequestBodyLimitMiddleware, max_bytes=MAX_REQUEST_BYTES)

# Cross-origin access is opt-in. The dashboard is served from this origin.
_configured_cors_origins = _cors_origins()
if _configured_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_configured_cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )


@app.middleware("http")
async def add_security_headers(request, call_next):
    """Add conservative browser security headers to every response."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response

# Mount static files for dashboard
dashboard_path = Path(__file__).parent.parent / "cwms_dashboard"
if dashboard_path.exists():
    app.mount("/static", StaticFiles(directory=str(dashboard_path)), name="static")


# Pydantic models for API
class SimulationConfigRequest(BaseModel):
    policy: str = Field(default="least-loaded", pattern="^(round-robin|least-loaded|fcfs|adaptive)$")
    intervals: int = Field(default=20, ge=1, le=200)
    base_rate: int = Field(default=40, ge=1, le=1000)
    burst_rate: int = Field(default=140, ge=1, le=1000)
    burst_start: int = Field(default=8, ge=0)
    burst_end: int = Field(default=13, ge=0)
    surge_threshold: int = Field(default=90, ge=1)
    load_threshold: float = Field(default=80.0, ge=0.0, le=150.0)
    max_load_threshold: float = Field(default=100.0, ge=0.0, le=300.0)
    fail_node: Optional[str] = Field(default=None, pattern="^(backend-a|backend-b|backend-c)$")
    forecast_window: int = Field(default=5, ge=1, le=50)
    forecast_strategy: str = Field(
        default="change_aware", pattern="^(moving_average|change_aware)$"
    )
    admission_control: bool = True
    overload_threshold: float = Field(default=100.0, ge=0.0, le=150.0)
    queue_limit: int = Field(default=50, ge=0, le=1000)
    request_timeout_ms: float = Field(default=2000.0, gt=0.0, le=600_000.0)
    seed: int = Field(default=7, ge=0)

    @model_validator(mode="after")
    def validate_total_volume(self):
        """Bound worst-case generated requests to protect the shared server."""
        peak_rate = max(self.base_rate, self.burst_rate)
        if self.intervals * peak_rate > MAX_TOTAL_REQUESTS:
            raise ValueError(
                f"intervals * max(base_rate, burst_rate) must be <= {MAX_TOTAL_REQUESTS}"
            )
        return self


class NodeStatus(BaseModel):
    name: str
    capacity: float
    load: float
    healthy: bool
    state: str
    assigned: int
    available_capacity: float
    overload_threshold: float = 100.0
    queue_limit: int = 50
    queued_current: int = 0
    queued_total: int = 0
    queue_overflow_total: int = 0
    max_queue_depth: int = 0


class SystemStatus(BaseModel):
    interval: int
    total_intervals: int
    running: bool
    policy: str
    requests_generated: int
    requests_assigned: int
    requests_rejected: int
    requests_completed: int = 0
    requests_failed: int = 0
    requests_queued: int = 0
    requests_timed_out: int = 0
    requests_rejected_overload: int = 0
    requests_rejected_no_capacity: int = 0
    surge_detected: bool
    forecast: float
    recommendation: str
    nodes: List[NodeStatus]
    error: Optional[str] = None
    run_id: Optional[int] = None
    label: str = "custom"


class SimulationSummary(BaseModel):
    config: dict
    system_metrics: dict
    node_metrics: List[dict]
    surge_events: List[dict]
    forecast_accuracy: dict
    final_recommendation: Optional[dict]


class ScenarioRequest(BaseModel):
    scenario: str = Field(pattern="^(normal|burst|failure|overload)$")
    policy: str = Field(default="least-loaded", pattern="^(round-robin|least-loaded|fcfs|adaptive)$")


class PruneHistoryRequest(BaseModel):
    keep_latest: int = Field(default=50, ge=0, le=10_000)


# API Routes
@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": "CWMS API",
        "version": "1.1.0",
        "description": "Cloud Workload Management System REST API",
        "endpoints": {
            "health": "/health",
            "config": "/api/config",
            "start": "/api/simulation/start",
            "status": "/api/simulation/status",
            "results": "/api/simulation/results",
            "summary": "/api/simulation/summary",
            "scenarios": "/api/scenarios",
            "history": "/api/history",
            "history_prune": "/api/history/prune",
            "dashboard": "/dashboard",
        },
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "CWMS API"}


@app.get("/api/config")
async def get_default_config():
    """Get default simulation configuration."""
    config = SimulationConfig()
    return {
        "policy": config.policy,
        "intervals": config.intervals,
        "base_rate": config.base_rate,
        "burst_rate": config.burst_rate,
        "burst_start": config.burst_start,
        "burst_end": config.burst_end,
        "surge_threshold": config.surge_threshold,
        "load_threshold": config.load_threshold,
        "max_load_threshold": config.max_load_threshold,
        "fail_node": config.fail_node,
        "forecast_window": config.forecast_window,
        "forecast_strategy": config.forecast_strategy,
        "admission_control": config.admission_control,
        "overload_threshold": config.overload_threshold,
        "queue_limit": config.queue_limit,
        "request_timeout_ms": config.request_timeout_ms,
        "available_forecast_strategies": list(WorkloadForecaster.STRATEGIES),
        "seed": config.seed,
        "available_policies": PolicyFactory.available_policies(),
        "available_scenarios": [
            "normal", "burst", "failure", "overload",
        ],
        "max_total_requests": MAX_TOTAL_REQUESTS,
        "max_request_bytes": MAX_REQUEST_BYTES,
        "auth_required": bool(_api_token()),
    }


@app.post("/api/simulation/start", dependencies=[Depends(require_api_token)])
async def start_simulation(config: SimulationConfigRequest, background_tasks: BackgroundTasks):
    """Start a new simulation."""
    if simulator_state.running:
        raise HTTPException(status_code=409, detail="Simulation already running")
    
    # Validate burst intervals. start == end disables the burst window.
    if config.burst_start > config.burst_end:
        raise HTTPException(status_code=400, detail="burst_start cannot be after burst_end")
    if config.burst_end > config.intervals:
        raise HTTPException(status_code=400, detail="burst_end cannot exceed intervals")
    
    sim_config = SimulationConfig(
        policy=config.policy,
        intervals=config.intervals,
        base_rate=config.base_rate,
        burst_rate=config.burst_rate,
        burst_start=config.burst_start,
        burst_end=config.burst_end,
        surge_threshold=config.surge_threshold,
        load_threshold=config.load_threshold,
        max_load_threshold=config.max_load_threshold,
        fail_node=config.fail_node,
        forecast_window=config.forecast_window,
        forecast_strategy=config.forecast_strategy,
        admission_control=config.admission_control,
        overload_threshold=config.overload_threshold,
        queue_limit=config.queue_limit,
        request_timeout_ms=config.request_timeout_ms,
        seed=config.seed,
    )
    
    _prepare_simulator(sim_config, "custom")
    simulator_state.running = True
    
    # Run simulation in background
    background_tasks.add_task(run_simulation_background)
    
    return {"message": "Simulation started", "intervals": config.intervals, "policy": config.policy}


def _update_progress(interval: int, total: int) -> None:
    """Progress callback invoked from the simulation thread."""
    simulator_state.current_interval = interval


async def run_simulation_background():
    """Background task to run simulation without blocking the event loop."""
    try:
        sim = simulator_state.simulator
        result = await asyncio.to_thread(sim.run, _update_progress, verbose=False)
        simulator_state.result = result
        try:
            simulator_state.run_id = results_store.save_run(result, simulator_state.label)
        except Exception:  # noqa: BLE001 - persistence must not hide results
            logger.exception("Failed to persist simulation result")
            simulator_state.error = "Results could not be saved. Check server logs."
    except Exception:  # noqa: BLE001 - never expose internal exception details
        logger.exception("Simulation execution failed")
        simulator_state.error = "Simulation failed during execution. Check server logs."
    finally:
        simulator_state.running = False
        simulator_state.current_interval = simulator_state.total_intervals


@app.get("/api/simulation/status", response_model=SystemStatus)
async def get_simulation_status():
    """Get current simulation status."""
    if simulator_state.simulator is None:
        return SystemStatus(
            interval=0,
            total_intervals=0,
            running=False,
            policy="-",
            requests_generated=0,
            requests_assigned=0,
            requests_rejected=0,
            surge_detected=False,
            forecast=0.0,
            recommendation="No simulation run yet",
            nodes=[],
        )
    
    # Get current state from simulator if running, or from result if completed
    if simulator_state.running and simulator_state.simulator:
        nodes = simulator_state.simulator.nodes
        metrics = simulator_state.simulator.metrics.get_system_metrics()
        forecast_value = simulator_state.simulator.forecaster.peek()
        recommendations = simulator_state.simulator.recommendation_engine.get_recommendations()
        
        return SystemStatus(
            interval=simulator_state.current_interval,
            total_intervals=simulator_state.total_intervals,
            running=True,
            policy=simulator_state.policy,
            requests_generated=metrics.total_requests_generated,
            requests_assigned=metrics.total_requests_assigned,
            requests_rejected=metrics.total_requests_rejected,
            requests_completed=metrics.total_requests_completed,
            requests_failed=metrics.total_requests_failed,
            requests_queued=metrics.total_requests_queued,
            requests_timed_out=metrics.total_requests_timed_out,
            requests_rejected_overload=metrics.total_requests_rejected_overload,
            requests_rejected_no_capacity=metrics.total_requests_rejected_no_capacity,
            surge_detected=len(simulator_state.simulator.surge_detector.get_surge_events()) > 0,
            forecast=forecast_value,
            recommendation=recommendations[-1].message if recommendations else "Evaluating...",
            nodes=[NodeStatus(**n.to_dict()) for n in nodes],
            error=simulator_state.error,
            label=simulator_state.label,
        )
    elif simulator_state.result:
        # Return final status
        final_interval = simulator_state.result.intervals[-1] if simulator_state.result.intervals else None
        nodes = simulator_state.simulator.nodes if simulator_state.simulator else []
        
        return SystemStatus(
            interval=simulator_state.total_intervals,
            total_intervals=simulator_state.total_intervals,
            running=False,
            policy=simulator_state.policy,
            requests_generated=simulator_state.result.final_system_metrics.total_requests_generated,
            requests_assigned=simulator_state.result.final_system_metrics.total_requests_assigned,
            requests_rejected=simulator_state.result.final_system_metrics.total_requests_rejected,
            requests_completed=simulator_state.result.final_system_metrics.total_requests_completed,
            requests_failed=simulator_state.result.final_system_metrics.total_requests_failed,
            requests_queued=simulator_state.result.final_system_metrics.total_requests_queued,
            requests_timed_out=simulator_state.result.final_system_metrics.total_requests_timed_out,
            requests_rejected_overload=simulator_state.result.final_system_metrics.total_requests_rejected_overload,
            requests_rejected_no_capacity=simulator_state.result.final_system_metrics.total_requests_rejected_no_capacity,
            surge_detected=final_interval.surge_detected if final_interval else False,
            forecast=final_interval.forecast["predicted"] if final_interval else 0.0,
            recommendation=final_interval.recommendation["message"] if final_interval else "Complete",
            nodes=[NodeStatus(**n.to_dict()) for n in nodes],
            error=simulator_state.error,
            run_id=simulator_state.run_id,
            label=simulator_state.label,
        )
    else:
        nodes = simulator_state.simulator.nodes if simulator_state.simulator else create_default_nodes()
        return SystemStatus(
            interval=0,
            total_intervals=simulator_state.total_intervals,
            running=False,
            policy=simulator_state.policy,
            requests_generated=0,
            requests_assigned=0,
            requests_rejected=0,
            surge_detected=False,
            forecast=0.0,
            recommendation="Simulation failed" if simulator_state.error
            else "Simulation initialized but not started",
            nodes=[NodeStatus(**n.to_dict()) for n in nodes],
            error=simulator_state.error,
            label=simulator_state.label,
        )


@app.get("/api/simulation/results")
async def get_simulation_results():
    """Get detailed simulation results (CSV data)."""
    if simulator_state.result is None:
        raise HTTPException(status_code=404, detail="No simulation results available")
    
    return {
        "intervals": [
            {
                "interval": r.interval,
                "requests_generated": r.requests_generated,
                "requests_assigned": r.requests_assigned,
                "requests_completed": r.requests_completed,
                "requests_failed": r.requests_failed,
                "requests_timed_out": r.requests_timed_out,
                "requests_queued": r.requests_queued,
                "requests_rejected": r.requests_rejected,
                "requests_rejected_overload": r.requests_rejected_overload,
                "requests_rejected_no_capacity": r.requests_rejected_no_capacity,
                "surge_detected": r.surge_detected,
                "surge_event": r.surge_event,
                "forecast": r.forecast,
                "recommendation": r.recommendation,
                "max_load": r.max_load,
                "nodes": r.node_metrics,
            }
            for r in simulator_state.result.intervals
        ],
    }


@app.get("/api/simulation/summary", response_model=SimulationSummary)
async def get_simulation_summary():
    """Get simulation summary with metrics."""
    if simulator_state.result is None:
        raise HTTPException(status_code=404, detail="No simulation results available")
    
    summary = simulator_state.result.to_summary_dict()
    return SimulationSummary(**summary)


@app.post("/api/scenarios/run", dependencies=[Depends(require_api_token)])
async def run_scenario(scenario: ScenarioRequest, background_tasks: BackgroundTasks):
    """Run a predefined scenario."""
    if simulator_state.running:
        raise HTTPException(status_code=409, detail="Simulation already running")
    
    scenario_configs = {
        "normal": {"base_rate": 40, "burst_rate": 40, "burst_start": 0, "burst_end": 0},
        "burst": {"base_rate": 40, "burst_rate": 180, "burst_start": 8, "burst_end": 13},
        "failure": {"base_rate": 50, "burst_rate": 50, "burst_start": 0, "burst_end": 0, "fail_node": "backend-b"},
        "overload": {
            "base_rate": 120, "burst_rate": 120, "burst_start": 0, "burst_end": 0,
            "overload_threshold": 80.0, "queue_limit": 10,
            "request_timeout_ms": 100.0,
        },
    }
    
    if scenario.scenario not in scenario_configs:
        raise HTTPException(status_code=400, detail=f"Unknown scenario: {scenario.scenario}")
    
    config_params = scenario_configs[scenario.scenario]
    config_params["policy"] = scenario.policy
    
    sim_config = SimulationConfig(**config_params)
    _prepare_simulator(sim_config, scenario.scenario)
    simulator_state.running = True
    
    background_tasks.add_task(run_simulation_background)
    
    return {"message": f"Scenario '{scenario.scenario}' started", "policy": scenario.policy}


@app.get("/api/scenarios")
async def list_scenarios():
    """List available predefined scenarios."""
    return {
        "scenarios": [
            {
                "id": "normal",
                "name": "Normal Steady Traffic",
                "description": "Steady request rate without bursts",
                "params": {"base_rate": 40, "burst_rate": 40},
            },
            {
                "id": "burst",
                "name": "Traffic Burst",
                "description": "Sudden traffic increase in middle intervals",
                "params": {"base_rate": 40, "burst_rate": 180, "burst_start": 8, "burst_end": 13},
            },
            {
                "id": "failure",
                "name": "Node Failure",
                "description": "One backend node marked unhealthy",
                "params": {"base_rate": 50, "fail_node": "backend-b"},
            },
            {
                "id": "overload",
                "name": "Overload and Queueing",
                "description": "Bounded queues, overflow rejection, and request timeouts",
                "params": {
                    "base_rate": 120, "queue_limit": 10,
                    "overload_threshold": 80, "request_timeout_ms": 100,
                },
            },
        ],
        "policies": PolicyFactory.available_policies(),
    }


@app.get("/api/nodes")
async def get_nodes():
    """Get current node statuses."""
    if simulator_state.simulator is None:
        nodes = create_default_nodes()
    else:
        nodes = simulator_state.simulator.nodes
    
    return {"nodes": [n.to_dict() for n in nodes]}


@app.post("/api/nodes/{node_name}/health", dependencies=[Depends(require_api_token)])
async def set_node_health(node_name: str, healthy: bool):
    """Set node health; the override is kept for subsequent simulations."""
    if simulator_state.running:
        raise HTTPException(status_code=409, detail="Cannot modify nodes during simulation")
    
    if node_name not in {n.name for n in create_default_nodes()}:
        raise HTTPException(status_code=404, detail=f"Node {node_name} not found")
    
    if simulator_state.simulator is None:
        _prepare_simulator(SimulationConfig(), "custom")
    
    node = next((n for n in simulator_state.simulator.nodes if n.name == node_name), None)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node {node_name} not found")
    
    node.set_health(NodeState.HEALTHY if healthy else NodeState.UNHEALTHY)
    simulator_state.health_overrides[node_name] = healthy
    return {"message": f"Node {node_name} set to {'healthy' if healthy else 'unhealthy'}"}


@app.get("/api/export/csv")
async def export_csv():
    """Export simulation results as CSV file."""
    if simulator_state.result is None:
        raise HTTPException(status_code=404, detail="No simulation results available")
    
    # Create CSV in memory and return
    from fastapi.responses import StreamingResponse
    import io
    import csv
    
    rows = simulator_state.result.to_csv_rows()
    if not rows:
        raise HTTPException(status_code=404, detail="No data to export")
    
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    
    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=cwms_results.csv"},
    )


@app.get("/api/export/json")
async def export_json():
    """Export simulation results as JSON."""
    if simulator_state.result is None:
        raise HTTPException(status_code=404, detail="No simulation results available")
    
    return simulator_state.result.to_summary_dict()


@app.get("/api/history")
async def list_history(limit: int = 20):
    """List persisted simulation runs (newest first)."""
    if not 1 <= limit <= 200:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 200")
    return {"runs": results_store.list_runs(limit=limit)}


@app.post("/api/history/prune", dependencies=[Depends(require_api_token)])
async def prune_history(request: PruneHistoryRequest):
    """Delete older stored runs, preserving the newest N."""
    before = results_store.count_runs()
    deleted = results_store.prune_runs(keep_latest=request.keep_latest)
    return {
        "deleted": deleted,
        "remaining": results_store.count_runs(),
        "previous": before,
        "keep_latest": request.keep_latest,
    }


@app.get("/api/history/{run_id}")
async def get_history_run(run_id: int):
    """Get one persisted run with interval and node metrics."""
    run = results_store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return run


@app.get("/dashboard")
async def dashboard():
    """Serve the dashboard HTML."""
    dashboard_file = dashboard_path / "index.html"
    if dashboard_file.exists():
        return FileResponse(str(dashboard_file))
    raise HTTPException(status_code=404, detail="Dashboard not found. Build the frontend first.")


def run_server(host: Optional[str] = None, port: Optional[int] = None, reload: bool = False):
    """Run the FastAPI server on loopback by default."""
    host = host or os.environ.get("CWMS_API_HOST", "127.0.0.1")
    port = int(port or os.environ.get("CWMS_API_PORT", "8000"))
    _validate_bind_host(host)
    uvicorn.run("cwms_api.main:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    run_server()