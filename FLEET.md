# FLEET.md — Fleet Identity Model and Registry

This document defines how autonomous agents, hosts, and their relationships are
identified across the fleet. The Observatory's Fleet Registry (see
[docs/architecture.md](docs/architecture.md)) will implement this model.

## Identity Convention

The current convention, using the first agent as the example:

```text
A001-OC01-RPSG01
│    │    └── Host ID: Raspberry Pi, Singapore, host number 01
│    └────── Instance ID: OpenClaw agent instance number 01 on that host
└─────────── Global serial: agent A001, globally unique and immutable
```

Full identity format:

```text
<GLOBAL-SERIAL>-<INSTANCE-ID>-<HOST-ID>
```

### Component Definitions

| Component | Example | Rules |
| --- | --- | --- |
| Global serial | `A001` | Globally unique, immutable, never reused. Assigned at commissioning, sequential (`A001`, `A002`, …). Survives re-hosting and framework changes. |
| Instance ID | `OC01` | Framework prefix + instance number on the host. `OC` = OpenClaw. Other frameworks get their own prefixes (e.g., `CC` for a hypothetical Claude-Code-native runner) reserved in this document before first use. |
| Host ID | `RPSG01` | Platform prefix + location code + host number. `RP` = Raspberry Pi, `SG` = Singapore, `01` = host number 01. |

### Host ID Scheme

```text
<PLATFORM><LOCATION><NN>
```

| Platform prefix | Meaning |
| --- | --- |
| `RP` | Raspberry Pi |
| `VP` | VPS |
| `WS` | Workstation |
| *(future)* | New platforms reserve a prefix here before first use |

Location codes are short human-meaningful codes (e.g., `SG` Singapore, `EU` Europe,
`US` United States, or provider/site codes as the fleet grows). Host numbers are
two-digit and unique per platform+location (extendable to three digits if ever needed).

Examples:

- `RPSG01` — Raspberry Pi, Singapore, host 01
- `VPEU01` — VPS, Europe, host 01
- `WSSG01` — Workstation, Singapore, host 01

## What the Model Supports

- **Globally unique Agent IDs:** the global serial (`A001`) uniquely identifies an agent
  across the entire fleet, forever.
- **Multiple agent frameworks:** the instance prefix (`OC`, plus future reserved
  prefixes) distinguishes OpenClaw agents from agents built on other frameworks.
- **Multiple agents on one host:** instance numbers (`OC01`, `OC02`) separate co-located
  agents.
- **Multiple hosts per location:** host numbers (`RPSG01`, `RPSG02`) separate hosts.
- **Raspberry Pi, VPS, workstation, and future platforms:** platform prefixes are an
  open, documented set.
- **Immutable global serials:** `A001` never changes, even if the agent moves to a new
  host or framework. The *full identity* changes to reflect the new placement; the
  serial does not.
- **Human-readable names:** each agent may have a friendly display name (registry field),
  which is cosmetic and never used as a key.
- **Machine-readable lowercase IDs:** for branches, hostnames, metrics labels, and API
  paths, the lowercase form is used: `a001-oc01-rpsg01` (and `a001` alone where the
  global serial suffices, e.g., branch prefix `a001/`).
- **Agent roles:** e.g., Autonomous Software Engineering Agent, Collector Agent,
  Operations Agent — a registry field, not encoded in the ID.
- **Agent lifecycle states:** see below.
- **Commissioning and retirement:** see below.

## Agent Lifecycle States

| State | Meaning |
| --- | --- |
| Provisioned | Identity reserved; host/credentials being prepared |
| Commissioning | Being installed, configured, and verified |
| Active | In service and eligible for missions |
| Paused | Temporarily out of service (maintenance, investigation) |
| Suspended | Deliberately disabled pending a decision (e.g., security event) |
| Retired | Permanently decommissioned; serial never reused |

Lifecycle transitions are recorded in the Fleet Registry with timestamps and the
authorizing human.

### Commissioning

Commissioning an agent requires: assignment of the next global serial, host placement,
credential provisioning (dedicated SSH keys, scoped tokens), registry entry creation,
supervisor sign-off, and a recorded commissioning date.

### Retirement

Retirement requires: revocation of all credentials, archival of the registry entry
(status → Retired, retirement date recorded), preservation of audit history, and
supervisor sign-off. Serials and identities of retired agents are never reused.

## Fleet Registry Fields

Each registry entry contains at minimum:

| Field | Description |
| --- | --- |
| Global ID | Immutable serial (`A001`) |
| Agent ID | Instance + host (`OC01-RPSG01`) |
| Full Identity | Combined identity (`A001-OC01-RPSG01`) |
| Machine ID | Lowercase form (`a001-oc01-rpsg01`) |
| Display Name | Optional human-friendly name |
| Framework | e.g., OpenClaw (with version where known) |
| Host | Host description and Host ID |
| Role | Agent role |
| Status | Lifecycle state |
| Supervisor | Responsible human |
| Commissioned | Commissioning date |
| Retired | Retirement date (if applicable) |
| Primary Mission | Current primary assignment |
| Control Channel | Human-attention channel (e.g., Telegram) |
| Engineering Interface | Primary work interface (e.g., SSH) |
| Repository | Primary repository (where applicable) |
| Credentials Reference | *Names* of provisioned credentials (never values) |
| Notes | Free-form operational notes |

## Fleet Registry

### A001 — First Registry Entry

| Field | Value |
| --- | --- |
| Global ID | A001 |
| Agent ID | OC01-RPSG01 |
| Full Identity | A001-OC01-RPSG01 |
| Framework | OpenClaw |
| Host | Raspberry Pi SG01 |
| Role | Autonomous Software Engineering Agent |
| Status | Active |
| Supervisor | Martin |
| Commissioned | 2026-07-19 |
| Primary Mission | OpenClaw Observatory |
| Control Channel | Telegram |
| Engineering Interface | SSH |
| Repository | cht35me/openclaw-observatory |

---

This file is the interim registry of record until the Observatory's Fleet Registry
service exists; at that point this document remains the specification and the service
becomes the runtime source of truth. Defined under Mission M001 by A001-OC01-RPSG01.
