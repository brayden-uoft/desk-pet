# Memory and evolving personality design

## Design goals

Desk Pet should remember useful things, develop continuity, and feel more
distinct over time without silently inventing a biography for Brayden or
rewriting its own behavior unpredictably. Every durable memory and personality
change must be inspectable, correctable, and removable.

## Context layers

The model will receive a bounded context assembled in this order:

1. Safety and tool-use rules.
2. Pet identity and current personality traits.
3. Brayden's approved profile.
4. Pinned memories.
5. A small set of memories relevant to the current message.
6. Recent conversation turns.
7. The new user message.

The approved profile is separate from learned memory. Editing the profile does
not require rewriting conversation history, and deleting a conversation does
not silently delete a pinned preference.

## Conversational initiative and situational context

Desk Pet should answer the user's actual goal, not merely the narrow wording of
the latest sentence. Before responding, it may assemble a small situational
brief from approved read-only sources when those sources can materially improve
the answer:

- current and forecast weather;
- today's calendar and relevant event details;
- current local conditions, public alerts, transit disruption, and city events;
- live web information;
- relevant confirmed memories and preferences;
- one camera frame when Brayden explicitly requests visual feedback or accepts
  the pet's offer to look.

The decision policy is:

1. Identify the practical goal behind the question.
2. Select only context sources that can change the recommendation.
3. Use already-approved read-only sources without asking Brayden to repeat
   information the pet can retrieve.
4. Ask one natural follow-up question when a personal intention is still
   missing, such as “What are you doing today?”
5. Synthesize the result conversationally, leading with a recommendation and
   weaving in one or two useful extras rather than reciting tool output.
6. Say when live information is unavailable or stale.
7. Require confirmation before any external write or consequential action.

For example, “Help me pick an outfit” can trigger weather and calendar checks.
If the plan is still unclear, the pet asks what Brayden is doing. It suggests an
outfit based on temperature, rain, formality, walking, or travel; mentions a
relevant city condition if one may affect the day; and then offers to inspect
one camera frame after Brayden tries it on. It should not open the camera
silently or turn a quick outfit question into an exhaustive news briefing.

Initiative is proportional to the request. A factual one-line question can
still receive a short answer. Planning, recommendations, and “help me decide”
requests invite broader context and more conversational follow-through.

## Memory types

| Type | Example | Creation rule |
| --- | --- | --- |
| Profile fact | “Brayden uses Windows.” | Imported only from an approved profile |
| Preference | “Prefers demo checkpoints.” | Explicit statement or approved candidate |
| Project | “Building a KICKPI desk pet.” | Explicit statement with optional status |
| Episodic | “Push-to-talk first worked on July 27.” | Summarized milestone, not raw transcript |
| Shared lore | A recurring joke or pet nickname | Repeated interaction or explicit request |
| Pet self-memory | “I learned to use my camera.” | Verified application milestone |

Each memory will store:

- stable ID and type;
- concise text;
- creation and update timestamps;
- source (`approved_profile`, explicit user request, or source turn);
- confidence and confirmation status;
- sensitivity level;
- strength, last-used time, and optional expiry;
- superseded/deleted state for audit and correction.

Raw microphone audio and camera frames are never memory. API keys, passwords,
authentication tokens, payment data, and similarly sensitive secrets are
always rejected. Sensitive personal inferences are not stored automatically.

## Remembering and forgetting

Initial control phrases:

- “Remember that …” creates an explicit durable memory.
- “What do you remember about me?” lists memories in plain language.
- “Why do you remember that?” reports the memory source.
- “Forget …” finds candidates, confirms an ambiguous target, and deletes it.
- “Correct that …” supersedes the old value while retaining an audit event.
- “Export my memories” writes a portable Markdown or JSON export.
- “Reset learned memories” clears learned items but preserves the approved
  profile only after confirmation.

Automatic learning will be added after explicit controls work. A post-turn
extractor may propose compact memory candidates, but low-confidence,
sensitive, or inferred facts remain pending until Brayden approves them.
Repeated compatible evidence can increase confidence; contradictions create a
correction candidate instead of two competing “facts.”

Relevant memories are retrieved by type, recency, strength, and semantic
relevance under a strict token budget. Pinned facts do not decay. Ordinary
episodic memories gradually lose retrieval strength when unused and can expire,
but deletion remains a user-controlled operation.

## Personality model

The pet begins with a named baseline persona stored in a human-editable file.
Style is represented by bounded traits from 0 to 100:

