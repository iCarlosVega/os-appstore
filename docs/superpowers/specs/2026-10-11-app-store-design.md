# Community Software Store Design

This store helps everyday computer users find useful software they can use free of charge. It centralizes project information, credits developers, and makes alternatives to paid products easier to discover. A nightly discovery job proposes GitHub projects; the owner approves additions before visitors can find them.

The owner approved the consolidated requirements in conversation on October 11, 2026 and authorized reasonable inferences for unanswered questions. This document records those requirements and supplies the operating defaults needed for planning. The written specification is ready for review. Visual design remains deferred at the owner's request.

## Product scope

- Audience: everyday users, including nontechnical visitors. Use plain explanations and identify software that needs compilation or additional setup.
- Service: a public community catalog. Visitors browse, search, request apps, and open project repositories without accounts.
- Funding: Buy Me a Coffee. Contributions support operating costs and donations to the Wikimedia Foundation. Display an owner-configured donation link and factual explanation; automatic donation transfers and a fixed allocation are outside the first release.
- Eligibility: prioritize open source projects with a usable free offering. Optional paid features are acceptable when the free offering is useful. Record the actual license without describing every listing as open source. Unclear eligibility enters review.
- Coverage: desktop and mobile apps, games, command-line tools, extensions, plugins, libraries, self-hosted services, and web apps. NSFW content is excluded.
- Games: rewritten, reimplemented, and decompiled game projects are eligible for owner review. Record requirements for external game assets when the project documents them. Specific examples can be added as seeds later.
- Source-only software may appear with a clear setup label. Source availability does not imply a ready-to-run installer.
- Discovery starts with public GitHub repositories. Broad web crawling, social-network monitoring, other Git hosts, and user-triggered external discovery are future extensions.
- Reviews, ratings, personalization, public profiles, native clients, and automated installation are outside the first release.

The initial release is one coherent slice: discover a candidate, approve it, publish a listing, find it through catalog search, and open its official repository. Operations, cost controls, and self-hosting support this slice.

## Visitor experience

Visitors can browse a category tree, filter listings, search, open an app page, and submit an app request. Initial functional pages are the catalog, category view, app detail, request form, and service information page. Layout, branding, imagery, and visual styling will be designed separately.

The initial categories are Productivity, Development, Creative Tools, Privacy, Utilities, Communication, Education, AI, and Gaming. Categories support parent-child relationships. An app can have multiple approved categories and tags. Category creation, renaming, and app category changes require owner approval.

Platforms are filters: Windows, macOS, Linux, Android, iOS, and Browser. Architecture values initially include x86-64 and ARM64. Record compatibility only when supported by upstream information. Visitors select platforms manually; the website does not select a platform from their device.

Simple filters also cover software type and documented attributes such as offline use, no account required, accessibility features, and low hardware requirements. An unknown attribute never counts as a confirmed match. These attributes describe the listed software, separately from the store's account-free visitor experience.

## Listings and attribution

Each published app has a stable internal ID and slug, its canonical GitHub repository ID and URL, and the following display fields:

| Field | Behavior |
| --- | --- |
| App name | Use the upstream name; retain former names as search aliases. |
| Developer or maintainer | Credit the current upstream owner or documented maintainer with its official link. Preserve original-author credit when documented. |
| Description | Reuse factual upstream text or an owner-edited explanation. Avoid generated promotional claims. |
| License and cost model | Record the upstream license and whether the usable offering is free or has optional paid features. |
| Platforms and architectures | Record documented compatibility without guessing. |
| Requirements | Include documented OS, RAM, storage, GPU, dependencies, runtime, internet, account, and external-asset requirements. |
| Version | Show the latest stable, non-draft release. When none exists, show “Not provided.” |
| Setup type | Distinguish ready-to-use software, source builds, command-line installation, hosted services, and other documented setup. |
| Official links | Repository plus available website, documentation, support, issues, and donation links. |
| Provenance | Record each metadata source, last successful refresh, and any owner override. |
| Download clicks | Count activations of the store's repository-opening action. |

An unavailable factual field displays “Not provided.” Requirements can include the version they describe when upstream specifies one; this release does not maintain a matrix of requirements for every historical binary.

Use an upstream icon only when its use is appropriate; otherwise use a neutral fallback. Screenshots are optional and can be supplied by the owner. Changelogs, activity summaries on app pages, related-app sections, and product-comparison pages are deferred. Related suggestions in search remain in scope.

Jev does not write descriptions. Automated ingestion uses upstream structured data and bounded source excerpts; the owner can improve descriptions in the admin interface. A separate generative model is optional future work and receives no automatic spending allocation.

