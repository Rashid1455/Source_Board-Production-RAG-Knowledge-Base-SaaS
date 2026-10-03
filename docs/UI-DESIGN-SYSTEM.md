# Sourceboard design system

Applied with the installed `ui-ux-pro-max` skill to the Next.js/React frontend.

## Direction

The skill's design-system search recommended minimal, spacious, functional layouts, clear typography, restrained motion, and consistent navigation for an enterprise knowledge workspace. Its generic color result matched an event palette; the knowledge-base search instead recommended a clean hierarchy and minimal functional color. Sourceboard retains its existing charcoal, green, and lime identity while applying those layout and accessibility principles.

Typography uses the locally available Segoe UI/system sans-serif stack, avoiding an external font dependency. Body copy and inputs on mobile use 16px type; secondary labels are smaller. Normal text targets at least 4.5:1 contrast. Headings, muted text, and controls share consistent surface-aware colors.

## Tokens and behavior

| Role | Value |
| --- | --- |
| Canvas | `#f6f6f0` |
| Surface | `#ffffff` |
| Navigation | `#202824` |
| Primary text | `#242b28` |
| Secondary text | `#586550` |
| Action fill | `#d6f38a` |
| Action text | `#293d24` |
| Focus | `#527634` |
| Control target | At least 44 × 44px for action buttons |
| Motion | Short color/border transitions; reduced motion supported |

## Applied improvements

- Enlarged reading text, form inputs, buttons, citations, and dialog controls.
- Stable card hover states without positional movement.
- Keyboard skip link, active navigation semantics, and document table caption.
- Persistent answer, source, history, and connection error messages with retry actions.
- Source/history loading indicators instead of misleading empty states.
- Disabled form controls during authentication and question submission.
- Next.js route error boundary with a recovery action.
- Increased contrast for muted labels, table headings, preview text, and placeholders.

## Verification scope

TypeScript and production build checks run locally. Headless browser checks use deterministic mocked API responses, covering the main user flows, connection/answer/history error recovery, provider-disabled actions, and button target sizes. Ask, library, and history layouts are checked at 320, 375, 390, 768, 1024, and 1440px.

An automated computed-color check found no below-threshold text pairs on the sampled sign-in, workspace, citation, library, history, and mobile screenshots after refinement. This is a targeted check, not a full WCAG certification or screen-reader audit. The application has one light content theme with a dark navigation rail; no separate dark mode is implemented.

Preview images and local browser check scripts are under `data/ui-review/`. These checks do not validate live database, storage, or model integrations.

## Cubify Digital branding and ambient motion

The original matching logo from `Downloads/Cubify Digital Final.jpg` is retained at `frontend/public/brand/cubify-digital.jpg`. The active asset is `frontend/public/brand/cubify-digital-transparent.png`, edited with built-in ImageGen to remove the white background. Alpha transparency was verified (1925 × 817 RGBA, alpha range 0–255). The light pages show its colors; a CSS white treatment makes the same transparent artwork readable on the dark sidebar. There is no backing, border, or rounded frame. Both the Docker image and local standalone startup copy the public assets directory.

Image edit prompt: “Use case: background-extraction. Edit target: supplied Cubify Digital logo. Remove only the white background and make it truly transparent with an alpha channel, including all spaces inside and around the letters. Preserve the exact original logo shapes, stylized lettering, DIGITAL text, navy and vivid blue colors, proportions, and composition. Do not redesign, add, remove, or reinterpret any strokes. No shadows, no border, no white matte, no checkerboard pixels. Output a transparent PNG, tightly framed with a small even transparent margin around the complete logo.”

Two decorative layers drift slowly behind the content using transform animations. They do not receive pointer events or appear in the accessibility tree. The Pause motion control stores the user's preference locally, and the operating system's reduced-motion preference disables the animation. No animation library or external asset service is required.
