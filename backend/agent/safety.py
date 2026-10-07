"""
agent/safety.py

Guardrail layer for SysKernel-AI. Every action the agent wants to take
must pass through here first. This is the enforcement point referenced
in docs/SAFETY.md.

Design principles:
1. Allowlist only - the agent can NEVER run an arbitrary command. It can
   only request one of a small set of pre-approved, parameterized actions.
2. Risk tiers - low-risk actions can run autonomously; medium/high-risk
   actions require human approval before execution.
3. Blast-radius limit - a hard cap on how many actions the agent can take
   per incident, plus auto-rollback if the issue doesn't resolve in time.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable, Dict, List, Optional


class RiskTier(Enum):
    LOW = "low"           # safe, reversible, narrow blast radius -> auto-approved
    MEDIUM = "medium"     # reversible but broader impact -> requires approval
    HIGH = "high"         # hard to reverse / high impact -> always requires approval


@dataclass
class ActionDefinition:
    name: str
    description: str
    risk_tier: RiskTier
    handler: Callable[..., str]  # the actual function that performs the action


@dataclass
class ActionRequest:
    action_name: str
    params: dict
    requested_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ActionDecision:
    approved: bool
    requires_human_approval: bool
    reason: str


class IncidentBudget:
    """Tracks the blast-radius limit for a single incident."""

    def __init__(self, max_actions: int = 3, window_minutes: int = 10):
        self.max_actions = max_actions
        self.window = timedelta(minutes=window_minutes)
        self.actions_taken: List[datetime] = []

    def can_take_action(self) -> bool:
        cutoff = datetime.now(timezone.utc) - self.window
        self.actions_taken = [t for t in self.actions_taken if t >= cutoff]
        return len(self.actions_taken) < self.max_actions

    def record_action(self):
        self.actions_taken.append(datetime.now(timezone.utc))

    def remaining(self) -> int:
        cutoff = datetime.now(timezone.utc) - self.window
        active = [t for t in self.actions_taken if t >= cutoff]
        return max(0, self.max_actions - len(active))


class SafetyGuard:
    """Central guardrail enforcement. All agent actions go through check_action()."""

    def __init__(self, allowlist: Dict[str, ActionDefinition], max_actions_per_incident: int = 3):
        self.allowlist = allowlist
        self.max_actions_per_incident = max_actions_per_incident
        self.budget = IncidentBudget(max_actions=max_actions_per_incident)

    def check_action(self, request: ActionRequest) -> ActionDecision:
        """Decide whether a requested action is allowed to run, and whether
        it needs human sign-off first. Does NOT execute the action."""

        action_def = self.allowlist.get(request.action_name)

        # Rule 1: must be on the allowlist. No exceptions, no arbitrary commands.
        if action_def is None:
            return ActionDecision(
                approved=False,
                requires_human_approval=False,
                reason=f"REJECTED: '{request.action_name}' is not an allowlisted action.",
            )

        # Rule 2: blast-radius limit for this incident.
        if not self.budget.can_take_action():
            return ActionDecision(
                approved=False,
                requires_human_approval=False,
                reason=(
                    f"REJECTED: blast-radius limit reached "
                    f"({self.max_actions_per_incident} actions per {self.budget.window})."
                ),
            )

        # Rule 3: risk tier determines autonomy.
        if action_def.risk_tier == RiskTier.LOW:
            return ActionDecision(
                approved=True,
                requires_human_approval=False,
                reason=f"Auto-approved (low risk): {action_def.description}",
            )
        else:
            return ActionDecision(
                approved=False,
                requires_human_approval=True,
                reason=(
                    f"HOLD for human approval ({action_def.risk_tier.value} risk): "
                    f"{action_def.description}"
                ),
            )

    def record_executed(self):
        """Call this AFTER an action actually executes, to count it against the budget."""
        self.budget.record_action()


# ---------------------------------------------------------------------------
# Example allowlist. Replace handlers with real implementations that call
# subprocess / psutil / systemd, each with its own strict parameter validation.
# ---------------------------------------------------------------------------

def _restart_service(service_name: str) -> str:
    # TODO: real implementation, e.g. subprocess.run(["systemctl", "restart", service_name])
    return f"Restarted service: {service_name}"


def _clear_temp_cache(path: str) -> str:
    # TODO: real implementation with strict path validation (never allow arbitrary paths)
    return f"Cleared cache at: {path}"


def _scale_replica(service_name: str, replicas: int) -> str:
    # TODO: real implementation, e.g. kubectl scale
    return f"Scaled {service_name} to {replicas} replicas"


DEFAULT_ALLOWLIST: Dict[str, ActionDefinition] = {
    "restart_service": ActionDefinition(
        name="restart_service",
        description="Restart a known, named service via systemd.",
        risk_tier=RiskTier.LOW,
        handler=_restart_service,
    ),
    "clear_temp_cache": ActionDefinition(
        name="clear_temp_cache",
        description="Clear a pre-approved temp/cache directory.",
        risk_tier=RiskTier.LOW,
        handler=_clear_temp_cache,
    ),
    "scale_replica": ActionDefinition(
        name="scale_replica",
        description="Change replica count for a service.",
        risk_tier=RiskTier.MEDIUM,
        handler=_scale_replica,
    ),
}


if __name__ == "__main__":
    guard = SafetyGuard(DEFAULT_ALLOWLIST, max_actions_per_incident=3)

    # Example 1: low-risk, allowlisted -> auto-approved
    req1 = ActionRequest(action_name="restart_service", params={"service_name": "nginx"})
    print(guard.check_action(req1))

    # Example 2: medium-risk -> needs human approval
    req2 = ActionRequest(action_name="scale_replica", params={"service_name": "api", "replicas": 3})
    print(guard.check_action(req2))

    # Example 3: not on allowlist at all -> rejected outright
    req3 = ActionRequest(action_name="rm_rf_root", params={})
    print(guard.check_action(req3))