A repository transfer or rename with the same GitHub repository ID keeps the existing app identity and enters review before its public canonical link changes. Distinct forks are separate candidates; they never merge automatically. Multiple repositories belonging to one app are associated by the owner. Keep aliases and redirects when an app slug changes.

## Repository opening and install prompt

The Download action opens the approved official repository. Files are not stored, proxied, built, or executed by the store.

Its dropdown also offers Copy install prompt with this exact template:

> Download and install {App Name} on my device using its official repository: {Repository URL}.

Copying a prompt does not increment download clicks. Explain near the action that it opens the project's repository. Display the notice “Download at your own risk.” No software security scans, malware checks, signature verification, or security certification claims are provided.

Download clicks measure button activations, not successful downloads, unique users, or installations. Count them atomically and apply basic abuse limits. Repeated clicks can still affect the total; do not present it as a verified adoption measure. The outbound action uses the app's stored, approved URL rather than accepting an arbitrary redirect destination.

If metadata tracking finds a missing or inaccessible repository, retain the listing and its last approved information, show that availability needs review, and alert the owner. Never switch to a third-party mirror automatically. The owner can disable its outbound action or unpublish it. An emergency downloads switch disables repository-opening actions throughout the catalog.

## Catalog search and Jev

Visitor search operates only on published catalog records. It never discovers or publishes external repositories in response to a visitor query.

Use three bounded layers:

1. Retrieve candidates through names, aliases, descriptions, tags, and categories using database search. Support basic typo tolerance and exact-name preference.
2. Include owner-approved alternative-product aliases and use-case terms, enabling searches such as “alternative to Photoshop” without generating unsupported comparisons.
3. Use Jev to score a bounded candidate set for query relevance when AI spending is enabled. Validate returned scores and identities before using them. Relevance dominates ordering; activity and popularity provide secondary signals, with inactive listings downranked.

