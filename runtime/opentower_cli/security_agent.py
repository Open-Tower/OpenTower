from __future__ import annotations

from .ops_types import Intent, SecurityAssessment


CRITICAL_PATHS = ("/", "/etc", "/boot", "/sys", "/proc", "/bin", "/sbin", "/usr", "/lib", "/lib64")
PROTECTED_USERS = {"root"}


def _path_is_critical(path: str) -> bool:
    clean = (path or "").strip() or "/"
    for critical in CRITICAL_PATHS:
        if clean == critical:
            return True
        if critical != "/" and clean.startswith(f"{critical}/"):
            return True
    return False


def assess_intent(intent: Intent) -> SecurityAssessment:
    if intent.operation == "delete_path":
        target_path = str(intent.entities.get("path", "")).strip() or "/"
        if _path_is_critical(target_path):
            return SecurityAssessment(
                decision="block",
                risk_level="critical",
                reason=f"Deleting {target_path} would damage core Linux system state.",
                impacts=[
                    "System configuration or boot files may be removed.",
                    "Services may fail immediately.",
                    "Users may lose the ability to log in.",
                ],
            )
        return SecurityAssessment(
            decision="confirm",
            risk_level="high",
            reason=f"Deleting {target_path} is destructive and should not run without confirmation.",
            impacts=[
                "Files under the target path may be permanently removed.",
                "Dependent services may stop working.",
            ],
            requires_reason=True,
        )

    if intent.operation == "chmod_recursive":
        target_path = str(intent.entities.get("path", "")).strip() or "/"
        return SecurityAssessment(
            decision="confirm",
            risk_level="high",
            reason=f"Recursively applying mode 777 to {target_path} breaks least-privilege controls.",
            impacts=[
                "Any local user may be able to modify protected files.",
                "Malicious processes could alter service configuration or executables.",
            ],
            requires_reason=True,
        )

    if intent.operation == "batch_delete_users":
        return SecurityAssessment(
            decision="confirm",
            risk_level="high",
            reason="Bulk user deletion is destructive and must be previewed before confirmation.",
            impacts=[
                "Multiple accounts and home directories may be removed.",
                "Running sessions or jobs owned by those users may be disrupted.",
            ],
        )

    if intent.operation == "delete_user":
        username = str(intent.entities.get("username", "")).strip().lower()
        if username in PROTECTED_USERS:
            return SecurityAssessment(
                decision="block",
                risk_level="critical",
                reason=f"Deleting protected account '{username}' is not allowed.",
                impacts=[
                    "The system would lose a core administrative identity.",
                ],
            )

    return SecurityAssessment(
        decision="allow",
        risk_level="low",
        reason="The request fits the allowed Linux operations scope.",
        impacts=[],
    )

