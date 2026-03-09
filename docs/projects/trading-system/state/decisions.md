# Decisions Log

## 2026-03-05: Documentation Architecture

**Decision:** Establish two-tier project documentation with TradingSystemAIBuild.md as master project doc and RateServiceAIBuild.md as service-level doc, with cross-references mirroring the service dependency graph.

**Rationale:** Enterprise-grade documentation requires proper structure. The original TradingSystemAIBuild.md was an early brief that didn't reflect current state. RateService had no project-level document. Cross-references ensure navigability between repos.

**Made by:** User + Claude (collaborative)

---

## 2026-03-08: Series/Chart/Strategy Nomenclature

**Decision:** Establish three-tier data model: Series (instrument+period, raw OHLCV), Chart (named view = Series + indicators), Strategy assignments on Charts (not Series). Multiple Charts can share a Series. Multiple Strategies per Chart, each toggleable.

**Rationale:** The existing `charts` table conflated the data stream with the analytical view. Separating them allows multiple analytical configurations on the same data, and strategies need indicators (which live on Charts) to function.

**Made by:** User + Claude (collaborative)

---

## 2026-03-08: Strategy Authoring Approach

**Decision:** Python (BaseStrategy subclass) as the foundation for all strategies. Plain English → Claude-generated Python as a convenience layer. No DSL or rules engine.

**Rationale:** Any condition expressible in a simple DSL is trivially generated as Python by Claude. A DSL adds complexity without capability. Both paths produce the same artifact: a Python file.

**Made by:** User + Claude (collaborative)

---

## 2026-03-08: Paper/Live Trading Dual API Keys

**Decision:** Separate OANDA credentials for paper (practice API) and live (production API) trading. UI toggle with prominent mode indicator. Default to paper. Require confirmation for live.

**Rationale:** Safety-critical. Accidental live trading must be impossible. OANDA provides separate practice/production environments with their own API keys.

**Made by:** User + Claude (collaborative)

---

## 2026-03-05: Requirement Scoping Constraint

**Decision:** All documentation captures current state and accomplishments only. Requirement scoping is user-driven — agents do not propose future features or roadmap items.

**Rationale:** User explicitly corrected overreach: "the agent definitions denote that I will be the one to scope new requirements." This is a behavioral constraint for all agents.

**Made by:** User (explicit directive)

---

## 2026-03-05: RateServiceEnterpriseStrength.md Disposition

**Decision:** Archive in RateService repo rather than delete. Done items folded into RateServiceAIBuild.md; planned items preserved for future user-scoped requirements.

**Rationale:** Preserves context for future requirement scoping sessions without cluttering active documentation.

**Made by:** User + Claude (collaborative)

---

## 2026-03-08: Commit Workflow Standard

**Decision:** Code and docs always commit together as a single package. Before every commit: show current tag, ask user what tag to use. Detailed commit messages with category breakdowns. Tag and push in one step.

**Rationale:** User identified drift where commits were being discussed piecemeal or docs shipped separately. Standardizing prevents fragmented state.

**Made by:** User (explicit directive)

---

## 2026-03-08: Docker-Only Deployment

**Decision:** Everything runs in Docker. No local launchctl fallback. This is a portability requirement.

**Rationale:** User confirmed this is a long-standing requirement. The launchctl plist approach caused port conflicts with Docker and left stale processes. Single deployment method eliminates ambiguity.

**Made by:** User (explicit directive)