Jev receives candidate information from the catalog and returns structured decisions. The official API accepts supplied state and typed questions; it is the decision component of this search design. [TypeSafe quick start](https://docs.typesafe.ai/introduction/quickstart)

Cache ranked results against the normalized query, filters, catalog revision, and model configuration. Provide a deterministic database-search fallback when Jev is unavailable, times out, produces unusable output, or spending is paused. Ordinary search remains available in that mode. Apply request and query-size limits so anonymous traffic cannot cause unrestricted model spending.

When no strong match exists, label related suggestions as suggestions and offer an anonymous app-request form. Store the requested app name or use case and an optional GitHub URL in the admin queue. No email address is required. Requests do not immediately trigger external discovery; the owner can approve a supplied repository for a later scheduled discovery run.

## Scheduled discovery

Nightly discovery consumes owner-provided seed repositories, GitHub topic searches across the initial categories, recently created repositories, and active existing projects. Use GitHub's public repository APIs, bounded pagination, and rate-limit headers. Search can return incomplete or bounded results, so the run records its coverage rather than claiming to index every project. [GitHub search documentation](https://docs.github.com/en/rest/search/search)

Operating defaults, configurable without changing application code:

| Setting | Initial value |
| --- | --- |
| Schedule timezone | America/New_York |
| Discovery | Daily at 02:00 local time |
| Metadata maintenance | Weekly on Sunday at 03:00 local time |
| Priority maintenance | Daily at 03:00 for the owner-selected priority subset |
| Discord digest | Weekly on Monday at 09:00 local time |
| New candidates in the review queue | At most 10 per day |
| External repositories evaluated | At most 100 per discovery run |
| Jev search ranking input | At most 20 catalog candidates per request |

Persist local schedule dates to prevent duplicate work across restarts and daylight-saving transitions. A single scheduler process creates due jobs; durable run identities and database locking prevent overlapping instances from creating duplicate runs.

The agent gathers available repository metadata, documentation excerpts, release information, and star snapshots. Stars and observed growth guide discovery without becoming a minimum eligibility threshold. Absolute growth and proportional growth remain separate signals so smaller growing projects can surface. A first observation has no measured growth and is never presented as a historical trend. Mature projects remain eligible.

Jev can suggest a category, score relevance to the store, and identify uncertainty using bounded supplied evidence. It has no publication, permission-management, or execution tools. Model judgments cannot fill missing factual fields without supporting upstream evidence. Treat repository text as untrusted input and treat model output as a proposal.

Deduplicate by GitHub repository ID. A rejected project stays suppressed until the owner reopens it; discovery may update its evidence without silently returning it to the approval queue. Ineligible or uncertain findings remain private and are summarized for review. NSFW projects are excluded from public publication even when discovered.

## Approval and maintenance

Candidate states are pending, approved, and rejected. Published apps separately have published or unpublished status and an active, inactive, or availability-needs-review condition.

The owner reviews a candidate's source, description, suggested categories, free-use eligibility, documented setup, and uncertainty. Approval publishes the exact reviewed revision atomically. Concurrent candidate updates cannot change the material being approved without requiring the owner to review the new revision.

Routine factual refreshes can update approved fields such as latest stable version, requirements, and source timestamps. Preserve explicit owner overrides. Repository identity changes, license or free-use changes, and category changes create pending change proposals and retain the previous approved public values.

Track release and repository activity internally. An inferred default marks a project inactive when upstream marks it archived or when it has had neither a release nor repository activity for 12 months. Inactivity affects ranking and does not automatically remove the app.

Weekly refreshes apply to the catalog, subject to the configured limits and available capacity. The owner selects a small priority subset for daily refreshes when faster release visibility is useful. Budget pauses or failures can delay updates; source timestamps show the actual last successful refresh.

## Administration and Discord

One owner controls a protected admin interface. Sign-in authorizes a single configured GitHub user ID; a successful GitHub login from another account grants no administrator access. Visitor accounts are unnecessary. Every mutation verifies owner authorization, and browser mutations use protection against cross-site request forgery.

Basic admin tools cover listings, candidate approval and rejection, pending changes, categories and tags, app requests, seeds, schedules, job status, and cost reporting. Separate controls pause discovery, pause publication, pause maintenance, disable outbound download actions, and disable paid AI calls. Publication pause also blocks manual publication until the owner lifts it.

The weekly Discord digest links to the protected admin queue and summarizes pending candidates, uncertain findings, proposed changes, requests, recent runs, and spending by provider. Decisions happen in the admin interface; a webhook alone does not implement conversational Discord approvals.

Send immediate Discord notifications for budget stops, failed runs, and upstream availability or identity changes that need attention. A failed run records its error and checkpoint and pauses its affected job type until the owner resumes it through the admin interface. Other job types can continue unless a global pause applies.

Track undelivered notifications separately. A Discord delivery failure stays visible in the admin interface and does not recursively create more alerts. The owner can retry notification delivery. Resuming jobs is always explicit after a failure or spending pause.

## Budget controls

The monthly operating target is USD 20 across Vercel, Railway, TypeSafe/Jev, and any later model or search provider. Donation proceeds do not automatically increase this target.

Store the monthly budget, a conservative hosting allowance, actual or imported hosting usage, paid-call estimates and actual usage, and reservations for in-flight calls. Configure the hosting allowance from the selected deployment plans before enabling paid features. Missing cost configuration keeps paid AI disabled.

Before every paid call, reserve a conservative upper cost bound atomically against the remaining allowance, using configured provider rates and bounded request sizes. Reconcile the reservation with reported usage after the call. Retain a conservative charge for uncertain or timed-out calls until reconciliation; never assume a timeout was free. Concurrent requests share the same ledger.

If estimated total monthly cost reaches USD 20, or a planned call would exceed the remaining allowance, pause discovery, maintenance, and paid AI calls and notify the owner. Catalog browsing and deterministic search remain available while hosting capacity permits. A monthly rollover starts a fresh accounting period but does not automatically clear an owner-response-required pause.

Hosting charges continue independently of discovery and AI jobs. The application therefore presents this as an operating target with estimates, not a guaranteed provider billing cap. Configure provider spending controls and usage notifications during deployment where available; select a smaller deployment or self-host configuration if projected baseline costs exceed the target. Current provider plans must be checked before deployment. [Railway plans](https://docs.railway.com/pricing/plans), [Vercel Hobby plan](https://vercel.com/docs/plans/hobby)

## Architecture and persistence

Use a shared TypeScript codebase with a Next.js public site and admin interface, PostgreSQL persistence, and a scheduled-job entry point. Vercel hosts the Next.js application. Railway hosts PostgreSQL and the scheduler/job process. Share catalog, discovery, budget, and provider modules between the web application and job process; no separately maintained discovery service or message broker is needed initially.

Responsibilities are bounded as follows:

- Catalog: published records, categories, aliases, metadata overrides, click totals, and public retrieval.
- Search: local retrieval, alternative aliases, Jev scoring, caching, and fallback.
- Discovery: GitHub ingestion, star observations, deduplication, and private candidates.
- Review: revision-aware approval, publication, change proposals, and audit events.
- Jobs: due schedules, locking, durable run status, checkpoints, and pause/resume controls.
- Operations: provider adapters, spending reservations, Discord notifications, and owner authentication.

Persist apps and sources, categories/tags and app assignments, alternative aliases, candidates and revisions, metadata change proposals, star observations, requests, settings, job runs, notification delivery status, search cache entries, cost periods/entries/reservations, daily click totals, and admin audit events. Schema migrations preserve existing data and run as an explicit deployment operation.

Only published apps are exposed through public search and detail queries. Credentials remain server-side. Provider responses are validated before persistence. Public request endpoints use bounded input sizes and abuse limits; stored repository URLs must be public HTTPS GitHub repository URLs. Metadata fetches use fixed upstream API hosts rather than fetching arbitrary visitor-supplied URLs.

These application controls protect the service and approval workflow; they do not inspect downloaded software for safety.

## Self-hosting and data handling

Provide a container deployment running the same Next.js app, scheduler, and PostgreSQL database with environment configuration for the public URL, owner GitHub identity/OAuth, database, TypeSafe credentials, GitHub API credentials, schedules, budget, and optional Discord webhook. A self-hosted installation brings its own external provider credentials. Self-hosting the store does not imply hosting Jev locally.

When TypeSafe credentials are absent, local search works and discovery can still collect GitHub candidates for manual review without Jev judgments. Missing GitHub credentials cause discovery to remain disabled until configured. Missing Discord configuration leaves notifications in the admin interface.

Store aggregate daily download clicks without persistent visitor identity. Do not require visitor emails or retain raw search histories for personalization. Search-result caches have an initial 24-hour expiry and are invalidated by catalog revisions. Abuse limits may use short-lived request identifiers without retaining raw IP addresses in application records.

Retain operational logs for 30 days and cost/audit records for 12 months. App requests remain until the owner resolves or deletes them. Keep unresolved candidates and proposals until reviewed. Maintain daily database backups with seven daily copies and documented restoration instructions; actual backup storage and execution must fit the selected deployment allowance.

## Acceptance conditions

1. A visitor can browse all initial categories and filter by platform without signing in.
2. Search finds published apps by name, alias, category, and supported paid-product alternative terms. Jev can improve relevance when available; failure or budget pause preserves deterministic results.
3. Unpublished candidates and pending changes never appear through public queries.
4. An app page credits its developer, shows documented requirements and latest stable version, identifies missing information, and links to its approved source.
5. Download opens the approved repository and records a click. Copy install prompt produces the exact template without incrementing that count. The risk notice is visible.
6. A nightly run proposes bounded, deduplicated candidates. Initial star observations do not fabricate growth. Every new publication requires owner approval.
7. The owner can approve a reviewed revision, reject candidates, edit listings, manage categories, resolve requests, and use each emergency control. Another GitHub account cannot perform these operations.
8. Weekly maintenance refreshes factual metadata, preserves overrides, and queues material changes. Inactivity downranks a listing without automatically deleting it.
9. Discord digests summarize the queue and costs. A job failure pauses the affected work and remains paused until the owner resumes it; notification failures remain visible.
10. Spending reservations prevent concurrent paid calls from oversubscribing the configured AI allowance. A budget stop disables paid work while retaining local catalog search.
11. The documented container deployment supports the same core workflows with user-supplied credentials and a documented database backup/restore procedure.
12. Visual branding and final page layouts can be developed later without changing catalog, approval, discovery, or budget behavior.

## Planning boundaries

The implementation plan will sequence a usable manual catalog and protected administration first, followed by catalog search and Jev ranking, then scheduled discovery and maintenance, and finally deployment/operations. Each stage must respect the approval and cost controls from its first external call. Development verification should focus on these acceptance conditions and failure behavior; no implementation or provider spending is authorized merely by the creation of this specification.

## Implementation steering — October 11, 2026

The owner requested shadcndirectory.com as the reference for all UI work. Use its directory structure, sidebar filters, compact cards, and restrained monochrome styling, with original software-store content. SQLite is available for local development; PostgreSQL remains the shared production database. A daily backup runs at 03:30 with seven-file retention.

## Backend correction — owner instruction

The backend must use **FastAPI**, served by **Uvicorn**, with **Pydantic** validation. Next.js is the frontend only. Python owns persistence, authentication, API business rules, provider calls, spending, and scheduled jobs. Existing schemas/JSON records are retained. The earlier all-TypeScript architecture is superseded by this correction. Local development starts both services; Vercel hosts Next.js and Railway hosts FastAPI, its worker, and PostgreSQL.
