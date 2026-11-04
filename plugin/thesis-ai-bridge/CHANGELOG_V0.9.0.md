# WordPress Bridge v0.9.0

- Preserved v0.8.5 abilities, WordPress Pull executor, WordPress-owned state, draft-first flow and WooCommerce Shop protection.
- `assets/front.css`: scoped `tai-generative` styles for the bounded AI design choices; responsive hero/grid, variable image aspect ratio and abstract artwork guided by approved site design tokens rather than hard-coded chocolate colors. No external image requests.
- PHP front-end font family output strips CSS special characters before interpolation; no new REST abilities or credentials required.
- This plugin provides only the rendering layer; the corresponding backend v0.9.0 generates and validates `GenerativeDesignSpec`.
- Real visual QA of WordPress-generated pages is not yet implemented in this release.