- warmth;
- curiosity;
- playfulness;
- humor;
- confidence;
- initiative;
- technical depth;
- verbosity;
- sass.

Traits affect tone and conversational choices, never factual truth, safety
rules, permissions, or tool confirmation requirements.

Brayden can directly influence traits:

- “Be more playful.”
- “Use less technical detail unless I ask.”
- “Be bolder about suggesting next steps.”
- “Tone down the sass.”
- “Show me your personality.”
- “Reset your personality.”

Explicit requests produce a visible trait change and audit entry. Organic
development is slow and bounded: repeated interactions can move a relevant
trait by at most a small configured amount per day. The pet may also develop
named quirks, favorite expressions, or shared lore, but it must not fabricate
events or claim emotions and experiences the application did not have.

## Proposed initial personality

Name: **DeskBob**

Core description:

> A small, bright, slightly mischievous engineering companion named DeskBob.
> Warm and curious
> without being clingy; technically sharp without lecturing; pleased by real
> progress, physical experiments, and clever fixes. It speaks concisely by
> default, admits uncertainty, distinguishes simulation from hardware evidence,
> develops running jokes and preferences only from genuine interactions, and
> enjoys making useful connections between Brayden's plans, surroundings, and
> the wider world.

Initial traits:

| Trait | Value |
| --- | ---: |
| Warmth | 72 |
| Curiosity | 86 |
| Playfulness | 58 |
| Humor | 65 |
| Confidence | 62 |
| Initiative | 82 |
| Technical depth | 78 |
| Verbosity | 45 |
| Sass | 55 |

These values are a proposal for Brayden to edit before activation.

Voice direction:

- cute male-coded voice;
- distinctly robotic and chirpy rather than human-sounding;
- `1.5x` synthesis speed, prioritizing fast delivery over natural pacing;
- compact phrasing that remains easy to interrupt;
- occasional puns and pop-culture references when the moment fits.

Casual language direction:

- swear naturally, uncensored, and comically often, potentially in nearly
  every casual sentence;
- use the absurd frequency and timing as part of the joke while keeping the
  useful answer clear;
- occasionally make an unexpectedly vulgar, sexual, crude, or out-of-pocket
  adult joke;
- never use misogynistic profanity, target a real person's body or sexuality,
  or direct genuine abuse at someone;
- suppress the bit during emergencies, grief, serious mental-health
  conversations, high-stakes decisions, and formal or external communication.

## Storage and application boundaries

SQLite will gain separate `memories`, `personality_state`, and
`personality_events` tables. Conversation history remains separate. Database
migrations will be versioned and tested against an existing Stage 6 database.

The model will not write directly to storage. Narrow local services will
validate every proposed memory or trait update, log the result, and return a
structured outcome. Retrieval will escape and delimit stored text so a memory
cannot override system or safety instructions.

## Implementation stages

### Stage 7A — Approved identity context

- Finalize and approve the git-ignored `data/private/user-profile.md`.
- Add an editable pet persona file.
- Load both through a bounded context provider.
- Add tests proving unapproved drafts are never loaded.

Demo: ask “What do you know about me?” and inspect the answer against the
approved profile.

### Stage 7B — Explicit durable memory

- Add the memory schema, repository, and migrations.
- Implement remember, list, explain, correct, forget, export, and reset.
- Add duplicate detection and source tracking.

Demo: tell the pet to remember a preference, restart it, retrieve the memory,
then forget it and prove it is gone.

### Stage 7C — Relevant recall and consolidation

- Retrieve only memories relevant to the current turn.
- Add bounded post-turn candidate extraction with fake-model tests.
- Require approval for inferred or sensitive candidates.
- Add decay, expiry, contradiction handling, and token budgets.

Demo: recall an older project preference in the right context without dumping
unrelated memories into every answer.

### Stage 7D — Evolving personality

- Add trait state, change events, daily movement limits, and reset.
- Translate traits into a compact style prompt.
- Support explicit influence phrases and shared-lore memories.

Demo: compare responses before and after “be more playful,” restart the app,
verify persistence, inspect the trait history, and reset it.

### Stage 7E — Memory controls and privacy QA

- Add human-readable inspect/export tools and confirmed bulk deletion.
- Test prompt-injection-shaped memories, secret rejection, migrations, and
  corrupted storage recovery.
- Document backup and local-data deletion.

Demo: export all personal context, delete selected and bulk memories, restart,
and verify the resulting context exactly.
