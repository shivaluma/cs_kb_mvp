# Design

## Design System

Base implementation should use Vite, React, Tailwind CSS v4, shadcn/ui latest, @tabler/icons-react icons, and local design tokens. Components should favor shadcn primitives for buttons, cards, badges, inputs, tabs, separators, and scroll areas.

## Visual Theme

The product is a restrained operational console. Use tinted neutrals, thin borders, strong focus rings, compact vertical rhythm, and one primary accent for actions and selected states. The interface should feel lighter than an incident dashboard and more precise than a content CMS.

## Color Strategy

Use OKLCH tokens. Base surfaces should be warm-neutral with a green-cyan operational accent, amber for AI/caution, red for destructive/error, and blue only for informational links or secondary status. Avoid purple gradients, black/white extremes, and one-note teal domination.

## Typography

Use a native product font stack unless the project later adopts an internal brand font. Keep labels compact and readable, with clear hierarchy through weight and spacing rather than display type.

## Layout

Default shell is sidebar plus task workspace. Search should lead the page. Result list and SOP detail should support side-by-side desktop reading, then collapse cleanly on tablet/mobile. Avoid nested cards and repeated identical card grids.

## Components

- Buttons: shadcn button variants with icon-leading actions where useful.
- Inputs/selects: shadcn input/select styling, visible focus states, minimum touch target support.
- Badges: compact status/taxonomy metadata, never decorative chips without purpose.
- Panels: use borders and background layers rather than colored side stripes.
- AI panel: visually distinct but constrained, with citations shown as first-class evidence.

## Motion

Use short 150-200ms transitions for state feedback, hover, focus, and panel reveal. Respect reduced motion. No decorative page choreography.
