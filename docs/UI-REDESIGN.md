# Sourceboard interface refresh

The interface uses a charcoal navigation rail, a warm neutral canvas, botanical green and lime accents, consistent line icons, and responsive layouts. No external font or icon service is required.

## Updated screens

- Registration and sign-in: larger headline, focused forms, and a product illustration.
- Ask: topic suggestion cards, an evidence panel, a focused composer, and a New question action.
- Sources: upload area, document status styling, and a filter empty state with a Clear filter action.
- History: conversation rows with dates and answer status, plus an actionable empty state.
- Citations: a labelled source dialog with a readable passage and original-document download.
- Mobile: responsive navigation and stacked panels, including a compact layout at 320px.

Keyboard improvements include focus after choosing a suggestion, active navigation semantics, a labelled citation dialog, and IME-safe Enter handling. Upload and question actions respect provider availability. Reduced-motion preferences are supported.

## Validation

- TypeScript checking passed.
- Final production build passed, including the 320px navigation correction.
- Browser checks passed using deterministic sample API responses: sign-in/register switching, suggestions and focus, answers, citations, New question, source filtering and clearing, history navigation, and provider-disabled controls.
- No browser page errors were observed. Page overflow checks passed at 1440, 768, 390, and 320px with the final stylesheet.
- Desktop and mobile screenshots were visually inspected. Previews are in `data/ui-review/`.

The browser checks validate frontend behavior with sample data, not live database, upload, worker, or model integration. The initial redesign was implemented before UI/UX Pro Max was installed. The subsequent skill-guided refinement is documented in [UI-DESIGN-SYSTEM.md](UI-DESIGN-SYSTEM.md). The integrated browser failed to initialize, so verification used the available local headless browser runner.

## Run

With Docker Desktop running, rebuild the frontend with `docker compose up -d --build web`, then visit `http://localhost:3000`.

For local frontend development, use `npm --prefix frontend run dev`. Backend services are still needed for real account and document operations.
