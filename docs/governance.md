# Model governance

The governance layer applies the five-stage lifecycle: **Discover**, **Document**,
**Redevelop**, **Validate**, and **Monitor**. Each approval advances one stage.
Reject and request-changes decisions remain auditable without advancing it.

Risk tiers follow the SS1/23 vocabulary (`low`, `medium`, `high`, `critical`).
`governance.core.STAGE_PRINCIPLES` provides the control-principle mapping.
Decision makers must be different from requesters (separation of duties), and
every decision is recorded in the append-only audit log.
